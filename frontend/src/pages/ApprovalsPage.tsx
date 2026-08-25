import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { approveDraft, rejectDraft } from "../api/approvals";
import { me } from "../api/auth";
import { ApiError } from "../api/client";
import { listDrafts } from "../api/drafts";
import { listRequests } from "../api/requests";
import type { ApprovalResponse, DraftResponse, RequestResponse } from "../api/types";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { StatusIndicator } from "../components/StatusIndicator";

/** States from which the backend accepts a decision (app/services/approval.py). */
const OPEN_STATES = new Set(["awaiting_approval", "edited"]);

export function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [decision, setDecision] = useState<ApprovalResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: me });
  const requestsQuery = useQuery({
    queryKey: ["requests"],
    queryFn: () => listRequests(),
  });

  const requests: RequestResponse[] = requestsQuery.data ?? [];
  const activeRequestId =
    selectedRequestId ?? (requests.length > 0 ? requests[0].request_id : null);

  const draftsQuery = useQuery({
    queryKey: ["drafts", activeRequestId],
    queryFn: () => listDrafts(activeRequestId ?? ""),
    enabled: Boolean(activeRequestId),
  });

  const drafts: DraftResponse[] = draftsQuery.data ?? [];
  const currentVersion = Math.max(0, ...drafts.map((d) => d.version));

  const reviewerId = meQuery.data?.member_id ?? null;
  // Usability hint only — the backend remains authoritative and a 403 is
  // still handled if it disagrees.
  const canApproveHint = meQuery.data?.member?.can_approve === true;

  function afterDecision(data: ApprovalResponse) {
    setDecision(data);
    setErrorMessage(null);
    void queryClient.invalidateQueries({ queryKey: ["drafts", activeRequestId] });
    void queryClient.invalidateQueries({
      queryKey: ["request-history", activeRequestId],
    });
  }

  function onDecisionError(err: unknown) {
    if (
      err instanceof ApiError &&
      err.status === 403 &&
      typeof err.detail === "string" &&
      err.detail.includes("approval authority")
    ) {
      setErrorMessage(
        `Reviewer ${reviewerId ?? ""} does not have approval authority (can_approve=false).`,
      );
    } else if (err instanceof ApiError && err.status === 404) {
      setErrorMessage("This draft or reviewer could not be found.");
    } else if (err instanceof ApiError && err.status === 409) {
      setErrorMessage(
        typeof err.detail === "string"
          ? err.detail
          : "This draft has already been decided or is no longer current.",
      );
    } else {
      setErrorMessage(
        "Unable to record the decision. Please try again or contact support if the problem persists.",
      );
    }
  }

  const approveMutation = useMutation({
    mutationFn: () =>
      approveDraft(String(currentDraftId()), { reviewer_id: reviewerId ?? "" }),
    onSuccess: afterDecision,
    onError: onDecisionError,
  });

  const rejectMutation = useMutation({
    mutationFn: () =>
      rejectDraft(String(currentDraftId()), { reviewer_id: reviewerId ?? "" }),
    onSuccess: afterDecision,
    onError: onDecisionError,
  });

  function currentDraft(): DraftResponse | null {
    return (
      drafts.find(
        (d) =>
          d.version === currentVersion && OPEN_STATES.has(d.approval_state),
      ) ?? null
    );
  }

  function currentDraftId(): string {
    return currentDraft()?.draft_id ?? "";
  }

  function handleDecision(kind: "approve" | "reject") {
    setErrorMessage(null);
    if (kind === "approve") approveMutation.mutate();
    else rejectMutation.mutate();
  }

  if (requestsQuery.isPending || meQuery.isPending) {
    return <LoadingState message="Loading approvals…" />;
  }

  if (requestsQuery.error || !requestsQuery.data) {
    return (
      <ErrorState
        message="Unable to load approvals."
        onRetry={() => void requestsQuery.refetch()}
      />
    );
  }

  if (requests.length === 0) {
    return (
      <div>
        <PageHeader
          eyebrow="Rasikh workspace"
          title="Approvals"
          description="Lawyer decisions on draft versions."
        />
        <Card>
          <EmptyState
            title="Nothing to approve"
            description="There are no matters yet. Drafts appear here once created."
          />
        </Card>
      </div>
    );
  }
  return (
    <div>
      <PageHeader
        eyebrow="Rasikh workspace"
        title="Approvals"
        description="Lawyer decisions on the current draft version of a matter. Decisions are recorded by the backend and are terminal."
      />

      <label className="auth-field">
        Matter
        <select
          value={activeRequestId ?? ""}
          onChange={(e) => {
            setSelectedRequestId(e.target.value);
            setDecision(null);
            setErrorMessage(null);
          }}
        >
          {requests.map((r) => (
            <option key={r.request_id} value={r.request_id}>
              {r.request_id}
              {r.org_id ? ` — ${r.org_id}` : ""}
            </option>
          ))}
        </select>
      </label>

      {activeRequestId && (
        <p className="auth-subtitle">
          Matter record:{" "}
          <Link className="text-link" to={`/requests/${encodeURIComponent(activeRequestId)}`}>
            open {activeRequestId}
          </Link>
          {" · "}Drafts:{" "}
          <Link className="text-link" to="/drafts">open drafts workspace</Link>
        </p>
      )}

      {errorMessage && (
        <p className="auth-error" role="alert">{errorMessage}</p>
      )}

      {draftsQuery.isPending && <LoadingState message="Loading draft versions…" />}

      {draftsQuery.error && (
        <ErrorState
          message="Unable to load draft versions for this matter."
          onRetry={() => void draftsQuery.refetch()}
        />
      )}

      {!draftsQuery.isPending &&
        !draftsQuery.error &&
        drafts.length === 0 && (
          <Card className="mt-md">
            <EmptyState
              title="No drafts for this matter"
              description="Create a draft in the drafts workspace first."
            />
          </Card>
        )}

      {drafts.length > 0 && (
        <Card className="mt-md">
          <DataTable<DraftResponse>
            getKey={(d) => String(d.draft_id)}
            columns={[
              {
                label: "Version",
                value: (d) =>
                  d.version === currentVersion ? `v${d.version} (current)` : `v${d.version}`,
              },
              {
                label: "Approval state",
                value: (d) => <StatusIndicator status={d.approval_state} />,
              },
              {
                label: "Created",
                value: (d) => new Date(d.created_at).toLocaleString(),
              },
              {
                label: "Updated",
                value: (d) => new Date(d.updated_at).toLocaleString(),
              },
            ]}
            items={drafts}
          />
        </Card>
      )}

      {currentDraft() ? (
        <Card className="mt-md">
          <p className="eyebrow">Decision — v{currentDraft()?.version}</p>
          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <button
              type="button"
              className="button"
              disabled={
                approveMutation.isPending ||
                rejectMutation.isPending ||
                !reviewerId
              }
              onClick={() => handleDecision("approve")}
            >
              {approveMutation.isPending ? "Recording…" : "Approve"}
            </button>
            <button
              type="button"
              className="logout-button"
              disabled={
                approveMutation.isPending ||
                rejectMutation.isPending ||
                !reviewerId
              }
              onClick={() => handleDecision("reject")}
            >
              {rejectMutation.isPending ? "Recording…" : "Reject"}
            </button>
            {(approveMutation.isPending || rejectMutation.isPending) && (
              <span className="auth-subtitle">Recording decision…</span>
            )}
          </div>
          {!canApproveHint && (
            <p className="auth-subtitle">
              Your linked member does not carry the can_approve capability; the
              backend will refuse the decision if it is not permitted.
            </p>
          )}
        </Card>
      ) : (
        drafts.length > 0 && (
          <Card className="mt-md">
            <EmptyState
              title="No decision available"
              description="Only the current version can be decided, and only while it is awaiting approval or edited."
            />
          </Card>
        )
      )}

      {decision && (
        <Card className="mt-md">
          <p className="eyebrow">Recorded decision</p>
          <h2 style={{ marginTop: "4px", fontSize: "20px" }}>
            {decision.decision} — v{decision.draft_version}
          </h2>
          <StatusIndicator status={decision.decision} />
          <p className="auth-subtitle">
            Reviewer {decision.reviewer_id} at{" "}
            {new Date(decision.decided_at).toLocaleString()}
          </p>
          <p className="auth-subtitle">
            The audit history for this matter now carries the{" "}
            {decision.decision} event.
          </p>
        </Card>
      )}
    </div>
  );
}
