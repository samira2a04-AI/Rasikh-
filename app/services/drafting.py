"""Draft persistence boundary (FR-028, APR-001–APR-003; docs/data-schema.md §8).

NOT an LLM and not a legal-reasoning component: this service persists draft
text that a caller (the later drafting engine) already produced. It enforces
the schema's draft lifecycle mechanics deterministically:

- The FIRST draft for a request gets ``version = 1``; every subsequent draft
  for the same request gets ``version = previous_max + 1``
  (docs/data-schema.md §8: "Starts at 1; increments on edit").
- Every new draft begins in ``approval_state = 'awaiting_approval'``
  (APR-002). Nothing here approves, rejects, or edits states — the approval
  workflow is a later phase.
- Drafts are APPEND-ONLY history: a new version inserts a new row and never
  modifies an existing one, so prior versions stay byte-identical
  (docs/data-schema.md §8: full edit history preserved via version rows).
- Content is stored EXACTLY as supplied — no whitespace normalisation, no
  rewriting of Arabic, no punctuation changes.

Version concurrency: the specification does not define concurrent-drafter
behaviour. The next version is computed inside the caller's transaction as
``MAX(version) + 1`` scoped to the request (deterministic, single-writer
assumption consistent with every other service in this project). Callers
serialising drafts per request get gap-free versions.

Audit (docs/data-schema.md §5 lists exactly these types): ``draft_created``
for version 1, ``draft_edited`` for subsequent versions. Events carry minimal
metadata (version number only) — never draft content. Actor is NULL (system
action). No other event types are invented.

Security boundary: touches only ``request`` (existence check) and ``draft``.
No MatterAssignment, AccessDecision, contract, clause, data-room, finding,
citation, or authorisation logic; no LLM/network/fuzzy matching. The caller
owns the transaction; Draft + AuditEvent are added together so any failure
rolls back atomically with no partial rows.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Draft, Request

EVENT_DRAFT_CREATED = "draft_created"
EVENT_DRAFT_EDITED = "draft_edited"

STATUS_AWAITING_APPROVAL = "awaiting_approval"


class DraftingError(ValueError):
    """Raised when a draft cannot be persisted as requested."""


def _require_request(session: Session, request_id: str) -> None:
    # Existence check selects ONLY the identifier column — the Request row's
    # content (raw_content) is deliberately never fetched by this service.
    exists = (
        session.execute(
            select(Request.request_id)
            .where(Request.request_id == request_id)
            .limit(1)
        ).first()
        is not None
    )
    if not exists:
        raise DraftingError(f"unknown request_id {request_id!r}")


def _validate_content(content: str) -> None:
    if not isinstance(content, str):
        raise DraftingError("draft content must be a string")
    if not content.strip():
        # Validation only — the stored value keeps the original bytes.
        raise DraftingError("draft content must not be empty")


def _next_version(session: Session, request_id: str) -> int:
    current_max = session.execute(
        select(func.max(Draft.version)).where(Draft.request_id == request_id)
    ).scalar_one()
    return (current_max or 0) + 1


def create_draft(
    session: Session,
    *,
    request_id: str,
    content: str,
    created_at: datetime | None = None,
) -> Draft:
    """Persist a caller-produced draft as the request's next version.

    - Version 1 for the request's first draft; otherwise ``max(version)+1``
      (request-scoped, append-only — existing versions are never touched).
    - ``approval_state`` always starts at ``awaiting_approval``.
    - ``content`` is stored exactly as supplied.
    - Appends the append-only ``draft_created`` (first version) or
      ``draft_edited`` (later versions) AuditEvent with version metadata only.
    - ``created_at``/``updated_at`` default to the columns' server-side
      ``now()``; callers may pass an explicit timezone-aware datetime for
      deterministic seeding.

    The rows are added to ``session`` but NOT committed — the caller owns the
    transaction, so a failure rolls back draft and audit event together.
    """
    _require_request(session, request_id)
    _validate_content(content)

    version = _next_version(session, request_id)
    event_type = EVENT_DRAFT_CREATED if version == 1 else EVENT_DRAFT_EDITED

    draft = Draft(
        request_id=request_id,
        content=content,
        version=version,
        approval_state=STATUS_AWAITING_APPROVAL,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(draft)
    session.flush()  # assign the PK for the audit reference

    session.add(
        AuditEvent(
            request_id=request_id,
            event_type=event_type,
            actor_id=None,  # system action (the drafting engine)
            detail_reference=f"draft:{draft.draft_id}",
            detail_json={"version": version},
        )
    )
    session.flush()  # surface any violation immediately; atomic with the draft
    return draft