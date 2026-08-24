"""Validate the seeded Rasikh database against the source data files.

Re-parses ``data/`` independently and checks the database row-by-row:
row counts, MatterAssignment coverage, rulebook categories, contract clauses
(including NULL-label gap annotations and Arabic preservation), privilege
flags, obligation bands, request skipping, foreign-key integrity, natural-key
duplicates, and content_uri existence.

Run from the repository root:  python scripts/validate_data.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Make the repository root importable regardless of where this is run from.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import func, select

import load_data  # scripts/load_data.py — shared parsers (sys.path[0] = scripts/)
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

ARABIC_RE = load_data.re.compile(r"[\u0600-\u06FF]")

failures: list[str] = []
checks = 0


def check(condition: bool, description: str) -> None:
    global checks
    checks += 1
    if condition:
        print(f"[PASS] {description}")
    else:
        print(f"[FAIL] {description}")
        failures.append(description)


def main() -> int:
    members = load_data.read_json("firm_team.json")
    orgs = load_data.read_json("organizations.json")
    obligations_src = load_data.read_json("obligations.json")
    rulebook_clauses = load_data.parse_rulebook()
    thresholds = load_data.extract_band_thresholds(rulebook_clauses)
    contracts_parsed = [
        load_data.parse_contract(p)
        for p in sorted((load_data.DATA_DIR / "contracts").glob("*.txt"))
    ]
    dataroom_parsed = [
        load_data.parse_dataroom_file(p)
        for p in sorted((load_data.DATA_DIR / "dataroom").glob("*.txt"))
    ]

    expected_pairs = load_data.build_assignment_pairs(members, orgs)

    with SessionLocal() as session:
        # ---- Row counts -------------------------------------------------
        count_of = lambda model: session.query(model).count()  # noqa: E731
        check(count_of(TeamMember) == 10, f"TeamMember has 10 rows (got {count_of(TeamMember)})")
        check(count_of(Organisation) == 150, f"Organisation has 150 rows (got {count_of(Organisation)})")
        check(
            count_of(ReviewStandardClause) == len(rulebook_clauses),
            f"ReviewStandardClause has {len(rulebook_clauses)} rows "
            f"(got {count_of(ReviewStandardClause)})",
        )
        check(count_of(Contract) == 12, f"Contract has 12 rows (got {count_of(Contract)})")
        check(count_of(DataRoomFile) == 6, f"DataRoomFile has 6 rows (got {count_of(DataRoomFile)})")
        check(count_of(Obligation) == 8, f"Obligation has 8 rows (got {count_of(Obligation)})")
        check(count_of(Request) == 26, f"Request has 26 rows, L-C-024 skipped (got {count_of(Request)})")

        # ---- MatterAssignment -------------------------------------------
        db_pairs = set(
            session.execute(select(MatterAssignment.member_id, MatterAssignment.org_id))
        )
        check(
            db_pairs == expected_pairs,
            f"MatterAssignment pairs exactly match sources "
            f"(db={len(db_pairs)}, expected={len(expected_pairs)}, "
            f"missing={len(expected_pairs - db_pairs)}, extra={len(db_pairs - expected_pairs)})",
        )
        firm_wide_ids = [m["member_id"] for m in members if m["access"] == "firm_wide"]
        org_id_list = [o["org_id"] for o in orgs]
        missing_firmwide = [
            (m, o) for m in firm_wide_ids for o in org_id_list if (m, o) not in db_pairs
        ]
        check(not missing_firmwide, "firm-wide partners assigned to all 150 organisations")
        dup_assignments = session.execute(
            select(MatterAssignment.member_id, MatterAssignment.org_id)
            .group_by(MatterAssignment.member_id, MatterAssignment.org_id)
            .having(func.count() > 1)
        ).all()
        check(not dup_assignments, "no duplicate (member_id, org_id) assignments")

        # ---- ReviewStandardClause ---------------------------------------
        std_rows = session.scalars(select(ReviewStandardClause)).all()
        numbers = [c.clause_number for c in std_rows]
        check(len(numbers) == len(set(numbers)), "rulebook clause numbers are unique")
        category_errors = []
        for c in std_rows:
            section = c.clause_number.split(".")[0]
            expected_cat = load_data.SECTION0_CLAUSE_CATEGORIES.get(
                c.clause_number, load_data.SECTION_CATEGORIES.get(section)
            )
            if c.category != expected_cat:
                category_errors.append((c.clause_number, c.category, expected_cat))
        check(not category_errors, f"rulebook categories match approved mapping ({category_errors or 'all ok'})")

        # ---- Contract / ContractClause ----------------------------------
        total_expected_clauses = sum(len(c["clauses"]) for c in contracts_parsed)
        check(
            count_of(ContractClause) == total_expected_clauses,
            f"ContractClause has {total_expected_clauses} rows "
            f"(got {count_of(ContractClause)})",
        )
        for rec in contracts_parsed:
            rows = session.scalars(
                select(ContractClause).where(ContractClause.contract_id == rec["contract_id"])
            ).all()
            db_labeled = {
                cc.clause_label: cc.text for cc in rows if cc.clause_label is not None
            }
            src_labeled = {
                cl["clause_label"]: cl["text"]
                for cl in rec["clauses"]
                if cl["clause_label"] is not None
            }
            check(
                db_labeled == src_labeled,
                f"{rec['contract_id']}: labeled clauses match source "
                f"({len(src_labeled)} clauses)",
            )
            db_unlabeled = sorted(
                str(cc.text) for cc in rows if cc.clause_label is None
            )
            src_unlabeled = sorted(
                str(cl["text"]) for cl in rec["clauses"] if cl["clause_label"] is None
            )
            check(
                db_unlabeled == src_unlabeled,
                f"{rec['contract_id']}: gap annotations stored verbatim with NULL label "
                f"({len(src_unlabeled)} annotation(s))",
            )
        arabic_contracts = ["C-09", "C-10", "C-11"]
        for cid in arabic_contracts:
            texts = [
                cc.text
                for cc in session.scalars(
                    select(ContractClause).where(ContractClause.contract_id == cid)
                )
            ]
            check(
                all(ARABIC_RE.search(t) for t in texts),
                f"{cid}: Arabic text preserved in all clause rows",
            )

        # ---- DataRoomFile ------------------------------------------------
        dr_rows = session.scalars(select(DataRoomFile)).all()
        privileged_ids = sorted([f.file_id for f in dr_rows if f.privileged])
        check(privileged_ids == ["DR-04"], f"exactly DR-04 is privileged (got {privileged_ids})")
        dr_mismatches = []
        for src in dataroom_parsed:
            row = next((f for f in dr_rows if f.file_id == src["file_id"]), None)
            if row is None or any(
                getattr(row, attr) != src[attr]
                for attr in ("org_id", "title", "privileged", "content_uri")
            ):
                dr_mismatches.append(src["file_id"])
        check(not dr_mismatches, f"data-room rows match sources ({dr_mismatches or 'all ok'})")

        # ---- Obligation ---------------------------------------------------
        member_ids = {m["member_id"] for m in members}
        org_ids = {o["org_id"] for o in orgs}
        obl_rows = session.scalars(select(Obligation)).all()
        bad_obl_fk = [
            o.obligation_id
            for o in obl_rows
            if o.org_id not in org_ids or o.owner_id not in member_ids
        ]
        check(not bad_obl_fk, f"obligation foreign keys valid ({bad_obl_fk or 'all ok'})")
        bands = {o.obligation_id: o.band for o in obl_rows}
        # Expected bands recomputed independently from the source files using
        # clause 6.2 thresholds and the dataset reference date 2026-07-01.
        expected_bands = {
            o["obl_id"]: load_data.compute_band(
                date.fromisoformat(o["due_date"]), thresholds
            )
            for o in obligations_src
        }
        band_mismatches = {
            k: (v, expected_bands[k]) for k, v in bands.items() if v != expected_bands[k]
        }
        check(
            not band_mismatches,
            f"obligation bands match clause 6.2 computation ({band_mismatches or 'all ok'})",
        )
        print(
            "       note: answer_key ALERTS expects alerts for OB-04 (overdue), OB-02 "
            "(urgent), OB-03+OB-05 (reminder); OB-01 is past-due but recorded as "
            "'historical/closed — not re-alerted', an application-level rule; its "
            "stored band remains the mechanical 'overdue'."
        )

        # ---- Request ------------------------------------------------------
        req_rows = session.scalars(select(Request)).all()
        req_ids = {r.request_id for r in req_rows}
        check("L-C-024" not in req_ids, "L-C-024 (EXTERNAL requester) absent as approved")
        bad_req_fk = [
            r.request_id
            for r in req_rows
            if r.requester_id not in member_ids
            or (r.org_id is not None and r.org_id not in org_ids)
        ]
        check(not bad_req_fk, f"request foreign keys valid ({bad_req_fk or 'all ok'})")
        loaded_types = sorted({r.request_type for r in req_rows})
        print(f"       request_type values loaded: {loaded_types}")

        # ---- Global FK orphan checks per seeded referencing table ---------
        def orphan_count(model, attr, referenced_ids):
            values = {getattr(row, attr) for row in session.scalars(select(model))}
            return len({v for v in values if v is not None} - referenced_ids)

        contract_org_bad = orphan_count(Contract, "org_id", org_ids)
        dr_org_bad = orphan_count(DataRoomFile, "org_id", org_ids)
        ma_member_bad = orphan_count(MatterAssignment, "member_id", member_ids)
        ma_org_bad = orphan_count(MatterAssignment, "org_id", org_ids)
        obl_org_bad = orphan_count(Obligation, "org_id", org_ids)
        obl_owner_bad = orphan_count(Obligation, "owner_id", member_ids)
        req_requester_bad = orphan_count(Request, "requester_id", member_ids)
        req_org_bad = len(
            {r.org_id for r in req_rows if r.org_id is not None and r.org_id not in org_ids}
        )
        fk_total = (
            contract_org_bad
            + dr_org_bad
            + ma_member_bad
            + ma_org_bad
            + obl_org_bad
            + obl_owner_bad
            + req_requester_bad
            + req_org_bad
        )
        check(fk_total == 0, f"no orphan foreign keys in seeded tables (bad={fk_total})")

        # ---- Natural-key duplicates --------------------------------------
        dup_clause_labels = session.execute(
            select(ContractClause.contract_id, ContractClause.clause_label)
            .where(ContractClause.clause_label.is_not(None))
            .group_by(ContractClause.contract_id, ContractClause.clause_label)
            .having(func.count() > 1)
        ).all()
        check(not dup_clause_labels, "no duplicate (contract_id, clause_label)")
        dup_numbers = session.execute(
            select(ReviewStandardClause.clause_number)
            .group_by(ReviewStandardClause.clause_number)
            .having(func.count() > 1)
        ).all()
        check(not dup_numbers, "no duplicate rulebook clause_number")

        # ---- content_uri existence ----------------------------------------
        uris = [c.content_uri for c in session.scalars(select(Contract))] + [
            f.content_uri for f in session.scalars(select(DataRoomFile))
        ]
        missing_uris = [uri for uri in uris if uri is None or not (REPO_ROOT / uri).exists()]
        check(
            not missing_uris,
            f"all content_uri paths exist on disk ({missing_uris or f'{len(uris)}/{len(uris)} ok'})",
        )

    print()
    if failures:
        print(f"VALIDATION FAILED: {len(failures)} of {checks} checks failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"All {checks} validation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
