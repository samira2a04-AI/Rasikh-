import type { ReviewResponse } from "../../api/types";
import { StatusIndicator } from "../../components/StatusIndicator";

/**
 * Renders the result of a review workflow run (access decision, findings,
 * obligations, escalations) for the information the backend returns. Reused
 * by the Reviews workspace and the request detail "Review" section so review
 * results are rendered consistently.
 */
export function ReviewResults({ review }: { review: ReviewResponse }) {
  return (
    <div style={{ display: "grid", gap: "16px" }}>
      <div>
        <p className="eyebrow">Access decision</p>
        <StatusIndicator status={review.access_decision} />
      </div>

      <div>
        <p className="eyebrow">Findings ({review.findings.length})</p>
        {review.findings.length === 0 ? (
          <p className="auth-subtitle">No findings were produced.</p>
        ) : (
          review.findings.map((finding) => (
            <div
              key={finding.finding_id}
              style={{
                padding: "12px 0",
                borderBottom: "1px solid rgba(0,0,0,0.08)",
              }}
            >
              <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                <StatusIndicator status={finding.grounded ? "authorized" : "rejected"} />
                {finding.risk_rating && (
                  <span className="role-badge role-badge--member">
                    {finding.risk_rating}
                  </span>
                )}
                {finding.checklist_area && (
                  <span className="role-badge role-badge--member">
                    {finding.checklist_area.replaceAll("_", " ")}
                  </span>
                )}
                {finding.tricky_case_type && (
                  <span className="role-badge role-badge--member">
                    {finding.tricky_case_type.replaceAll("_", " ")}
                  </span>
                )}
              </div>
              <p style={{ marginTop: "8px" }}>{finding.statement}</p>
              {finding.citations.length > 0 && (
                <p className="auth-subtitle">
                  Citations: {finding.citations.length} source clause(s)
                </p>
              )}
            </div>
          ))
        )}
      </div>

      <div>
        <p className="eyebrow">Obligations ({review.obligations.length})</p>
        {review.obligations.length === 0 ? (
          <p className="auth-subtitle">No obligations surfaced by this review.</p>
        ) : (
          review.obligations.map((ob) => (
            <div
              key={ob.obligation_id}
              style={{
                padding: "8px 0",
                borderBottom: "1px solid rgba(0,0,0,0.08)",
              }}
            >
              {ob.obligation_id} — band {ob.stored_band}
              <span className="auth-subtitle">
                {" "}
                (org {ob.org_id}, due {ob.due_date})
              </span>
            </div>
          ))
        )}
      </div>

      <div>
        <p className="eyebrow">Escalations ({review.escalations.length})</p>
        {review.escalations.length === 0 ? (
          <p className="auth-subtitle">No escalations from this review.</p>
        ) : (
          review.escalations.map((esc) => (
            <div
              key={esc.escalation_id}
              style={{
                padding: "8px 0",
                borderBottom: "1px solid rgba(0,0,0,0.08)",
              }}
            >
              {esc.reason}
              <span className="auth-subtitle"> routed to {esc.routed_to_id}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
