"""Access-control service — the sole authority for matter-access decisions.

Deterministic application logic (SEC-001, SEC-003, SEC-005, Rule 1, Rule 2):
the decision is derived ONLY from

1. the existence of the ``TeamMember``,
2. the existence of the ``Organisation``,
3. a ``MatterAssignment`` row for ``(member_id, org_id)`` — which includes the
   materialised firm-wide partners (L-01/L-02/L-03 × every organisation).

Request text (``Request.raw_content``), document contents, and AI output are
never inputs: this module's functions do not even accept them as parameters,
and no document table is ever queried here. The schema stores the facts; this
service implements the gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessDecision, MatterAssignment, Organisation, TeamMember

# Basis labels recorded on AccessDecision rows. They always reference the
# assignment/access records — never request content (docs/data-schema.md §3).
BASIS_ASSIGNED = "matter_assignment"
BASIS_NO_ASSIGNMENT = "no_matter_assignment"
BASIS_UNKNOWN_MEMBER = "unknown_member"
BASIS_UNKNOWN_ORGANISATION = "unknown_organisation"


@dataclass(frozen=True)
class AccessCheckResult:
    """Structured outcome of an access check.

    Mirrors the fields of an ``access_decision`` row except for the request
    linkage and timestamp; ``basis`` identifies which access rule produced
    the outcome.
    """

    authorized: bool
    member_id: str
    org_id: str
    basis: str


def check_access(session: Session, member_id: str, org_id: str) -> AccessCheckResult:
    """Decide whether ``member_id`` is authorized to access ``org_id``.

    Only identifiers are accepted — never request text or document content.
    An unknown member or organisation yields an unauthorized result with an
    explicit basis; it can never silently become authorized.
    """
    if session.get(TeamMember, member_id) is None:
        return AccessCheckResult(
            authorized=False, member_id=member_id, org_id=org_id, basis=BASIS_UNKNOWN_MEMBER
        )

    if session.get(Organisation, org_id) is None:
        return AccessCheckResult(
            authorized=False,
            member_id=member_id,
            org_id=org_id,
            basis=BASIS_UNKNOWN_ORGANISATION,
        )

    assigned = (
        session.execute(
            select(MatterAssignment.assignment_id)
            .where(
                MatterAssignment.member_id == member_id,
                MatterAssignment.org_id == org_id,
            )
            .limit(1)
        ).first()
        is not None
    )

    if assigned:
        return AccessCheckResult(
            authorized=True, member_id=member_id, org_id=org_id, basis=BASIS_ASSIGNED
        )
    return AccessCheckResult(
        authorized=False, member_id=member_id, org_id=org_id, basis=BASIS_NO_ASSIGNMENT
    )


class AccessControlInputError(ValueError):
    """Raised when an AccessDecision cannot be recorded because the member or
    organisation does not exist.

    Such a row would violate its foreign keys, so recording it is impossible;
    failing loudly here keeps invalid attempts from disappearing silently.
    """


def record_access_decision(
    session: Session,
    request_id: str,
    member_id: str,
    org_id: str,
) -> AccessDecision:
    """Run :func:`check_access` and append one ``AccessDecision`` row.

    Stores request_id, member_id, org_id, outcome, basis; ``decided_at`` uses
    the column's server-side ``now()`` default. The row is added to
    ``session`` but NOT committed — the caller owns the transaction.

    This function never retrieves documents (SEC-002): it touches only
    team_member, organisation, matter_assignment, and access_decision. The
    ``request_id`` is stored as given; its validity is enforced by the
    database foreign key at flush time (the Request row itself is deliberately
    not loaded, so request content is never even fetched).
    """
    result = check_access(session, member_id=member_id, org_id=org_id)

    if result.basis == BASIS_UNKNOWN_MEMBER:
        raise AccessControlInputError(f"unknown member_id {member_id!r}")
    if result.basis == BASIS_UNKNOWN_ORGANISATION:
        raise AccessControlInputError(f"unknown org_id {org_id!r}")

    decision = AccessDecision(
        request_id=request_id,
        member_id=member_id,
        org_id=org_id,
        outcome="authorized" if result.authorized else "unauthorized",
        basis=result.basis,
    )
    session.add(decision)
    return decision