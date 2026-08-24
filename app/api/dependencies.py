"""Translate service-level exceptions into HTTP responses.

The workflow orchestrator raises two flavours of error at the HTTP boundary:

* :class:`~app.services.workflow.WorkflowAccessDenied` — propagated unwrapped
  (it carries an already-recorded unauthorized ``AccessDecision``).
* :class:`~app.services.workflow.WorkflowStageError` — a wrapper that preserves
  the original service exception as ``__cause__`` so we can map it precisely.

This module inspects ``__cause__`` (when present) to turn each domain failure
into the status code the specification implies, without inventing policies.
String matching is only used on the *deterministic* messages emitted by the
already-locked service code (approval state machine messages), never on free
text.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.services.access_control import AccessControlInputError
from app.services.approval import ApprovalWorkflowError
from app.services.document_retrieval import DocumentAccessDenied
from app.services.drafting import DraftingError
from app.services.request_intake import RequestIntakeError
from app.services.review import ReviewPersistenceError
from app.services.workflow import WorkflowAccessDenied, WorkflowStageError


def _cause(exc: Exception) -> Exception:
    """Return the underlying service exception (unwraps WorkflowStageError)."""
    if isinstance(exc, WorkflowStageError):
        return exc.__cause__ or exc
    return exc


def _http_for_intake(msg: str) -> int:
    # "unsupported request_type ..." -> 400 (validation)
    # "unknown requester_id / unknown org_id / unknown request_id ..." -> 404
    if "unsupported request_type" in msg:
        return 400
    return 404


def _http_for_approval(msg: str) -> int:
    # The approval service emits a small, fixed vocabulary of messages:
    if "unknown draft_id" in msg:
        return 404
    if "unknown reviewer_id" in msg:
        return 404
    if "does not have approval authority" in msg:
        return 403
    # stale version, terminal state, or "already carries an ApprovalDecision"
    return 409


def translate_error(exc: Exception) -> HTTPException:
    """Map a service exception (wrapped or direct) to an ``HTTPException``.

    The detail string is the service's own message — it is domain information
    (why the transition was rejected), not an internal stack trace, so it is
    safe to return to the caller. Unknown exception types fall through to 500.
    """
    cause = _cause(exc)
    detail = str(cause)

    if isinstance(cause, ApprovalWorkflowError):
        return HTTPException(status_code=_http_for_approval(detail), detail=detail)
    if isinstance(cause, RequestIntakeError):
        return HTTPException(status_code=_http_for_intake(detail), detail=detail)
    if isinstance(cause, AccessControlInputError):
        return HTTPException(status_code=404, detail=detail)
    if isinstance(cause, DocumentAccessDenied):
        return HTTPException(status_code=403, detail=detail)
    if isinstance(cause, ReviewPersistenceError):
        return HTTPException(status_code=400, detail=detail)
    if isinstance(cause, DraftingError):
        code = 404 if "unknown request_id" in detail else 400
        return HTTPException(status_code=code, detail=detail)
    return HTTPException(status_code=500, detail="internal workflow error")



def get_session() -> Generator[Session, None, None]:
    """Yield a fresh ``SessionLocal`` for the request, closing it afterwards.

    Closing an uncommitted session rolls back any pending transaction, so this
    is itself a safety net for routes that raised without committing.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def transactional(session: Session) -> Generator[None, None, None]:
    """Run a mutating service call with explicit commit/rollback semantics.

    - success: the caller commits inside the ``with`` block before returning.
    - :class:`WorkflowAccessDenied`: commit the recorded denied AccessDecision
      (SEC-006) and surface ``403 Forbidden``.
    - any other exception: roll back the session and translate the service
      error into the appropriate HTTP response.
    """
    try:
        yield
    except WorkflowAccessDenied as exc:
        # The unauthorized AccessDecision is already in the session; persist it
        # so denied attempts remain auditable (SEC-006), then surface 403.
        session.commit()
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        # e.g. a foreign-key violation from referencing a non-existent
        # request/member/org at a service boundary that does not pre-check.
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail="request references a non-existent entity",
        ) from exc
    except WorkflowStageError as exc:
        # The orchestrator wraps lower-level service errors, preserving the
        # original exception as ``__cause__`` for translation.
        session.rollback()
        raise translate_error(exc) from exc
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # safety net for anything unexpected
        session.rollback()
        raise translate_error(exc)

