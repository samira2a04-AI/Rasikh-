import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { getReview, reviewFinding } from "../../api/reviews";
import { getRequest } from "../../api/requests";
import { listContracts } from "../../api/contracts";
import { listOrganisations } from "../../api/organisations";
import type {
    CitationResponse,
    FindingResponse,
    ReviewResponse,
} from "../../api/types";

/** Extracts a rulebook clause number (e.g. "1.2") from a finding statement. */
function clauseNumberOf(finding: FindingResponse): string | null {
    const match = finding.statement.match(/clause\s+(\d+\.\d+)/i);
    return match ? match[1] : null;
}

function isGrounded(finding: FindingResponse): boolean {
    return finding.grounded && finding.citations.length > 0;
}

function SummaryCard({
    label,
    value,
    accent,
}: {
    label: string;
    value: number;
    accent?: boolean;
}) {
    return (
        <div
            className={
                accent ? "crv-summary-card crv-summary-card--accent" : "crv-summary-card"
            }
        >
            <span className="crv-summary-value">{value}</span>
            <span className="crv-summary-label">{label}</span>
        </div>
    );
}

function RiskBadge({ rating }: { rating: string | null }) {
    const text = rating ?? "Unrated";
    const tone = text.toLowerCase().includes("high")
        ? "crv-risk crv-risk--high"
        : text.toLowerCase().includes("medium")
            ? "crv-risk crv-risk--medium"
            : "crv-risk crv-risk--low";
    return <span className={tone}>{text}</span>;
}

function CitationChips({ citations }: { citations: CitationResponse[] }) {
    return (
        <div className="crv-citations">
            <p className="crv-source-label">Source</p>
            <div className="crv-citation-list">
                {citations.map((c) => (
                    <span
                        key={c.citation_id}
                        className={
                            c.source_type === "contract_clause"
                                ? "crv-citation crv-citation--contract"
                                : "crv-citation crv-citation--standard"
                        }
                    >
                        {c.source_type === "contract_clause"
                            ? "Contract clause"
                            : "Rulebook clause"}
                        <code>{(c.contract_clause_id ?? c.standard_clause_id ?? "").slice(0, 8)}</code>
                    </span>
                ))}
            </div>
        </div>
    );
}

function FindingCard({
    finding,
    requestId,
}: {
    finding: FindingResponse;
    requestId: string;
}) {
    const queryClient = useQueryClient();
    const [isEditing, setIsEditing] = useState(false);
    const [notes, setNotes] = useState(finding.reviewer_notes ?? "");

    const reviewMutation = useMutation({
        mutationFn: (args: { status: string; reviewer_notes?: string }) =>
            reviewFinding(requestId, finding.finding_id, args),
        onSuccess: () => {
            setIsEditing(false);
            void queryClient.invalidateQueries({ queryKey: ["review", requestId] });
        },
    });

    const clause = clauseNumberOf(finding);
    const contractCitations = finding.citations.filter(
        (c) => c.source_type === "contract_clause",
    );
    const isReviewed = finding.status === "reviewed";
    const reviewerDisplayName = finding.reviewed_by_name ?? finding.reviewed_by ?? "Lawyer";

    return (
        <article className="crv-finding-card">
            <header className="crv-finding-head">
                {finding.grounded ? (
                    <span className="crv-grounded-badge">Grounded Finding</span>
                ) : (
                    <span className="crv-grounded-badge crv-grounded-badge--na">Not Addressed</span>
                )}
                <span
                    className={
                        isReviewed
                            ? "crv-status-pill crv-status-pill--reviewed"
                            : "crv-status-pill crv-status-pill--open"
                    }
                >
                    {isReviewed ? "✓ Reviewed" : "Open"}
                </span>
                {finding.risk_rating && <RiskBadge rating={finding.risk_rating} />}
            </header>
            {clause && <p className="crv-clause-ref">Clause {clause}</p>}
            <p className="crv-statement">{finding.statement}</p>
            {finding.citations.length > 0 && (
                <footer className="crv-finding-foot">
                    <CitationChips citations={finding.citations} />
                    {contractCitations.length > 0 && (
                        <p className="crv-contract-doc">
                            {contractCitations.length} contract clause
                            {contractCitations.length === 1 ? "" : "s"} cited as evidence
                        </p>
                    )}
                </footer>
            )}

            <div className="crv-review-panel">
                {isReviewed && !isEditing ? (
                    <div className="crv-review-confirmed">
                        <p className="crv-reviewer-name">
                            ✓ REVIEWED by {reviewerDisplayName}
                        </p>
                        {finding.reviewed_at && (
                            <p className="crv-reviewer-time">
                                {new Date(finding.reviewed_at).toLocaleString()}
                            </p>
                        )}
                        {finding.reviewer_notes && (
                            <p className="crv-reviewer-note">
                                Note: "{finding.reviewer_notes}"
                            </p>
                        )}
                    </div>
                ) : isEditing ? (
                    <div className="crv-note-field">
                        <label className="crv-note-label">Reviewer Note (optional)</label>
                        <textarea
                            className="crv-note-textarea"
                            placeholder="Optional note explaining review decision..."
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            rows={2}
                        />
                        <div className="crv-action-bar">
                            <button
                                type="button"
                                className="button button--primary"
                                disabled={reviewMutation.isPending}
                                onClick={() =>
                                    reviewMutation.mutate({
                                        status: "reviewed",
                                        reviewer_notes: notes.trim() || undefined,
                                    })
                                }
                            >
                                {reviewMutation.isPending ? "Saving…" : "Mark as Reviewed"}
                            </button>
                            <button
                                type="button"
                                className="button button--secondary"
                                onClick={() => setIsEditing(false)}
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                ) : (
                    <button
                        type="button"
                        className="button button--secondary"
                        onClick={() => setIsEditing(true)}
                    >
                        Mark as Reviewed
                    </button>
                )}
            </div>
        </article>
    );
}

function NotAddressedSection({
    findings,
    requestId,
}: {
    findings: FindingResponse[];
    requestId: string;
}) {
    const [open, setOpen] = useState(true);
    return (
        <section className="crv-section">
            <div className="crv-section-head">
                <h2>Not Addressed Findings</h2>
                <div style={{ display: "flex", gap: "var(--space-sm)", alignItems: "center" }}>
                    <span className="crv-count-chip">{findings.length}</span>
                    <button
                        type="button"
                        className="crv-collapse-toggle"
                        onClick={() => setOpen((o) => !o)}
                    >
                        {open ? "Collapse" : "Expand"}
                    </button>
                </div>
            </div>
            <p className="crv-not-addressed-summary">
                {findings.length} standard{findings.length === 1 ? " is" : "s are"} not
                addressed by this contract. Each ungrounded finding requires human legal review.
            </p>
            {open && (
                <div className="crv-finding-grid" style={{ marginTop: "var(--space-md)" }}>
                    {findings.map((f) => (
                        <FindingCard key={f.finding_id} finding={f} requestId={requestId} />
                    ))}
                </div>
            )}
        </section>
    );
}

export function ContractReviewWorkspace() {
    const { requestId = "" } = useParams<{ requestId: string }>();

    const reviewQuery = useQuery({
        queryKey: ["review", requestId],
        queryFn: () => getReview(requestId),
        enabled: Boolean(requestId),
        retry: false,
    });

    const requestQuery = useQuery({
        queryKey: ["request", requestId],
        queryFn: () => getRequest(requestId),
        enabled: Boolean(requestId),
    });

    const organisationsQuery = useQuery({
        queryKey: ["organisations"],
        queryFn: listOrganisations,
    });

    const orgId = requestQuery.data?.org_id ?? null;

    const contractsQuery = useQuery({
        queryKey: ["contracts", orgId],
        queryFn: () => listContracts(orgId!),
        enabled: Boolean(orgId),
    });

    const review: ReviewResponse | undefined = reviewQuery.data;

    const stats = useMemo(() => {
        if (!review) return null;
        const grounded = review.findings.filter(isGrounded);
        const reviewedCount = review.findings.filter((f) => f.status === "reviewed").length;
        return {
            total: review.findings.length,
            grounded: grounded.length,
            notAddressed: review.findings.length - grounded.length,
            reviewed: reviewedCount,
            obligations: review.obligations.length,
            escalations: review.escalations.length,
        };
    }, [review]);

    // Grounded findings split off; the rest are "not addressed".
    const groundedFindings = useMemo(
        () => review?.findings.filter(isGrounded) ?? [],
        [review],
    );
    const notAddressedFindings = useMemo(
        () => review?.findings.filter((f) => !isGrounded(f)) ?? [],
        [review],
    );

    const orgName = organisationsQuery.data?.find((o) => o.org_id === orgId)?.name;
    const contractsWithClauses = (contractsQuery.data ?? []).filter(
        (c) => c.has_clauses,
    );
    // The review API does not echo back which contract was reviewed; surface the
    // contract with clauses only when it is unambiguous, otherwise omit it.
    const reviewedContract =
        contractsWithClauses.length === 1 ? contractsWithClauses[0] : undefined;

    if (reviewQuery.isPending) {
        return (
            <div className="crv-loading">
                <span className="crv-spinner" aria-hidden />
                <p>Analyzing contract…</p>
            </div>
        );
    }

    if (reviewQuery.error || !review || !stats) {
        return (
            <div className="state-panel">
                <strong>No review has been run for this request yet.</strong>
                <Link className="button mt-md" to={`/requests/${requestId}`}>
                    Back to Request
                </Link>
            </div>
        );
    }

    const isHumanReviewComplete = stats.reviewed === stats.total && stats.total > 0;

    return (
        <div className="crv-page">
            <nav className="crv-back ctx-bar">
                <Link to={`/requests/${requestId}`} className="text-link">
                    ← Request Workspace
                </Link>
                <span className="ctx-request">
                    Request <code>{requestId}</code>
                </span>
            </nav>

            <header className="crv-header">
                <div>
                    <p className="eyebrow">Contract Review</p>
                    <h1 className="crv-title">
                        {orgName ?? orgId ?? "Organisation"}
                        {orgId && orgName ? ` · ${orgId}` : ""}
                    </h1>
                    {reviewedContract && (
                        <p className="crv-subtitle">
                            {reviewedContract.contract_id} · {reviewedContract.title}
                        </p>
                    )}
                </div>
                <div className="crv-header-badges">
                    <span className="crv-badge crv-badge--completed">
                        AI Analysis: <strong>COMPLETED</strong>
                    </span>
                    <span
                        className={
                            isHumanReviewComplete
                                ? "crv-badge crv-badge--completed"
                                : "crv-badge crv-badge--in-progress"
                        }
                    >
                        Human Review: <strong>{isHumanReviewComplete ? "COMPLETED" : "IN PROGRESS"}</strong>
                    </span>
                </div>
            </header>

            <section className="crv-summary">
                <SummaryCard label="Total Findings" value={stats.total} accent />
                <SummaryCard label="Grounded" value={stats.grounded} />
                <SummaryCard label="Human-Reviewed" value={stats.reviewed} />
                <SummaryCard label="Not Addressed" value={stats.notAddressed} />
                <SummaryCard label="Obligations" value={stats.obligations} />
                <SummaryCard label="Escalations" value={stats.escalations} />
            </section>

            <div className="crv-progress-banner">
                <span className="crv-progress-title">
                    Human Review Progress: {stats.reviewed} / {stats.total} reviewed
                </span>
                <span className={isHumanReviewComplete ? "crv-progress-sub crv-progress-sub--complete" : "crv-progress-sub"}>
                    {isHumanReviewComplete ? "✓ All findings human-reviewed" : "Review each finding to complete legal verification"}
                </span>
            </div>

            <section className="crv-section">
                <div className="crv-section-head">
                    <h2>Grounded Findings</h2>
                    <span className="crv-count-chip">{groundedFindings.length}</span>
                </div>
                {groundedFindings.length === 0 ? (
                    <p className="auth-subtitle">No grounded findings were produced.</p>
                ) : (
                    <div className="crv-finding-grid">
                        {groundedFindings.map((f) => (
                            <FindingCard key={f.finding_id} finding={f} requestId={requestId} />
                        ))}
                    </div>
                )}
            </section>

            {notAddressedFindings.length > 0 && (
                <NotAddressedSection findings={notAddressedFindings} requestId={requestId} />
            )}

            <section className="crv-section">
                <div className="crv-section-head">
                    <h2>Obligations</h2>
                    <span className="crv-count-chip">{stats.obligations}</span>
                </div>
                {review.obligations.length === 0 ? (
                    <p className="crv-empty">No obligations surfaced by this review.</p>
                ) : (
                    <ul className="crv-simple-list">
                        {review.obligations.map((ob) => (
                            <li key={ob.obligation_id}>
                                <strong>{ob.obligation_id}</strong> — band {ob.stored_band}, due{" "}
                                {ob.due_date}
                            </li>
                        ))}
                    </ul>
                )}
            </section>

            <section className="crv-section">
                <div className="crv-section-head">
                    <h2>Escalations</h2>
                    <span className="crv-count-chip">{stats.escalations}</span>
                </div>
                {review.escalations.length === 0 ? (
                    <p className="crv-empty">No escalations from this review.</p>
                ) : (
                    <ul className="crv-simple-list">
                        {review.escalations.map((esc) => (
                            <li key={esc.escalation_id}>
                                {esc.reason} — routed to {esc.routed_to_id}
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </div>
    );
}