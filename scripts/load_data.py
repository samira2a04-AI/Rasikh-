"""Seed the Rasikh database from the runtime data files under ``data/``.

Deterministic and idempotent:
- Every record is upserted by its natural key (member_id, org_id, contract_id,
  obl_id, request_id, clause_number, ...) or by the unique constraints that
  stand in for one (MatterAssignment (member_id, org_id), ReviewStandardClause
  clause_number, ContractClause (contract_id, clause_label)).
- Re-running never creates duplicates and never deletes existing rows.
- All work happens in ONE transaction: a failure rolls back everything.

Approved conventions implemented here (see project decisions):
- L-C-024 (requester ``EXTERNAL``) is SKIPPED, never synthesised.
- Firm-wide partners (``access == "firm_wide"``) get MatterAssignment rows for
  every organisation, merged with the explicit ``assigned_team`` rows.
- Rulebook categories use the approved section/clause mapping.
- Contract gap annotations ([...]) become ContractClause rows with
  ``clause_label = NULL``, text preserved verbatim.
- content_uri values are repository-relative paths under ``data/``.
- Request.created_at = header Date at UTC midnight; Contract/DataRoomFile
  created_at use the server default.
- Obligation.band is computed from rulebook clause 6.2 thresholds parsed at
  load time (never hard-coded), reference date 2026-07-01 (dataset "today").
- answer_key.json is NEVER loaded (evaluation-only ground truth).

Run from the repository root:  python scripts/load_data.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Make the repository root importable regardless of where this is run from.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select

from app.database.connection import SessionLocal
from app.models import (
    Contract,
    ContractClause,
    DataRoomFile,
    MatterAssignment,
    Obligation,
    Organisation,
    Request,
    ReviewStandardClause,
    TeamMember,
)

DATA_DIR = REPO_ROOT / "data"

# The dataset's stated "today" (data/README.md) — NOT the system clock.
REFERENCE_DATE = date(2026, 7, 1)

# Approved ReviewStandardClause category mapping.
SECTION_CATEGORIES = {
    "1": "review_checklist",
    "3": "risk_taxonomy",
    "4": "sharia_sensitive",
    "5": "escalation_rule",
    "6": "obligation_threshold",
}
SECTION0_CLAUSE_CATEGORIES = {
    "0.1": "gate_grounding",
    "0.2": "gate_approval",
    "0.3": "access_by_matter",
    "0.4": "privilege",
    "0.5": "other",
    "0.6": "other",
}

ORG_ID_RE = re.compile(r"ORG-\d+")
CONTRACT_CLAUSE_START_RE = re.compile(r"^(?P<label>\d+)\.\s+(?P<rest>.*)$")
GAP_ANNOTATION_RE = re.compile(r"^\[.*\]$")
RULEBOOK_HEADING_RE = re.compile(
    r"\*\*Clause (?P<number>\d+\.\d+) — (?P<title>.+?)\*\*", re.DOTALL
)
REQUEST_HEADER_RE = re.compile(r"^(?P<key>[A-Za-z_ ]+?):\s*(?P<value>.+)$")


# ---------------------------------------------------------------------------
# File parsing helpers (pure functions; no database access)
# ---------------------------------------------------------------------------

def read_json(filename: str) -> Any:
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


def parse_rulebook() -> list[dict[str, str]]:
    """Parse rulebook/*.md into ReviewStandardClause field dicts."""
    clauses: list[dict[str, str]] = []
    for path in sorted((DATA_DIR / "rulebook").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        headings = list(RULEBOOK_HEADING_RE.finditer(content))
        if not headings:
            raise ValueError(f"{path.name}: no '**Clause N.M — …**' headings found")
        for i, match in enumerate(headings):
            number = match.group("number")
            title = match.group("title").strip()
            body_start = match.end()
            body_end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
            body = content[body_start:body_end].strip()
            section = number.split(".")[0]
            if number in SECTION0_CLAUSE_CATEGORIES:
                category = SECTION0_CLAUSE_CATEGORIES[number]
            elif section in SECTION_CATEGORIES:
                category = SECTION_CATEGORIES[section]
            else:
                raise ValueError(f"No approved category mapping for clause {number}")
            clauses.append(
                {
                    "clause_number": number,
                    "text": f"{title}\n\n{body}",
                    "category": category,
                }
            )
    return clauses


def parse_contract(path: Path) -> dict[str, Any]:
    """Parse one contract file into Contract + ContractClause field dicts."""
    lines = path.read_text(encoding="utf-8").splitlines()
    title = lines[0].strip()

    header_block = "\n".join(lines[:6])
    org_match = ORG_ID_RE.search(header_block)
    if org_match is None:
        raise ValueError(f"{path.name}: no 'Matter: ORG-xxxx' header found")
    org_id = org_match.group(0)
    if "العربية" in header_block:
        language = "ar"
    elif "English" in header_block:
        language = "en"
    else:
        raise ValueError(f"{path.name}: cannot determine Language")

    # Body starts after the first blank line following the header block.
    body_start = next(i for i, ln in enumerate(lines) if not ln.strip()) + 1

    clauses: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            clauses.append(
                {"clause_label": current["label"], "text": " ".join(current["parts"])}
            )
            current = None

    for line in lines[body_start:]:
        stripped = line.strip()
        if not stripped:
            continue
        clause_match = CONTRACT_CLAUSE_START_RE.match(stripped)
        gap_match = GAP_ANNOTATION_RE.match(stripped)
        if clause_match is not None:
            flush()
            current = {"label": clause_match.group("label"), "parts": [clause_match.group("rest")]}
        elif gap_match is not None:
            # Gap annotation: own row, clause_label NULL, text verbatim.
            flush()
            current = {"label": None, "parts": [stripped]}
        elif current is not None:
            current["parts"].append(stripped)
        else:
            raise ValueError(
                f"{path.name}: unexpected body line before first clause: {stripped!r}"
            )
    flush()

    return {
        "contract_id": path.name.split("_")[0],
        "org_id": org_id,
        "title": title,
        "language": language,
        "content_uri": f"data/contracts/{path.name}",
        "clauses": clauses,
    }


def parse_dataroom_file(path: Path) -> dict[str, Any]:
    """Parse one data-room file into DataRoomFile field dicts."""
    lines = path.read_text(encoding="utf-8").splitlines()
    title = lines[0].strip()
    header_block = "\n".join(lines[:4])
    org_match = ORG_ID_RE.search(header_block)
    if org_match is None:
        raise ValueError(f"{path.name}: no 'Matter: ORG-xxxx' header found")
    return {
        "file_id": path.name.split("_")[0],
        "org_id": org_match.group(0),
        "title": title,
        "privileged": "PRIVILEGED" in header_block,
        "content_uri": f"data/dataroom/{path.name}",
    }


def parse_request(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Parse one request file.

    Returns ``(fields, None)`` on success or ``(None, reason)`` when the
    request must be skipped (e.g. EXTERNAL requester).
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    header: dict[str, str] = {}
    body_start = len(lines)
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        match = REQUEST_HEADER_RE.match(line.strip())
        if match is None:
            raise ValueError(f"{path.name}: unparseable header line {line!r}")
        header[match.group("key").strip()] = match.group("value").strip()

    request_id = header["Request ID"]
    requester_id = header["Requester member_id"]
    if requester_id == "EXTERNAL":
        # Approved decision: never synthesise a TeamMember for external
        # requesters; skip and report.
        return None, f"{request_id}: skipped — EXTERNAL requester"

    return (
        {
            "request_id": request_id,
            "requester_id": requester_id,
            "org_id": header["Matter"],
            "request_type": header["Type"],
            # Seeded requests are recorded but not yet processed by any
            # pipeline component, so they sit at the lifecycle's documented
            # starting state ('intake' per docs/data-schema.md §3 / FR-001).
            "status": "intake",
            "raw_content": "\n".join(lines[body_start:]).strip(),
            "created_at": datetime.combine(
                date.fromisoformat(header["Date"]), datetime.min.time(), tzinfo=timezone.utc
            ),
        },
        None,
    )


def extract_band_thresholds(rulebook_clauses: list[dict[str, str]]) -> dict[str, int]:
    """Parse the obligation-band thresholds out of rulebook clause 6.2.

    Thresholds are read from the rulebook text at load time — they are never
    hard-coded constants (docs/data-schema.md §9).
    """
    clause_62 = next(
        (c for c in rulebook_clauses if c["clause_number"] == "6.2"), None
    )
    if clause_62 is None:
        raise ValueError("rulebook clause 6.2 (alert thresholds) not found")
    text = clause_62["text"]
    on_track_match = re.search(r"more than (\d+) days", text)
    reminder_match = re.search(r"(\d+) to (\d+) days", text)
    urgent_match = re.search(r"(\d+) days or fewer", text)
    if not (on_track_match and reminder_match and urgent_match):
        raise ValueError("could not parse band thresholds from clause 6.2")
    on_track_gt = int(on_track_match.group(1))
    reminder_lo, reminder_hi = int(reminder_match.group(1)), int(reminder_match.group(2))
    urgent_le = int(urgent_match.group(1))
    if not (urgent_le + 1 == reminder_lo and reminder_hi == on_track_gt):
        raise ValueError(
            "inconsistent thresholds parsed from clause 6.2: "
            f"urgent<={urgent_le}, reminder {reminder_lo}-{reminder_hi}, "
            f"on_track>{on_track_gt}"
        )
    return {
        "on_track_gt": on_track_gt,
        "reminder_lo": reminder_lo,
        "reminder_hi": reminder_hi,
        "urgent_le": urgent_le,
    }


def compute_band(due_date: date, thresholds: dict[str, int]) -> str:
    """Classify an obligation due date against REFERENCE_DATE (dataset today)."""
    if due_date < REFERENCE_DATE:
        return "overdue"
    days_until = (due_date - REFERENCE_DATE).days
    if days_until <= thresholds["urgent_le"]:
        return "urgent"
    if thresholds["reminder_lo"] <= days_until <= thresholds["reminder_hi"]:
        return "reminder"
    if days_until > thresholds["on_track_gt"]:
        return "on_track"
    raise ValueError(f"due date {due_date} falls between defined bands")


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert_team_members(session, members: list[dict[str, Any]], stats: dict[str, int]) -> None:
    for m in members:
        obj = session.get(TeamMember, m["member_id"])
        if obj is None:
            session.add(
                TeamMember(
                    member_id=m["member_id"],
                    name=m["name"],
                    role=m["role"],
                    practice=m.get("practice"),
                    can_approve=m["can_approve"],
                )
            )
            stats["team_member.ins"] += 1
        else:
            changed = False
            for attr, value in (
                ("name", m["name"]),
                ("role", m["role"]),
                ("practice", m.get("practice")),
                ("can_approve", m["can_approve"]),
            ):
                if getattr(obj, attr) != value:
                    setattr(obj, attr, value)
                    changed = True
            if changed:
                stats["team_member.upd"] += 1


def upsert_organisations(session, orgs: list[dict[str, Any]], stats: dict[str, int]) -> None:
    for o in orgs:
        obj = session.get(Organisation, o["org_id"])
        if obj is None:
            session.add(
                Organisation(
                    org_id=o["org_id"],
                    name=o["name"],
                    sector=o["sector"],
                    type=o["type"],
                    status=o["status"],
                )
            )
            stats["organisation.ins"] += 1
        else:
            changed = False
            for attr, value in (
                ("name", o["name"]),
                ("sector", o["sector"]),
                ("type", o["type"]),
                ("status", o["status"]),
            ):
                if getattr(obj, attr) != value:
                    setattr(obj, attr, value)
                    changed = True
            if changed:
                stats["organisation.upd"] += 1


def build_assignment_pairs(
    members: list[dict[str, Any]], orgs: list[dict[str, Any]]
) -> set[tuple[str, str]]:
    """Explicit assigned_team pairs plus firm-wide partners × every org."""
    pairs: set[tuple[str, str]] = set()
    for o in orgs:
        for member_id in o["assigned_team"]:
            pairs.add((member_id, o["org_id"]))
    firm_wide = [m["member_id"] for m in members if m["access"] == "firm_wide"]
    for member_id in firm_wide:
        for o in orgs:
            pairs.add((member_id, o["org_id"]))
    return pairs


def upsert_assignments(session, pairs: set[tuple[str, str]], stats: dict[str, int]) -> None:
    existing = set(
        session.execute(select(MatterAssignment.member_id, MatterAssignment.org_id))
    )
    missing = sorted(pairs - existing)
    session.add_all(
        [MatterAssignment(member_id=m, org_id=o) for m, o in missing]
    )
    stats["matter_assignment.ins"] = len(missing)


def upsert_standard_clauses(session, clauses: list[dict[str, str]], stats: dict[str, int]) -> None:
    existing = {
        c.clause_number: c
        for c in session.scalars(select(ReviewStandardClause))
    }
    for c in clauses:
        obj = existing.get(c["clause_number"])
        if obj is None:
            session.add(ReviewStandardClause(**c))
            stats["review_standard_clause.ins"] += 1
        else:
            changed = False
            if obj.text != c["text"]:
                obj.text = c["text"]
                changed = True
            if obj.category != c["category"]:
                obj.category = c["category"]
                changed = True
            if changed:
                stats["review_standard_clause.upd"] += 1


def upsert_contracts(session, contracts: list[dict[str, Any]], stats: dict[str, int]) -> None:
    for rec in contracts:
        obj = session.get(Contract, rec["contract_id"])
        if obj is None:
            obj = Contract(
                contract_id=rec["contract_id"],
                org_id=rec["org_id"],
                title=rec["title"],
                language=rec["language"],
                privileged=False,
                content_uri=rec["content_uri"],
            )
            session.add(obj)
            stats["contract.ins"] += 1
        else:
            changed = False
            for attr, value in (
                ("org_id", rec["org_id"]),
                ("title", rec["title"]),
                ("language", rec["language"]),
                ("content_uri", rec["content_uri"]),
            ):
                if getattr(obj, attr) != value:
                    setattr(obj, attr, value)
                    changed = True
            if changed:
                stats["contract.upd"] += 1

        existing_rows = session.scalars(
            select(ContractClause).where(ContractClause.contract_id == rec["contract_id"])
        ).all()
        labeled = {cc.clause_label: cc for cc in existing_rows if cc.clause_label is not None}
        unlabeled_texts = {cc.text for cc in existing_rows if cc.clause_label is None}
        for cl in rec["clauses"]:
            if cl["clause_label"] is not None:
                target = labeled.get(cl["clause_label"])
                if target is None:
                    session.add(
                        ContractClause(
                            contract_id=rec["contract_id"],
                            clause_label=cl["clause_label"],
                            text=cl["text"],
                        )
                    )
                    stats["contract_clause.ins"] += 1
                elif target.text != cl["text"]:
                    target.text = cl["text"]
                    stats["contract_clause.upd"] += 1
            else:
                if cl["text"] not in unlabeled_texts:
                    session.add(
                        ContractClause(
                            contract_id=rec["contract_id"],
                            clause_label=None,
                            text=cl["text"],
                        )
                    )
                    stats["contract_clause.ins"] += 1


def upsert_dataroom_files(session, files: list[dict[str, Any]], stats: dict[str, int]) -> None:
    for f in files:
        obj = session.get(DataRoomFile, f["file_id"])
        if obj is None:
            session.add(DataRoomFile(**f))
            stats["data_room_file.ins"] += 1
        else:
            changed = False
            for attr, value in (
                ("org_id", f["org_id"]),
                ("title", f["title"]),
                ("privileged", f["privileged"]),
                ("content_uri", f["content_uri"]),
            ):
                if getattr(obj, attr) != value:
                    setattr(obj, attr, value)
                    changed = True
            if changed:
                stats["data_room_file.upd"] += 1


def upsert_obligations(
    session,
    obligations: list[dict[str, Any]],
    thresholds: dict[str, int],
    stats: dict[str, int],
) -> None:
    for o in obligations:
        band = compute_band(date.fromisoformat(o["due_date"]), thresholds)
        values = {
            "org_id": o["org_id"],
            "owner_id": o["owner"],
            "type": o["type"],
            "description": o["description"],
            "due_date": date.fromisoformat(o["due_date"]),
            "band": band,
            "note": o.get("note"),
        }
        obj = session.get(Obligation, o["obl_id"])
        if obj is None:
            session.add(Obligation(obligation_id=o["obl_id"], **values))
            stats["obligation.ins"] += 1
        else:
            changed = False
            for attr, value in values.items():
                if getattr(obj, attr) != value:
                    setattr(obj, attr, value)
                    changed = True
            if changed:
                stats["obligation.upd"] += 1


def upsert_requests(
    session, requests: list[dict[str, Any]], stats: dict[str, int]
) -> None:
    for r in requests:
        obj = session.get(Request, r["request_id"])
        if obj is None:
            session.add(Request(**r))
            stats["request.ins"] += 1
        else:
            changed = False
            for attr, value in (
                ("requester_id", r["requester_id"]),
                ("org_id", r["org_id"]),
                ("request_type", r["request_type"]),
                ("status", r["status"]),
                ("raw_content", r["raw_content"]),
                ("created_at", r["created_at"]),
            ):
                if getattr(obj, attr) != value:
                    setattr(obj, attr, value)
                    changed = True
            if changed:
                stats["request.upd"] += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    members = read_json("firm_team.json")
    orgs = read_json("organizations.json")
    obligations = read_json("obligations.json")

    rulebook_clauses = parse_rulebook()
    thresholds = extract_band_thresholds(rulebook_clauses)
    contracts = [parse_contract(p) for p in sorted((DATA_DIR / "contracts").glob("*.txt"))]
    dataroom_files = [
        parse_dataroom_file(p) for p in sorted((DATA_DIR / "dataroom").glob("*.txt"))
    ]

    requests: list[dict[str, Any]] = []
    skipped: list[str] = []
    for path in sorted((DATA_DIR / "requests").glob("*.txt")):
        fields, reason = parse_request(path)
        if fields is None:
            skipped.append(reason or path.name)
        else:
            requests.append(fields)

    assignment_pairs = build_assignment_pairs(members, orgs)

    stats: dict[str, int] = defaultdict(int)
    with SessionLocal() as session, session.begin():
        upsert_team_members(session, members, stats)
        upsert_organisations(session, orgs, stats)
        upsert_assignments(session, assignment_pairs, stats)
        upsert_standard_clauses(session, rulebook_clauses, stats)
        upsert_contracts(session, contracts, stats)
        upsert_dataroom_files(session, dataroom_files, stats)
        upsert_obligations(session, obligations, thresholds, stats)
        upsert_requests(session, requests, stats)

    print("Load complete (single committed transaction).")
    print(f"  Band thresholds from clause 6.2 @ {REFERENCE_DATE}: {thresholds}")
    for key in sorted(stats):
        if stats[key]:
            print(f"  {key}: {stats[key]}")
    if skipped:
        print("Skipped records:")
        for reason in skipped:
            print(f"  - {reason}")
    else:
        print("Skipped records: none")

    print("\nRow totals now in database:")
    with SessionLocal() as count_session:
        for label, model in (
            ("team_member", TeamMember),
            ("organisation", Organisation),
            ("matter_assignment", MatterAssignment),
            ("review_standard_clause", ReviewStandardClause),
            ("contract", Contract),
            ("contract_clause", ContractClause),
            ("data_room_file", DataRoomFile),
            ("obligation", Obligation),
            ("request", Request),
        ):
            count = count_session.query(model).count()
            print(f"  {label}: {count}")
    print(f"  expected matter_assignment pairs from sources: {len(assignment_pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())