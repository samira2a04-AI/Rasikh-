import { useState } from "react";
import { Link } from "react-router-dom";
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
import { StatusIndicator } from "../components/StatusIndicator";

export function DraftsPage() {
  const queryClient = useQueryClient();
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
  const selectedDraft =
    drafts.find((d) => d.draft_id === selectedDraftId) ?? null;

  const createMutation = useMutation({
    mutationFn: () =>
      createDraft(activeRequestId ?? "", {
        content,
      }),
    onSuccess: (created) => {
      setContent("");
      setErrorMessage(null);
      setSelectedDraftId(created.draft_id);
      void queryClient.invalidateQueries({ queryKey: ["drafts", activeRequestId] });
      // Draft creation records a draft_created/draft_edited audit event.
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
      <PageHeader
        eyebrow="Rasikh workspace"
        title="Drafts"
        description="Versioned legal drafts per matter. New versions append to the matter's draft history and start awaiting approval."
      />

      <label className="auth-field">
        Matter
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

      {!draftsQuery.isPending && !draftsQuery.error && drafts.length === 0 && (
        <Card className="mt-md">
          <EmptyState
            title="No drafts for this matter"
            description="Create the first draft version below."
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
                    }}
                    onClick={() => setSelectedDraftId(String(d.draft_id))}
                  >
                    v{d.version}
                    {selectedDraftId === d.draft_id ? " (selected)" : ""}
                  </button>
                ),
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

      {selectedDraft && (
        <Card className="mt-md">
          <p className="eyebrow">Draft detail</p>
          <h2 style={{ marginTop: "4px", fontSize: "20px" }}>
            {activeRequestId} — v{selectedDraft.version}
          </h2>
          <StatusIndicator status={selectedDraft.approval_state} />
          <pre
            className="mt-md"
            style={{
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              background: "rgba(15, 44, 89, 0.04)",
              padding: "12px",
              borderRadius: "8px",
            }}
          >
            {selectedDraft.content}
          </pre>
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
