"""Rulebook-driven contract review (FR-010–FR-013, FR-021, FR-022; GRD-001–GRD-007).

Deterministic evaluation of ALREADY-RETRIEVED contract clauses against the
firm's Review Standard. This is not an AI layer: every rule below implements,
verbatim in intent, what the seeded ReviewStandardClause rows define:

- 1.1 term/renewal: distinguish fixed expiry from auto-renewal; report the
  notice window. The two are different findings (FR-021 pair #1).
- 1.2 liability: distinguish capped from uncapped; flag any carve-out that
  makes an otherwise-capped position unlimited (FR-021 pairs #2/#3).
- 1.3 payment: report late-payment charges; interest/penalty are Section 4
  Sharia-sensitive constructs.
- 1.4 termination: report termination rights (report-only here).
- 1.5 governing law: report the stated law/forum (report-only here).
- 1.7/1.8 missing essentials: a missing term, governing-law clause, liability
  position, or signature block is reported as missing — never assumed — using
  the rulebook 0.1 "not addressed in the documents" wording.
- 3.1/3.2/3.3 risk taxonomy: labels (high/medium/low) and numeric thresholds
  (30-day notice window, >60-day payment terms) are DERIVED from the supplied
  standard-clause text at runtime — never hard-coded (docs/data-schema.md §9).
- 4.1/4.3/4.4 Sharia: interest and penalties are flagged for scholar review
  with the clause cited; never ruled on.

SECURITY BOUNDARY: operates only on clause instances supplied by the caller
(i.e. produced by the authorised retrieval layer). It never queries contract,
data-room, or standard-clause tables, never touches MatterAssignment or
AccessDecision, and never reads Request.raw_content for decisions.

SOURCE FACT vs RULEBOOK ASSESSMENT: each finding's statement reports what the
contract clause says (fact) and what the rulebook requires (assessment), and
cites BOTH the contract clause and the supplied rulebook clauses it applied.
Nothing is cited that was not supplied.

All persistence goes through app.services.review.create_grounded_finding /
create_ungrounded_finding, so grounding, citation, atomicity, and audit
(`finding_produced`) guarantees are inherited unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import ContractClause, Request, ReviewStandardClause
from app.services.review import (
    create_grounded_finding,
    create_ungrounded_finding,
)

# ---------------------------------------------------------------------------
# Risk framework derived from the supplied rulebook clauses (3.1–3.3)
# ---------------------------------------------------------------------------

_RISK_TITLE_PREFIXES = (
    ("high risk", "high"),
    ("medium risk", "medium"),
    ("low risk", "low"),
)


@dataclass
class RiskFramework:
    """Labels and thresholds extracted from supplied rulebook clauses 3.1–3.3."""

    labels: dict[str, str] = field(default_factory=dict)
    high_notice_window_days: int | None = None  # 3.1: "within N days"
    long_payment_days: int | None = None        # 3.2: "longer than N days"


def derive_risk_framework(standard_clauses: list[ReviewStandardClause]) -> RiskFramework:
    """Derive risk labels/thresholds from the supplied rulebook text.

    Nothing about the taxonomy is hard-coded: the labels come from the clause
    titles ("High risk." / "Medium risk." / "Low risk.") and the numeric
    thresholds from the clause bodies. Missing pieces simply stay absent and
    the affected ratings are omitted downstream (rulebook 3.4: never rate
    without the rule behind it).
    """
    framework = RiskFramework()
    for clause in standard_clauses:
        number = clause.clause_number
        title = clause.text.split("\n", 1)[0].strip().lower()
        for prefix, label in _RISK_TITLE_PREFIXES:
            if title.startswith(prefix):
                framework.labels[label] = label
        if number == "3.1":
            m = re.search(r"within (\d+) days", clause.text, flags=re.IGNORECASE)
            if m:
                framework.high_notice_window_days = int(m.group(1))
        elif number == "3.2":
            m = re.search(r"longer than (\d+) days", clause.text, flags=re.IGNORECASE)
            if m:
                framework.long_payment_days = int(m.group(1))
    return framework


# ---------------------------------------------------------------------------
# Detection helpers (deterministic, negation-aware)
# ---------------------------------------------------------------------------

# Detection is case-insensitive: contracts use capitals for emphasis
# ("EXCEPT", "UNLIMITED") and sentence-initial capitalisation.
_AUTO_RENEW_RE = re.compile(r"renew\w*\s+automatically|automatically\s+renew|تتجدد تلقائياً", re.IGNORECASE)
_NOT_AUTO_RENEW_RE = re.compile(r"does not renew automatically|not renew automatically", re.IGNORECASE)
_EXPIRY_RE = re.compile(r"\bexpir\w+|\bfixed term\b|لمدة سنة واحدة|لمدة", re.IGNORECASE)
# "(90) days" style parenthesised numerals must match too.
_NOTICE_DAYS_RE = re.compile(r"(\d+)\)?\s*days|(\d+)\)?\s*يوماً", re.IGNORECASE)
_UNCAPPED_RE = re.compile(r"without limit|unlimited|بدون حد|غير محدودة", re.IGNORECASE)
_CAPPED_RE = re.compile(r"\bcapped\b|يقتصر مسؤولية", re.IGNORECASE)
_EXCEPT_RE = re.compile(r"\bexcept\b|carve-out|إلا أن", re.IGNORECASE)
_INTEREST_RE = re.compile(r"\binterest\b|فائدة", re.IGNORECASE)
_NO_INTEREST_RE = re.compile(r"no\s+interest", re.IGNORECASE)
_PENALTY_RE = re.compile(r"penalt|غرامة", re.IGNORECASE)
_GOVERNING_LAW_RE = re.compile(r"governing law|القانون الواجب التطبيق", re.IGNORECASE)
_SIGNATURE_RE = re.compile(r"signatur|تواقيع", re.IGNORECASE)
_TERMINATION_RE = re.compile(r"terminat|إنهاء", re.IGNORECASE)
_DURATION_RE = re.compile(r"\byears?\b|\bmonths?\b|مدة|لمدة", re.IGNORECASE)


def _first_match(text: str, pattern: re.Pattern[str]) -> int | None:
    m = pattern.search(text)
    if m is None:
        return None
    return int(next(g for g in m.groups() if g))


def _snippet(text: str, limit: int = 90) -> str:
    clean = " ".join(text.split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


# ---------------------------------------------------------------------------
# Internal finding specifications
# ---------------------------------------------------------------------------

@dataclass
class _Spec:
    area: str
    statement: str
    citations: list[ContractClause | ReviewStandardClause]
    grounded: bool
    tricky_case_type: str | None = None
    risk_rating: str | None = None
    sharia_sensitive_flag: bool = False


def _review_term(clause: ContractClause, fw: RiskFramework) -> _Spec | None:
    text = clause.text
    lowered = text.lower()
    is_auto = bool(_AUTO_RENEW_RE.search(text)) and not _NOT_AUTO_RENEW_RE.search(lowered)
    is_fixed = bool(_EXPIRY_RE.search(text)) and not is_auto

    if is_auto:
        notice_days = _first_match(text, _NOTICE_DAYS_RE)
        high_t = fw.high_notice_window_days
        if notice_days is not None and high_t is not None and "high" in fw.labels:
            risk = fw.labels["high"] if notice_days <= high_t else fw.labels.get("medium")
            risk_rule = "3.1" if notice_days <= high_t else "3.2"
        else:
            risk, risk_rule = None, None
        window_txt = f"{notice_days} days" if notice_days is not None else "an unstated window"
        threshold_txt = (
            f" A notice window of {notice_days} days is "
            f"{'at or within' if notice_days <= high_t else 'beyond'} the "
            f"{high_t}-day high-risk threshold."
            if notice_days is not None and high_t is not None
            else ""
        )
        statement = (
            f"SOURCE FACT: the contract renews automatically unless written "
            f"non-renewal notice is given {window_txt} before the end of the "
            f"then-current term ({_snippet(text)}). "
            f"RULEBOOK ASSESSMENT: clause 1.1 requires distinguishing "
            f"auto-renewal from fixed expiry and reporting the notice window."
            f"{threshold_txt}"
        )
        citations: list[ContractClause | ReviewStandardClause] = [clause]
        return _Spec(
            area="term_renewal",
            statement=statement,
            citations=citations,
            grounded=True,
            tricky_case_type="auto_renewal",
            risk_rating=risk,
        )

    if is_fixed:
        risk = fw.labels.get("low")
        statement = (
            f"SOURCE FACT: the contract runs for a fixed term that simply "
            f"expires ({_snippet(text)}). "
            f"RULEBOOK ASSESSMENT: clause 1.1 — a fixed-term expiry is a "
            f"different finding from auto-renewal; clause 3.3 — a fixed term "
            f"with clear expiry is low risk."
        )
        return _Spec(
            area="term_renewal",
            statement=statement,
            citations=[clause],
            grounded=True,
            tricky_case_type="fixed_expiry",
            risk_rating=risk,
        )
    return None


def _review_liability(clause: ContractClause, fw: RiskFramework) -> _Spec | None:
    text = clause.text
    uncapped = bool(_UNCAPPED_RE.search(text))
    capped = bool(_CAPPED_RE.search(text))
    has_except = bool(_EXCEPT_RE.search(text))

    if capped and has_except and uncapped:
        return _Spec(
            area="liability",
            statement=(
                f"SOURCE FACT: liability is stated as capped, but a carve-out "
                f"makes specified positions unlimited ({_snippet(text)}). "
                f"RULEBOOK ASSESSMENT: clause 1.2 — flag any carve-out that "
                f"makes an otherwise-capped position unlimited; clause 3.1 — "
                f"rated high risk. Reported as uncapped, not capped (FR-021)."
            ),
            citations=[clause],
            grounded=True,
            tricky_case_type="capped_with_uncapped_carveout",
            risk_rating=fw.labels.get("high"),
        )
    if uncapped:
        return _Spec(
            area="liability",
            statement=(
                f"SOURCE FACT: liability is uncapped/unlimited "
                f"({_snippet(text)}). "
                f"RULEBOOK ASSESSMENT: clause 1.2 — distinguish uncapped from "
                f"capped liability; clause 3.1 — uncapped or unlimited "
                f"liability is high risk."
            ),
            citations=[clause],
            grounded=True,
            tricky_case_type="uncapped_liability",
            risk_rating=fw.labels.get("high"),
        )
    if capped:
        at_contract_value = "contract value" in text.lower()
        risk = fw.labels.get("low") if at_contract_value else None
        relation = (
            "at the contract value" if at_contract_value else "without a stated relation to the contract value"
        )
        return _Spec(
            area="liability",
            statement=(
                f"SOURCE FACT: liability is capped {relation} "
                f"({_snippet(text)}). "
                f"RULEBOOK ASSESSMENT: clause 1.2 — report the ceiling and "
                f"what it covers"
                + (
                    "; clause 3.3 — capped at or below contract value is low risk."
                    if at_contract_value and risk is not None
                    else "."
                )
            ),
            citations=[clause],
            grounded=True,
            tricky_case_type="capped_liability",
            risk_rating=risk,
        )
    return None


def _review_payment(clause: ContractClause, fw: RiskFramework) -> _Spec | None:
    text = clause.text
    interest = bool(_INTEREST_RE.search(text)) and not _NO_INTEREST_RE.search(text.lower())
    penalty = bool(_PENALTY_RE.search(text))
    if not (interest or penalty):
        return None

    constructs = []
    if interest:
        constructs.append("interest (rulebook 4.1, riba-sensitive)")
    if penalty:
        constructs.append("a late-payment penalty (rulebook 4.3)")
    statement = (
        f"SOURCE FACT: the payment terms include {' and '.join(constructs)} "
        f"({_snippet(text)}). "
        f"RULEBOOK ASSESSMENT: clause 1.3 — report any late-payment charge; "
        f"section 4 classifies this as Sharia-sensitive — flagged FOR SCHOLAR "
        f"REVIEW with the clause cited; no ruling on permissibility is given "
        f"(clause 4.4)."
    )
    return _Spec(
        area="payment",
        statement=statement,
        citations=[clause],
        grounded=True,
        sharia_sensitive_flag=True,
    )


def _review_governing_law_present(clause: ContractClause) -> _Spec:
    return _Spec(
        area="governing_law",
        statement=(
            f"SOURCE FACT: governing law and dispute forum are stated "
            f"({_snippet(clause.text)}). "
            f"RULEBOOK ASSESSMENT: clause 1.5 — report the stated law and "
            f"forum; do not opine on enforceability."
        ),
        citations=[clause],
        grounded=True,
    )


def _review_termination(clause: ContractClause) -> _Spec:
    return _Spec(
        area="termination",
        statement=(
            f"SOURCE FACT: termination rights are stated "
            f"({_snippet(clause.text)}). "
            f"RULEBOOK ASSESSMENT: clause 1.4 — report each party's "
            f"termination rights, the notice required, and any fee."
        ),
        citations=[clause],
        grounded=True,
    )


def _gap_spec(missing: str, rulebook_ref: str) -> _Spec:
    return _Spec(
        area="gap",
        statement=(
            f"SOURCE FACT: no {missing} appears in the supplied contract "
            f"clauses. "
            f"RULEBOOK ASSESSMENT: clause 1.7 — a missing essential is "
            f"reported as missing, never assumed; clause 1.8 — reported as "
            f"not addressed in this contract ({rulebook_ref}). "
            f"This is not addressed in the documents provided."
        ),
        citations=[],
        grounded=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review_contract(
    session: Session,
    *,
    request_id: str,
    contract_clauses: list[ContractClause],
    standard_clauses: list[ReviewStandardClause],
) -> list:
    """Review supplied contract clauses against supplied rulebook clauses.

    Both lists MUST come from the authorised retrieval layer. Produces
    grounded Findings (with contract-clause and rulebook citations) and, for
    missing essentials per rulebook 1.7/1.8, ungrounded gap Findings carrying
    the required wording. Returns the created Finding objects (persisted via
    app.services.review inside the caller's transaction).
    """
    if session.get(Request, request_id) is None:
        raise ValueError(f"unknown request_id {request_id!r}")

    framework = derive_risk_framework(standard_clauses)
    supplied_std = {c.clause_number: c for c in standard_clauses}

    def std(*numbers: str) -> list[ReviewStandardClause]:
        return [supplied_std[n] for n in numbers if n in supplied_std]

    specs: list[_Spec] = []
    seen_areas: dict[str, list[ContractClause]] = {
        "term_renewal": [],
        "liability": [],
        "governing_law": [],
        "termination": [],
    }
    duration_seen = False

    # Only labelled clauses are provisions; NULL-label rows are the verbatim
    # gap annotations (e.g. "[No signature block is included.]") and must
    # never count as evidence that a provision exists.
    labelled = [c for c in contract_clauses if c.clause_label is not None]

    for clause in labelled:
        text = clause.text
        if _DURATION_RE.search(text):
            duration_seen = True
        spec = _review_term(clause, framework)
        if spec is not None:
            specs.append(spec)
            seen_areas["term_renewal"].append(clause)

        spec = _review_liability(clause, framework)
        if spec is not None:
            specs.append(spec)
            seen_areas["liability"].append(clause)

        spec = _review_payment(clause, framework)
        if spec is not None:
            specs.append(spec)

        if _GOVERNING_LAW_RE.search(text):
            specs.append(_review_governing_law_present(clause))
            seen_areas["governing_law"].append(clause)

        if _TERMINATION_RE.search(text):
            specs.append(_review_termination(clause))
            seen_areas["termination"].append(clause)

    # Rulebook 1.7: missing essentials reported as gaps (1.8 wording). A bare
    # duration statement satisfies "term present" even where 1.1's expiry vs
    # auto-renewal distinction does not apply to the supplied wording.
    if not seen_areas["term_renewal"] and not duration_seen:
        specs.append(_gap_spec("term or renewal provision", "rulebook 1.1"))
    if not seen_areas["liability"]:
        specs.append(_gap_spec("liability position", "rulebook 1.2"))
    if not seen_areas["governing_law"]:
        specs.append(_gap_spec("governing-law clause", "rulebook 1.5"))
    if not any(_SIGNATURE_RE.search(c.text) for c in labelled):
        specs.append(_gap_spec("signature block", "rulebook 1.7"))

    findings = []
    for spec in specs:
        citations: list[ContractClause | ReviewStandardClause] = list(spec.citations)
        if spec.grounded:
            # Attach the rulebook clauses this assessment relied on — only
            # ones actually supplied (never fabricated).
            rule_refs: list[str] = []
            if spec.area == "term_renewal":
                rule_refs.append("1.1")
                if spec.risk_rating == framework.labels.get("high"):
                    rule_refs.append("3.1")
                elif spec.risk_rating == framework.labels.get("medium"):
                    rule_refs.append("3.2")
                elif spec.risk_rating == framework.labels.get("low"):
                    rule_refs.append("3.3")
            elif spec.area == "liability":
                rule_refs.append("1.2")
                if spec.tricky_case_type in ("uncapped_liability", "capped_with_uncapped_carveout"):
                    rule_refs.append("3.1")
                elif spec.risk_rating == framework.labels.get("low"):
                    rule_refs.append("3.3")
            elif spec.area == "payment":
                rule_refs.append("1.3")
                if "interest" in spec.statement:
                    rule_refs.append("4.1")
                if "penalty" in spec.statement:
                    rule_refs.append("4.3")
                rule_refs.append("4.4")
            elif spec.area == "governing_law":
                rule_refs.append("1.5")
            elif spec.area == "termination":
                rule_refs.append("1.4")

            citations.extend(std(*rule_refs))
            findings.append(
                create_grounded_finding(
                    session,
                    request_id=request_id,
                    statement=spec.statement,
                    citations=citations,
                    checklist_area=spec.area,
                    risk_rating=spec.risk_rating,
                    sharia_sensitive_flag=spec.sharia_sensitive_flag,
                    tricky_case_type=spec.tricky_case_type,
                )
            )
        else:
            findings.append(
                create_ungrounded_finding(
                    session,
                    request_id=request_id,
                    statement=spec.statement,
                    checklist_area=spec.area,
                )
            )
    return findings