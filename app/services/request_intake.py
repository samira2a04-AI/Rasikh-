"""Request intake and classification services (FR-001, FR-002, AI-001).

Intake owns request creation ONLY: it captures requester identity, the
organisation/matter reference when structurally known, and the raw request
text verbatim. It never reads matter documents and never decides
authorization.

Classification reads request metadata only and sets ``request_type``. It is a
plain, deterministic lookup/assignment step — no LLM, no heuristics, no
document access.

Neither component decides whether the requester is authorized: that remains
the sole responsibility of :mod:`app.services.access_control`. The pipeline
stays strictly sequenced:

    Intake -> Classification -> AccessControl -> DocumentRetrieval

Lifecycle transitions follow docs/system-architecture.md §4:
``intake`` -> ``classified``.

Audit follows docs/data-schema.md §5, which names both required event types:
``intake`` (request creation) and ``classified`` (classification). Both are
append-only AuditEvent rows; the caller owns the transaction, matching the
access-control and document-retrieval service patterns.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AuditEvent, Organisation, Request, TeamMember

STATUS_INTAKE = "intake"
STATUS_CLASSIFIED = "classified"

EVENT_INTAKE = "intake"
EVENT_CLASSIFIED = "classified"

# The classification vocabulary defined by FR-002 and docs/data-schema.md §3
# (request.request_type: "contract_review / consultation / meeting_prep /
# obligation_check (set by Classification)"). The two seeded data_room_access
# rows are historical input typings from the source files — the PRD never
# lists data-room access as a classification output, and the column
# deliberately carries no CHECK constraint, so those rows remain untouched.
CLASSIFIABLE_REQUEST_TYPES = frozenset(
    {"contract_review", "consultation", "meeting_prep", "obligation_check"}
)


class RequestIntakeError(ValueError):
    """Raised when intake or classification receives invalid input.

    Failures happen before any row is added (or leave the session clean for
    the caller's rollback), so no partial database state can remain.
    """


def submit_request(
    session: Session,
    *,
    request_id: str,
    requester_id: str,
    raw_content: str,
    org_id: str | None = None,
    created_at: datetime | None = None,
) -> Request:
    """Record an incoming request at the ``intake`` stage (FR-001).

    - ``requester_id`` must reference an existing TeamMember.
    - ``org_id``, when provided, must reference an existing Organisation;
      it comes from structured request information, never from guessing.
    - ``raw_content`` is stored exactly as received and is used for nothing
      here — certainly not for any authorization decision.
    - ``request_type`` starts as NULL; classification sets it next.
    - ``status`` starts at ``intake``.
    - ``created_at`` defaults to the column's server-side ``now()``; callers
      may pass an explicit timezone-aware datetime for deterministic seeding.

    Appends the append-only ``intake`` AuditEvent. The row is added to
    ``session`` but NOT committed — the caller owns the transaction.
    """
    if session.get(TeamMember, requester_id) is None:
        raise RequestIntakeError(f"unknown requester_id {requester_id!r}")
    if org_id is not None and session.get(Organisation, org_id) is None:
        raise RequestIntakeError(f"unknown org_id {org_id!r}")

    request = Request(
        request_id=request_id,
        requester_id=requester_id,
        org_id=org_id,
        request_type=None,
        raw_content=raw_content,
        status=STATUS_INTAKE,
        created_at=created_at,
    )
    session.add(request)
    session.add(
        AuditEvent(
            request_id=request_id,
            event_type=EVENT_INTAKE,
            actor_id=requester_id,
            detail_reference=f"request:{request_id}",
            detail_json={"org_id": org_id} if org_id is not None else None,
        )
    )
    return request


def classify_request(
    session: Session,
    *,
    request_id: str,
    request_type: str,
) -> Request:
    """Assign the request type and move ``intake`` -> ``classified`` (FR-002).

    Deterministic validation only: ``request_type`` must be one of the four
    types the specification defines for Classification, and the request must
    currently be in the ``intake`` state. Reads request metadata only — never
    documents, never assignment records, never authorization outcomes.

    Appends the append-only ``classified`` AuditEvent (actor NULL: the
    classification is performed by the system, not by a firm member). The
    caller owns the transaction.
    """
    if request_type not in CLASSIFIABLE_REQUEST_TYPES:
        raise RequestIntakeError(
            f"unsupported request_type {request_type!r}; expected one of "
            f"{sorted(CLASSIFIABLE_REQUEST_TYPES)}"
        )

    # Make a just-submitted (pending, uncommitted) request visible to the
    # lookup below so intake -> classification works within one caller
    # transaction. Flush emits SQL only inside the caller's transaction.
    session.flush()

    request = session.get(Request, request_id)
    if request is None:
        raise RequestIntakeError(f"unknown request_id {request_id!r}")
    if request.status not in (STATUS_INTAKE, "insufficient"):
        raise RequestIntakeError(
            f"request {request_id!r} has status {request.status!r}; "
            f"only {STATUS_INTAKE!r} or 'insufficient' requests can be classified"
        )

    request.request_type = request_type
    request.status = STATUS_CLASSIFIED

    session.add(
        AuditEvent(
            request_id=request_id,
            event_type=EVENT_CLASSIFIED,
            actor_id=None,
            detail_reference=f"request:{request_id}",
            detail_json={"request_type": request_type},
        )
    )
    return request