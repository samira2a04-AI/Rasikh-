import { Link } from "react-router-dom";

/**
 * Contextual navigation for request-specific child pages (Review Workspace,
 * Drafts, Approvals, Obligations, Audit). Always offers a way back to the
 * Unified Request Workspace while showing which request the user is in.
 */
export function RequestContextBar({
  requestId,
  note,
}: {
  requestId: string;
  /** Optional scope clarification, e.g. organization-scoped obligations. */
  note?: string;
}) {
  return (
    <div className="ctx-bar">
      <Link className="text-link ctx-back" to={`/requests/${encodeURIComponent(requestId)}`}>
        ← Request Workspace
      </Link>
      <span className="ctx-request">
        Request <code>{requestId}</code>
      </span>
      {note && <span className="ctx-note">{note}</span>}
    </div>
  );
}