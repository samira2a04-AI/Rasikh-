import { useState, useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { createDraft, listDrafts } from "../api/drafts";
import { listRequests } from "../api/requests";
import type { DraftResponse, RequestResponse } from "../api/types";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { RequestContextBar } from "../components/RequestContextBar";
import { StatusIndicator } from "../components/StatusIndicator";

export function DraftsPage() {
  const queryClient = useQueryClient();
  const { requestId: routeRequestId, draftId: routeDraftId } = useParams<{
    requestId?: string;
    draftId?: string;
  }>();
  const [searchParams] = useSearchParams();
  const queryRequestId = searchParams.get("request");
  const queryDraftId = searchParams.get("draft");

  const contextRequestId = routeRequestId || queryRequestId || null;
  const contextDraftId = routeDraftId || queryDraftId || null;

  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(
    contextRequestId,
  );
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(
    contextDraftId,
  );
  const [content, setContent] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (contextRequestId) setSelectedRequestId(contextRequestId);
    if (contextDraftId) setSelectedDraftId(contextDraftId);
  }, [contextRequestId, contextDraftId]);

  const requestsQuery = useQuery({
    queryKey: ["requests"],
    queryFn: () => listRequests(),
  });

  const requests: RequestResponse[] = requestsQuery.data ?? [];
  const activeRequestId =
    selectedRequestId ?? contextRequestId ?? (requests.length > 0 ? requests[0].request_id : null);
  const activeRequest = requests.find((r) => r.request_id === activeRequestId);

  const draftsQuery = useQuery({
    queryKey: ["drafts", activeRequestId],
    queryFn: () => listDrafts(activeRequestId ?? ""),
    enabled: Boolean(activeRequestId),
  });

  const drafts: DraftResponse[] = draftsQuery.data ?? [];
  const activeDraftId = selectedDraftId ?? contextDraftId;
  const selectedDraft =
    drafts.find((d) => String(d.draft_id) === String(activeDraftId)) ??
    (drafts.length > 0 ? drafts[0] : null);

  const createMutation = useMutation({
    mutationFn: () =>
      createDraft(activeRequestId ?? "", {
        content,
      }),
    onSuccess: (created) => {
      setContent("");
      setErrorMessage(null);
      setSelectedDraftId(String(created.draft_id));
      void queryClient.invalidateQueries({ queryKey: ["drafts", activeRequestId] });
      void queryClient.invalidateQueries({
        queryKey: ["request-history", activeRequestId],
      });
    },
    onError: (err) => {
      if (
        err instanceof ApiError &&
        err.status === 400 &&
        typeof err.detail === "string" &&
        err.detail.includes("empty")
      ) {
        setErrorMessage("Draft content must not be empty.");
      } else if (err instanceof ApiError && err.status === 404) {
        setErrorMessage("This matter could not be found.");
      } else {
        setErrorMessage(
          "Unable to save the draft. Please try again or contact support if the problem persists.",
        );
      }
    },
  });

  function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!activeRequestId || !content.trim()) {
      setErrorMessage("Draft content must not be empty.");
      return;
    }
    setErrorMessage(null);
    createMutation.mutate();
  }

  if (requestsQuery.isPending) {
    return <LoadingState message="Loading drafts…" />;
  }

  if (requestsQuery.error || !requestsQuery.data) {
    return (
      <ErrorState
        message="Unable to load drafts."
        onRetry={() => void requestsQuery.refetch()}
      />
    );
  }

  if (requests.length === 0) {
    return (
      <div>
        <PageHeader
          eyebrow="Rasikh workspace"
          title="Drafts"
          description="Versioned legal drafts are produced per matter."
        />
        <Card>
          <EmptyState
            title="No drafts yet"
            description="There are no matters to draft against yet. Submit a request first."
          />
        </Card>
      </div>
    );
  }

  return (
    <div>
      {activeRequestId && (
        <RequestContextBar requestId={activeRequestId} />
      )}
      <PageHeader
        eyebrow="Rasikh workspace"
        title="Drafts Workspace"
        description="Versioned legal drafts per matter. New versions append to the matter's draft history and start awaiting approval."
      />

      <div style={{ display: "flex", gap: "16px", alignItems: "center", marginBottom: "16px" }}>
        <label className="auth-field" style={{ margin: 0, flexGrow: 1 }}>
          Matter / Request
          <select
            value={activeRequestId ?? ""}
            onChange={(e) => {
              setSelectedRequestId(e.target.value);
              setSelectedDraftId(null);
              setErrorMessage(null);
            }}
          >
            {requests.map((r) => (
              <option key={r.request_id} value={r.request_id}>
                {r.request_id}
                {r.org_id ? ` — ${r.org_id}` : ""}
                {r.request_type ? ` (${r.request_type})` : ""}
              </option>
            ))}
          </select>
        </label>
        {activeRequestId && (
          <Link
            className="button-secondary"
            to={`/requests/${encodeURIComponent(activeRequestId)}`}
            style={{ marginTop: "22px" }}
          >
            ← Back to Request ({activeRequestId})
          </Link>
        )}
      </div>

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

      {!draftsQuery.isPending && !draftsQuery.error && drafts.length === 0 && (
        <Card className="mt-md">
          <EmptyState
            title="No drafts for this matter"
            description="Generate an AI draft or create a new draft version below."
          />
        </Card>
      )}

      {drafts.length > 0 && (
        <Card className="mt-md">
          <p className="eyebrow">Draft versions for {activeRequestId}</p>
          <DataTable<DraftResponse>
            getKey={(d) => String(d.draft_id)}
            columns={[
              {
                label: "Version",
                value: (d) => (
                  <button
                    type="button"
                    className="text-link"
                    style={{
                      background: "none",
                      border: "none",
                      padding: 0,
                      cursor: "pointer",
                      font: "inherit",
                      fontWeight: (selectedDraft && String(selectedDraft.draft_id) === String(d.draft_id)) ? 700 : 400,
                    }}
                    onClick={() => setSelectedDraftId(String(d.draft_id))}
                  >
                    v{d.version}
                    {(selectedDraft && String(selectedDraft.draft_id) === String(d.draft_id)) ? " (active)" : ""}
                  </button>
                ),
              },
              {
                label: "Approval state",
                value: (d) => <StatusIndicator status={d.approval_state} />,
              },
              {
                label: "Created by",
                value: (d) => <code>{d.created_by ?? "AI Assistant"}</code>,
              },
              {
                label: "Created at",
                value: (d) => new Date(d.created_at).toLocaleString(),
              },
            ]}
            items={drafts}
          />
        </Card>
      )}

      {selectedDraft && (
        <Card className="mt-md">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <p className="eyebrow">Draft detail</p>
              <h2 style={{ marginTop: "4px", fontSize: "20px" }}>
                {activeRequestId} — Draft v{selectedDraft.version}
              </h2>
            </div>
            {activeRequestId && (
              <Link
                className="button-secondary"
                to={`/requests/${encodeURIComponent(activeRequestId)}`}
              >
                ← Back to Request
              </Link>
            )}
          </div>

          <dl className="ws-meta mt-md">
            <div>
              <dt>Request ID</dt>
              <dd><code>{activeRequestId}</code></dd>
            </div>
            <div>
              <dt>Draft ID</dt>
              <dd><code>{selectedDraft.draft_id}</code></dd>
            </div>
            <div>
              <dt>Request Type</dt>
              <dd>{activeRequest?.request_type ?? "Contract Review"}</dd>
            </div>
            <div>
              <dt>Organisation / Matter</dt>
              <dd>{activeRequest?.org_id ?? "Assigned Matter"}</dd>
            </div>
            <div>
              <dt>Draft Status</dt>
              <dd><StatusIndicator status={selectedDraft.approval_state} /></dd>
            </div>
            <div>
              <dt>Created By</dt>
              <dd><code>{selectedDraft.created_by ?? "AI Assistant"}</code></dd>
            </div>
            <div>
              <dt>Created At</dt>
              <dd>{new Date(selectedDraft.created_at).toLocaleString()}</dd>
            </div>
          </dl>

          <pre
            className="mt-md"
            style={{
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              background: "rgba(15, 44, 89, 0.04)",
              padding: "16px",
              borderRadius: "8px",
              fontFamily: "var(--font-mono, monospace)",
              fontSize: "14px",
              lineHeight: "1.6",
            }}
          >
            {selectedDraft.content}
          </pre>

          <div className="mt-md" style={{ display: "flex", gap: "12px" }}>
            {activeRequestId && (
              <Link
                className="button"
                to={`/requests/${encodeURIComponent(activeRequestId)}`}
              >
                Return to Request Workspace
              </Link>
            )}
            {activeRequestId && (
              <Link
                className="button-secondary"
                to={`/requests/${encodeURIComponent(activeRequestId)}/approvals`}
              >
                Go to Approvals Queue
              </Link>
            )}
          </div>
        </Card>
      )}

      {activeRequestId && (
        <Card className="mt-md">
          <p className="eyebrow">New draft version</p>
          <form onSubmit={handleCreate}>
            <label className="auth-field">
              Content
              <textarea
                rows={5}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Draft text for the next version…"
              />
            </label>
            <button
              type="submit"
              className="button"
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? "Saving…" : "Save draft"}
            </button>
            {createMutation.isPending && (
              <p className="auth-subtitle">Saving draft version…</p>
            )}
          </form>
        </Card>
      )}
    </div>
  );
}
