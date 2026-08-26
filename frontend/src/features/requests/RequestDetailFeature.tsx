"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { me } from "../../api/auth";
import { getRequestHistory } from "../../api/history";
import { listContracts } from "../../api/contracts";
import { listOrganisations } from "../../api/organisations";
import { getRequest, getRequestView, resolveRequest } from "../../api/requests";
import { getReview, runReview } from "../../api/reviews";
import { generateAIDraft } from "../../api/drafts";
import { ApiError } from "../../api/client";
import type {
  AnalysisRunSummary,
  AuditEventResponse,
  FindingSummary,
  ObligationSummary,
} from "../../api/types";
import { Card, StatusIndicator } from "../../components/ui";

// ---------------------------------------------------------------------------
// Helpers (pure, data-derived — no hardcoded workflow states)
// ---------------------------------------------------------------------------

const SEVERITY_ORDER = ["low", "medium", "high", "critical"];

/** Extract the normalised level from a verbatim rating like "Low risk". */
function severityLevel(risk?: string | null): string | null {
  if (!risk) return null;
  const r = risk.toLowerCase();
  for (let i = SEVERITY_ORDER.length - 1; i >= 0; i--) {
    if (r.includes(SEVERITY_ORDER[i])) return SEVERITY_ORDER[i];
  }
  return null;
}

function severityRank(risk?: string | null): number {
  const level = severityLevel(risk);
  return level ? SEVERITY_ORDER.indexOf(level) : -1;
}

function titleCase(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Prioritise: high severity first, then sharia-sensitive, then ungrounded. */
function prioritiseFindings(findings: FindingSummary[]): FindingSummary[] {
  return [...findings].sort((a, b) => {
    const sev = severityRank(b.risk_rating) - severityRank(a.risk_rating);
    if (sev !== 0) return sev;
    if (a.sharia_sensitive_flag !== b.sharia_sensitive_flag)
      return a.sharia_sensitive_flag ? -1 : 1;
    if (a.grounded !== b.grounded) return a.grounded ? 1 : -1;
    return 0;
  });
}

type StepState = "done" | "active" | "pending";

interface Step {
  key: string;
  label: string;
  state: StepState;
}

/**
 * Derive the workflow position strictly from existing backend data.
 * No invented statuses: every boolean comes from persisted request/view data.
 */
function deriveSteps(opts: {
  status: string;
  hasOrg: boolean;
  hasAnalysis: boolean;
  findingCount: number;
  draftCount: number;
  approvalCount: number;
}): Step[] {
  const { status, hasOrg, hasAnalysis, findingCount, draftCount, approvalCount } =
    opts;
  const completed = status === "completed" || status === "resolved";
  return [
    { key: "submitted", label: "Submitted", state: "done" },
    {
      key: "ai",
      label: "AI Analysis",
      state: hasAnalysis ? "done" : hasOrg ? "active" : "pending",
    },
    {
      key: "review",
      label: "Review",
      state:
        findingCount > 0 ? "done" : hasAnalysis && hasOrg ? "active" : "pending",
    },
    {
      key: "draft",
      label: "Draft",
      state: draftCount > 0 ? "done" : findingCount > 0 ? "active" : "pending",
    },
    {
      key: "approval",
      label: "Approval",
      state: approvalCount > 0 ? "done" : draftCount > 0 ? "active" : "pending",
    },
    {
      key: "completed",
      label: "Completed",
      state: completed ? "done" : approvalCount > 0 ? "active" : "pending",
    },
  ];
}

function WorkflowStepper({ steps }: { steps: Step[] }) {
  return (
    <ol className="ws-stepper" aria-label="Request workflow">
      {steps.map((step, i) => (
        <li
          key={step.key}
          className={`ws-step ws-step-${step.state}`}
          aria-current={step.state === "active" ? "step" : undefined}
        >
          <span className="ws-step-dot">{step.state === "done" ? "✓" : i + 1}</span>
          <span className="ws-step-label">{step.label}</span>
          {i < steps.length - 1 && <span className="ws-step-line" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

function SeverityBadge({ rating }: { rating?: string | null }) {
  const level = severityLevel(rating);
  if (!level) return null;
  return <span className={`ws-sev ws-sev-${level}`}>{level}</span>;
}

function ObligationRow({ obligation }: { obligation: ObligationSummary }) {
  return (
    <li className="ws-list-row">
      <Link className="text-link" to="/obligations">
        {obligation.obligation_id}
      </Link>
      <span className="ws-row-desc">{obligation.description}</span>
      <span className="ws-row-meta">
        owner {obligation.owner_id} · due{" "}
        {new Date(obligation.due_date).toLocaleDateString()} · band{" "}
        <StatusIndicator status={obligation.band} />
      </span>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RequestDetailFeature() {
  const { requestId = "" } = useParams<{ requestId: string }>();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftNotice, setDraftNotice] = useState<string | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [selectedContractId, setSelectedContractId] = useState("");
  const [selectedRequestType, setSelectedRequestType] = useState<
    "" | "contract_review" | "consultation" | "meeting_prep" | "obligation_check"
  >("");
  const [showFullAnswer, setShowFullAnswer] = useState(false);

  const requestQuery = useQuery({
    queryKey: ["request", requestId],
    queryFn: () => getRequest(requestId),
    enabled: Boolean(requestId),
  });

  const historyQuery = useQuery({
    queryKey: ["request-history", requestId],
    queryFn: () => getRequestHistory(requestId),
    enabled: Boolean(requestId),
  });

  const reviewQuery = useQuery({
    queryKey: ["review", requestId],
    queryFn: () => getReview(requestId),
    enabled: Boolean(requestId),
    retry: false,
  });

  const { data, isPending, error, refetch } = requestQuery;

  const viewQuery = useQuery({
    queryKey: ["request-view", requestId],
    queryFn: () => getRequestView(requestId),
    enabled: Boolean(requestId),
  });

  const meQuery = useQuery({ queryKey: ["me"], queryFn: me });

  const organisationsQuery = useQuery({
    queryKey: ["organisations"],
    queryFn: listOrganisations,
  });

  const contractsQuery = useQuery({
    queryKey: ["contracts", data?.org_id],
    queryFn: () => listContracts(data!.org_id!),
    enabled: Boolean(data?.org_id),
  });

  // Auto-select the first contract that actually has clauses (e.g. C-01).
  const contracts = contractsQuery.data ?? [];
  useEffect(() => {
    if (!selectedContractId && contracts.length > 0) {
      const preferred = contracts.find((c) => c.has_clauses) ?? contracts[0];
      setSelectedContractId(preferred.contract_id);
    }
  }, [contracts, selectedContractId]);

  const resolveMutation = useMutation({
    mutationFn: () =>
      resolveRequest(requestId, {
        org_id: selectedOrgId,
        request_type: selectedRequestType as never,
      }),
    onSuccess: () => {
      setResolveError(null);
      void requestQuery.refetch();
      void queryClient.invalidateQueries({
        queryKey: ["request-history", requestId],
      });
    },
    onError: (err) => {
      if (err instanceof ApiError && typeof err.detail === "string") {
        setResolveError(err.detail);
      } else {
        setResolveError("Unable to resolve request.");
      }
    },
  });

  const runMutation = useMutation({
    mutationFn: () =>
      runReview(requestId, {
        member_id: meQuery.data?.member_id ?? "",
        org_id: requestQuery.data?.org_id ?? "",
        contract_id: selectedContractId || null,
      }),
    onSuccess: () => {
      setReviewError(null);
      void queryClient.invalidateQueries({
        queryKey: ["request-history", requestId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["request-view", requestId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["review", requestId],
      });
      // Navigate only after the POST succeeds.
      navigate(`/requests/${requestId}/review`);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 403) {
        setReviewError(
          "Your account is not authorised to review this organisation's matters.",
        );
      } else {
        setReviewError(
          "Unable to run the review. Please try again or contact support.",
        );
      }
    },
  });

  const draftMutation = useMutation({
    mutationFn: () => generateAIDraft(requestId),
    onSuccess: (created) => {
      setDraftError(null);
      setDraftNotice(
        `AI draft v${created.version} generated and saved. It is awaiting approval.`,
      );
      void queryClient.invalidateQueries({ queryKey: ["drafts", requestId] });
      void queryClient.invalidateQueries({
        queryKey: ["request-history", requestId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["request-view", requestId],
      });
      navigate(
        `/requests/${encodeURIComponent(requestId)}/drafts/${encodeURIComponent(created.draft_id)}`,
      );
    },
    onError: (err) => {
      setDraftNotice(null);
      if (err instanceof ApiError && typeof err.detail === "string") {
        // e.g. "all findings must be human-reviewed..." (409) or request not found (404).
        setDraftError(err.detail);
      } else {
        setDraftError(
          "Unable to generate an AI draft. Complete the analysis and human review, then try again.",
        );
      }
    },
  });

  // ---- derived view model --------------------------------------------------
  const view = viewQuery.data;
  const counts = view?.counts;
  const analysis = view?.analysis ?? null;

  const sortedFindings = useMemo(
    () => (view ? prioritiseFindings(view.findings) : []),
    [view],
  );
  const topFindings = sortedFindings.slice(0, 5);
  const groundedCount = view?.findings.filter((f) => f.grounded).length ?? 0;
  const ungroundedCount =
    view?.findings.filter((f) => !f.grounded).length ?? 0;
  const highSeverityCount =
    view?.findings.filter((f) => severityRank(f.risk_rating) >= 2).length ?? 0;
  const pendingDrafts =
    view?.drafts.filter((d) => d.approval_state !== "approved").length ?? 0;
  const overallRisk = useMemo(() => {
    const worst = [...(view?.findings ?? [])].sort(
      (a, b) => severityRank(b.risk_rating) - severityRank(a.risk_rating),
    )[0];
    return severityLevel(worst?.risk_rating);
  }, [view]);
  // Obligations that are overdue/urgent by band, or due within 30 days.
  const attentionObligations =
    view?.obligations.filter((o) => {
      if (["overdue", "urgent"].includes(o.band.toLowerCase())) return true;
      const due = new Date(o.due_date).getTime();
      return due - Date.now() < 30 * 24 * 60 * 60 * 1000;
    }).length ?? 0;

  // "Needs attention" items — every entry is derived from real backend fields.
  const attentionItems: { tone: string; label: string; count: number }[] = [];
  if (highSeverityCount > 0)
    attentionItems.push({ tone: "high", label: "High-severity findings", count: highSeverityCount });
  if (ungroundedCount > 0)
    attentionItems.push({ tone: "medium", label: "Citation checks needed", count: ungroundedCount });
  if (pendingDrafts > 0)
    attentionItems.push({ tone: "medium", label: "Drafts awaiting decision", count: pendingDrafts });
  if (attentionObligations > 0)
    attentionItems.push({ tone: "low", label: "Obligations due soon or overdue", count: attentionObligations });


  const steps = useMemo(() => {
    if (!data) return [];
    return deriveSteps({
      status: data.status,
      hasOrg: Boolean(data.org_id),
      hasAnalysis: Boolean(view?.analysis),
      findingCount: counts?.findings ?? 0,
      draftCount: counts?.drafts ?? 0,
      approvalCount: counts?.approvals ?? 0,
    });
  }, [data, view, counts]);

  const decisionLabel = useMemo(() => {
    if (view?.decision) return view.decision;
    if (!data) return "INTAKE";
    if (data.status === "access_denied" || view?.access_decisions?.some((a) => a.outcome === "unauthorized")) {
      return "REFUSE_ACCESS";
    }
    if (data.status === "escalated" || (view?.escalations?.length ?? 0) > 0) {
      return "ESCALATE";
    }
    if (data.status === "insufficient") {
      return "REQUEST_INFO";
    }
    if (view?.findings?.some((f) => !f.grounded)) {
      return "NOT_IN_DOCUMENTS";
    }
    if (data.request_type === "contract_review") return "REVIEW_CONTRACT";
    if (data.request_type === "consultation") return "ANSWER_CONSULTATION";
    if (data.request_type === "meeting_prep") return "PREP_MEETING";
    if (data.request_type === "obligation_check") return "FLAG_OBLIGATION";
    return data.status.toUpperCase();
  }, [data, view]);

  // ---- loading / error states ----------------------------------------------
  if (isPending) {
    return <div className="state-panel">Loading request workspace...</div>;
  }

  if (error || !data) {
    return (
      <div className="state-panel">
        <strong>Unable to load this request.</strong>
        <button className="button mt-md" onClick={() => refetch()}>
          Try again
        </button>
      </div>
    );
  }

  const canReview = Boolean(data.org_id && meQuery.data?.member_id);
  const typeLabel = data.request_type ? titleCase(data.request_type) : "Unclassified";

  return (
    <div className="ws-page">
      {/* ------------------------------------------------ Header ---------- */}
      <header className="ws-header">
        <div className="ws-header-main">
          <p className="eyebrow">Request workspace</p>
          <h1>{typeLabel}</h1>
          <dl className="ws-meta">
            <div>
              <dt>Request ID</dt>
              <dd>
                <code>{data.request_id}</code>
              </dd>
            </div>
            <div>
              <dt>Request Type</dt>
              <dd>{typeLabel}</dd>
            </div>
            <div>
              <dt>Decision</dt>
              <dd>
                <span className="ws-sev" style={{ background: "rgba(0,0,0,0.06)", fontWeight: 600, color: "var(--color-fg-default)" }}>
                  {decisionLabel}
                </span>
              </dd>
            </div>
            <div>
              <dt>Organisation</dt>
              <dd>{data.org_id ?? "Not assigned"}</dd>
            </div>
            <div>
              <dt>Requested by</dt>
              <dd>{data.requester_id}</dd>
            </div>
            <div>
              <dt>Submitted</dt>
              <dd>{new Date(data.created_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <StatusIndicator status={data.status} />
              </dd>
            </div>
          </dl>
        </div>
        <div className="ws-header-actions">
          <Link
            className="button"
            to={`/requests/${encodeURIComponent(data.request_id)}/review`}
          >
            Open Review Workspace
          </Link>
          <Link className="button-secondary" to="/requests">
            Back to registry
          </Link>
        </div>
      </header>

      {/* --------------------------------------------- Workflow stepper --- */}
      <WorkflowStepper steps={steps} />

      {/* --------------------------------------------- Security & Access Denial --- */}
      {(data.status === "access_denied" ||
        view?.access_decisions?.some((a) => a.outcome === "unauthorized")) && (
        <Card className="mt-md" style={{ borderLeft: "4px solid #e53e3e", background: "#fff5f5" }}>
          <p className="eyebrow" style={{ color: "#c53030" }}>Security &amp; Authorization</p>
          <h2 style={{ fontSize: "18px", color: "#9b2c2c", margin: "4px 0" }}>
            ACCESS DENIED — Document Access Halted
          </h2>
          <p style={{ color: "#742a2a", margin: "8px 0" }}>
            Access check failed prior to reading matter documents. Requester <code>{data.requester_id}</code> is not on the assigned matter team for <strong>{data.org_id ?? "this organisation"}</strong>.
          </p>
          <p className="auth-subtitle" style={{ color: "#9b2c2c", margin: 0 }}>
            Rule SEC-001 enforced: document retrieval was stopped. No protected contract text or confidential findings are rendered.
          </p>
        </Card>
      )}

      {/* --------------------------------------------- Escalation Banner ---------- */}
      {(data.status === "escalated" || (view?.escalations?.length ?? 0) > 0) && (
        <Card className="mt-md" style={{ borderLeft: "4px solid #dd6b20", background: "#fffaf0" }}>
          <p className="eyebrow" style={{ color: "#c05621" }}>Workflow Escalation</p>
          <h2 style={{ fontSize: "18px", color: "#9c4221", margin: "4px 0" }}>
            ESCALATED TO HUMAN COUNSEL
          </h2>
          <p style={{ color: "#7b341e", margin: "8px 0" }}>
            Reason: <strong>{view?.escalations[0]?.reason?.replaceAll("_", " ") ?? "Litigation / Statutory trigger"}</strong>.
            Routed to senior counsel: <code>{view?.escalations[0]?.routed_to_id ?? "Legal Counsel"}</code>.
          </p>
          <p className="auth-subtitle" style={{ color: "#9c4221", margin: 0 }}>
            Rule ESC-006 enforced: no automated draft legal answer is produced when an instruction requires senior escalation.
          </p>
        </Card>
      )}

      {/* ------------------------- Organisation resolution (when needed) -- */}
      {data.status === "insufficient" && !data.org_id && (
        <Card className="mt-md">
          <p className="eyebrow">Action required</p>
          <h2 style={{ fontSize: "16px", color: "var(--red-11)" }}>
            Organisation could not be identified
          </h2>
          <p>Select it before running the analysis.</p>
          <div style={{ display: "grid", gap: "12px", maxWidth: "420px" }}>
            <label className="auth-field">
              Organisation
              <select
                value={selectedOrgId}
                onChange={(e) => setSelectedOrgId(e.target.value)}
                disabled={resolveMutation.isPending}
              >
                <option value="">Select organisation...</option>
                {(organisationsQuery.data ?? []).map((o) => (
                  <option key={o.org_id} value={o.org_id}>
                    {o.name} ({o.org_id})
                  </option>
                ))}
              </select>
            </label>
            <label className="auth-field">
              Request type
              <select
                value={selectedRequestType}
                onChange={(e) =>
                  setSelectedRequestType(e.target.value as typeof selectedRequestType)
                }
                disabled={resolveMutation.isPending}
              >
                <option value="">Select type...</option>
                <option value="contract_review">Contract review</option>
                <option value="consultation">Consultation</option>
                <option value="meeting_prep">Meeting preparation</option>
                <option value="obligation_check">Obligation check</option>
              </select>
            </label>
            <button
              type="button"
              className="button"
              disabled={resolveMutation.isPending || !selectedOrgId || !selectedRequestType}
              onClick={() => resolveMutation.mutate()}
            >
              {resolveMutation.isPending ? "Saving…" : "Confirm details"}
            </button>
            {resolveError && (
              <p className="auth-error" role="alert">{resolveError}</p>
            )}
          </div>
        </Card>
      )}

      {/* --------------------------------------------- AI Analysis hero --- */}
      {data.status !== "access_denied" && (
      <section className="ws-hero mt-md">
        <div className="ws-hero-head">
          <div>
            <p className="eyebrow">AI analysis</p>
            <h2>
              {analysis?.status === "completed"
                ? `${typeLabel} result`
                : "AI Analysis"}
            </h2>
          </div>
          <div className="ws-hero-badges">
            {overallRisk && (
              <span className={`ws-sev ws-sev-${overallRisk} ws-risk-badge`}>
                {overallRisk} risk
              </span>
            )}
            {analysis && (
              <span className={`ws-sev ws-run-status ws-run-${analysis.status}`}>
                {analysis.status}
                {analysis.engine === "deterministic_fallback" && " · fallback"}
              </span>
            )}
          </div>
        </div>

        {analysis?.completed_at && (
          <p className="ws-analysis-time">
            Analysis completed {new Date(analysis.completed_at).toLocaleString()}
          </p>
        )}

        {analysis?.summary ? (
          <>
            <pre className="crv-statement ws-hero-text">
              {
                showFullAnswer || analysis.summary.length <= 700
                  ? analysis.summary
                  : `${analysis.summary.slice(0, 700)}…`
              }
            </pre>
            {analysis.summary.length > 700 && (
              <button
                type="button"
                className="ws-linklike"
                onClick={() => setShowFullAnswer((v) => !v)}
              >
                {showFullAnswer ? "Show less" : "Show full result"}
              </button>
            )}
          </>
        ) : (
          <p className="auth-subtitle">
            No analysis has been completed yet. Run the analysis to produce
            findings for this matter.
          </p>
        )}
        {reviewError && <p className="auth-error" role="alert">{reviewError}</p>}

        <div className="ws-stats">
          <div className="ws-stat">
            <span className="ws-stat-value">
              {analysis?.finding_count ?? counts?.findings ?? 0}
            </span>
            <span className="ws-stat-label">findings</span>
          </div>
          <div className="ws-stat">
            <span className="ws-stat-value">
              {analysis?.high_severity_count ?? highSeverityCount}
            </span>
            <span className="ws-stat-label">high severity</span>
          </div>
          <div className="ws-stat">
            <span className="ws-stat-value">
              {analysis && analysis.finding_count > 0
                ? `${Math.round((analysis.grounded_count / analysis.finding_count) * 100)}%`
                : counts && counts.findings > 0
                  ? `${Math.round((groundedCount / counts.findings) * 100)}%`
                  : "—"}
            </span>
            <span className="ws-stat-label">grounded</span>
          </div>
          <div className="ws-stat">
            <span className="ws-stat-value">{counts?.obligations ?? 0}</span>
            <span className="ws-stat-label">org obligations</span>
          </div>
          <div className="ws-stat">
            <span className="ws-stat-value">{view?.sources.length ?? 0}</span>
            <span className="ws-stat-label">sources</span>
          </div>
        </div>

        {(() => {
          const isEscalatedOrRefused =
            data.status === "escalated" ||
            data.status === "access_denied" ||
            (view?.escalations?.length ?? 0) > 0 ||
            view?.decision === "ESCALATE" ||
            view?.decision === "REFUSE_ACCESS" ||
            view?.decision === "REFUSE_OVERRIDE";
          const isObligationCheck = data.request_type === "obligation_check";

          return (
            <div className="ws-hero-actions">
              {canReview && !isObligationCheck && !isEscalatedOrRefused && (
                <button
                  type="button"
                  className="button-secondary"
                  disabled={runMutation.isPending}
                  onClick={() => runMutation.mutate()}
                >
                  {runMutation.isPending
                    ? "Analyzing…"
                    : counts && counts.findings > 0
                      ? "Re-run analysis"
                      : "Run analysis"}
                </button>
              )}
              {analysis?.status === "completed" && !isEscalatedOrRefused && (
                <button
                  type="button"
                  className="button-secondary"
                  disabled={draftMutation.isPending}
                  onClick={() => draftMutation.mutate()}
                >
                  {draftMutation.isPending
                    ? "Generating…"
                    : counts && counts.drafts > 0
                      ? "Generate new draft"
                      : "Generate AI draft"}
                </button>
              )}
              <Link
                className="button"
                to={`/requests/${encodeURIComponent(data.request_id)}/review`}
              >
                View Full Analysis
              </Link>
            </div>
          );
        })()}
        {draftMutation.isPending && (
          <p className="auth-subtitle">Composing the grounded draft…</p>
        )}
        {draftError && <p className="auth-error" role="alert">{draftError}</p>}
        {draftNotice && !draftError && (
          <p className="auth-subtitle">{draftNotice}</p>
        )}
      </section>
      )}

      {/* ---------------- Needs attention + work product (2-col) --------- */}
      <div className="ws-columns mt-md">
        <section className="ws-attention" aria-label="Needs attention">
          <p className="eyebrow">Needs attention</p>
          {attentionItems.length === 0 ? (
            <p className="auth-subtitle">
              Nothing requires immediate human action on this request.
            </p>
          ) : (
            <ul className="ws-attention-list">
              {attentionItems.map((item) => (
                <li
                  key={item.label}
                  className={`ws-attention-item ws-attn-${item.tone}`}
                >
                  <span className="ws-attn-dot" aria-hidden />
                  <span className="ws-attn-label">{item.label}</span>
                  <span className="ws-attn-count">{item.count}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Work product">
          <p className="eyebrow">Work product</p>
          <div className="ws-cards ws-cards-compact">
            <Link
              className="ws-card"
              to={`/requests/${encodeURIComponent(data.request_id)}/drafts`}
            >
              <span className="ws-card-label">Drafts</span>
              <span className="ws-card-value">
                {counts?.drafts ?? 0}
                <span className="ws-card-arrow" aria-hidden>→</span>
              </span>
              <span className="ws-card-sub">
                {pendingDrafts > 0
                  ? `${pendingDrafts} awaiting decision`
                  : (counts?.drafts ?? 0) === 0
                    ? "none created"
                    : "all decided"}
              </span>
            </Link>
            <Link
              className="ws-card"
              to={`/requests/${encodeURIComponent(data.request_id)}/approvals`}
            >
              <span className="ws-card-label">Approvals</span>
              <span className="ws-card-value">
                {counts?.approvals ?? 0}
                <span className="ws-card-arrow" aria-hidden>→</span>
              </span>
              <span className="ws-card-sub">
                {(counts?.approvals ?? 0) === 0
                  ? "none recorded"
                  : pendingDrafts > 0
                    ? `${pendingDrafts} draft(s) still pending`
                    : "fully approved"}
              </span>
            </Link>
            <Link
              className="ws-card"
              to={`/requests/${encodeURIComponent(data.request_id)}/review`}
            >
              <span className="ws-card-label">Findings</span>
              <span className="ws-card-value">
                {counts?.findings ?? 0}
                <span className="ws-card-arrow" aria-hidden>→</span>
              </span>
              <span className="ws-card-sub">high severity: {highSeverityCount}</span>
            </Link>
            <Link className="ws-card" to="/obligations">
              <span className="ws-card-label">Obligations</span>
              <span className="ws-card-value">
                {counts?.obligations ?? 0}
                <span className="ws-card-arrow" aria-hidden>→</span>
              </span>
              <span className="ws-card-sub">organization-scoped</span>
            </Link>
          </div>
        </section>
      </div>

      {/* ------------------------------------------------ Findings -------- */}
      {data.status !== "access_denied" && (
      <Card className="mt-md">
        <div className="ws-section-head">
          <div>
            <p className="eyebrow">Findings</p>
            <h2>
              Key findings{(counts?.findings ?? 0) > 0 ? ` (${counts?.findings})` : ""}
            </h2>
          </div>
          {(counts?.findings ?? 0) > 5 && (
            <Link
              className="text-link"
              to={`/requests/${encodeURIComponent(data.request_id)}/review`}
            >
              View all in Review Workspace →
            </Link>
          )}
        </div>
        {sortedFindings.length === 0 ? (
          <p className="auth-subtitle">
            No findings yet — run the analysis to generate them.
          </p>
        ) : (
          <ul className="ws-finding-list">
            {topFindings.map((f) => (
              <li key={f.finding_id} className="ws-finding">
                <div className="ws-finding-tags" style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "6px" }}>
                  <SeverityBadge rating={f.risk_rating} />
                  {f.sharia_sensitive_flag && (
                    <span className="ws-sev ws-sev-sharia">sharia-sensitive</span>
                  )}
                  {!f.grounded ? (
                    <span className="ws-sev ws-sev-ungrounded">
                      Not in documents
                    </span>
                  ) : (
                    <span className="ws-sev" style={{ background: "#e6fffa", color: "#234e52", border: "1px solid #b2f5ea" }}>
                      ✓ Grounded
                    </span>
                  )}
                </div>
                <p className="ws-finding-text">{f.statement}</p>

                {/* Grounded Citations (Task 8) */}
                {f.citations && f.citations.length > 0 && (
                  <div style={{ marginTop: "8px", paddingTop: "8px", borderTop: "1px dashed rgba(0,0,0,0.1)", display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "var(--color-fg-muted)", fontWeight: 500 }}>Citations:</span>
                    {f.citations.map((c) => (
                      <span
                        key={c.citation_id}
                        style={{
                          fontSize: "12px",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          background: c.source_type === "contract_clause" ? "#ebf8ff" : "#f7fafc",
                          color: c.source_type === "contract_clause" ? "#2b6cb0" : "#4a5568",
                          border: "1px solid rgba(0,0,0,0.1)",
                          fontFamily: "monospace",
                        }}
                      >
                        {c.source_type === "contract_clause" ? "📄 " : "📜 "}
                        {c.clause_reference ?? c.source_type}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      )}

      {/* ------------------------------- Organization Obligations --------- */}
      <Card className="mt-md">
        <div className="ws-section-head">
          <div>
            <p className="eyebrow">Related organization obligations</p>
            <h2>
              Organization Obligations
              {(counts?.obligations ?? 0) > 0 ? ` (${counts?.obligations})` : ""}
            </h2>
            <p className="auth-subtitle">
              Organisation-scoped obligations on file for{" "}
              {data.org_id ?? "this organisation"} — tracked at the organisation
              level and may predate this request.
            </p>
          </div>
          {(counts?.obligations ?? 0) > 5 && (
            <Link className="text-link" to="/obligations">
              View all →
            </Link>
          )}
        </div>
        {!view || view.obligations.length === 0 ? (
          <p className="auth-subtitle">No organization obligations on file.</p>
        ) : (
          <ul className="ws-list">
            {view.obligations.slice(0, 5).map((o) => (
              <ObligationRow key={o.obligation_id} obligation={o} />
            ))}
          </ul>
        )}
      </Card>

      {/* --------------------------------------------------- Sources ------ */}
      <Card className="mt-md">
        <div className="ws-section-head">
          <div>
            <p className="eyebrow">Evidence &amp; sources</p>
            <h2>
              {view && view.sources.length > 0
                ? `${view.sources.length} source${view.sources.length === 1 ? "" : "s"} analyzed`
                : "Sources"}
            </h2>
            <p className="auth-subtitle">
              Documents the analysis drew upon for this organisation.
            </p>
          </div>
        </div>
        {!view || view.sources.length === 0 ? (
          <p className="auth-subtitle">
            No source documents linked to this organisation.
          </p>
        ) : (
          <ul className="ws-list">
            {view.sources.map((s) => (
              <li key={s.contract_id} className="ws-list-row">
                <Link className="text-link" to="/documents">
                  {s.contract_id}
                </Link>
                <span className="ws-row-desc">{s.title}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ---------------------------------------------- Audit timeline ---- */}
      <Card className="mt-md">
        <p className="eyebrow">Activity</p>
        <h2>Audit History</h2>
        {historyQuery.isPending && (
          <p className="auth-subtitle">Loading audit events…</p>
        )}
        {historyQuery.error && (
          <p className="auth-subtitle">
            Unable to load the audit history for this matter.
          </p>
        )}
        {historyQuery.data &&
          (historyQuery.data.events.length === 0 ? (
            <p className="auth-subtitle">No activity recorded yet.</p>
          ) : (
            <>
              <ol className="ws-timeline">
                {historyQuery.data.events.map((event: AuditEventResponse) => (
                  <li key={event.audit_event_id} className="ws-timeline-item">
                    <span className="ws-timeline-dot" aria-hidden />
                    <div>
                      <span className="ws-timeline-event">
                        {event.event_type.replaceAll("_", " ")}
                      </span>
                      <span className="ws-timeline-time">
                        {new Date(event.occurred_at).toLocaleString()}
                        {event.detail_reference ? ` — ${event.detail_reference}` : ""}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
              <Link className="text-link ws-timeline-more" to="/history">
                View complete audit history →
              </Link>
            </>
          ))}
      </Card>
    </div>
  );
}
