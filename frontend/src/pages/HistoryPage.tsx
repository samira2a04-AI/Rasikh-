import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { listAuditEvents } from "../api/history";
import type { AuditEventResponse } from "../api/types";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { RequestContextBar } from "../components/RequestContextBar";

const PAGE_SIZE = 25;

export function HistoryPage() {
  // Request context: /history?request={id} comes from the Unified Request
  // Workspace and pre-fills the request filter (refresh-safe).
  const [searchParams] = useSearchParams();
  const contextRequestId = searchParams.get("request");
  const [eventType, setEventType] = useState("");
  const [requestFilter, setRequestFilter] = useState(contextRequestId ?? "");
  const [actorFilter, setActorFilter] = useState("");
  const [offset, setOffset] = useState(0);

  const auditQuery = useQuery({
    queryKey: [
      "audit",
      eventType.trim(),
      requestFilter.trim(),
      actorFilter.trim(),
      offset,
    ],
    queryFn: () =>
      listAuditEvents({
        event_type: eventType,
        request_id: requestFilter,
        actor_id: actorFilter,
        limit: PAGE_SIZE,
        offset,
      }),
    placeholderData: keepPreviousData,
  });

  const events: AuditEventResponse[] = auditQuery.data ?? [];

  return (
    <div>
      {contextRequestId && (
        <RequestContextBar requestId={contextRequestId} />
      )}
      <PageHeader
        eyebrow="Rasikh workspace"
        title="History"
        description="The append-only audit trail across all matters and obligation escalations, newest first."
      />

      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setOffset(0);
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <label className="auth-field">
              Event type
              <input
                type="text"
                value={eventType}
                onChange={(e) => {
                  setEventType(e.target.value);
                  setOffset(0);
                }}
                placeholder="e.g. escalated, draft_edited"
              />
            </label>
            <label className="auth-field">
              Actor (member ID)
              <input
                type="text"
                value={actorFilter}
                onChange={(e) => {
                  setActorFilter(e.target.value);
                  setOffset(0);
                }}
                placeholder="optional — e.g. L-02"
              />
            </label>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "16px", alignItems: "end" }}>
            <label className="auth-field">
              Matter (request ID)
              <input
                type="text"
                value={requestFilter}
                onChange={(e) => {
                  setRequestFilter(e.target.value);
                  setOffset(0);
                }}
                placeholder="optional — e.g. L-C-003"
              />
            </label>
            <button type="submit" className="button">Apply filters</button>
          </div>
        </form>
      </Card>
      {auditQuery.isPending && <LoadingState message="Loading audit history…" />}

      {auditQuery.isError && (
        <ErrorState
          message="Unable to load the audit history."
          onRetry={() => void auditQuery.refetch()}
        />
      )}

      {auditQuery.isSuccess && events.length === 0 && (
        <Card className="mt-md">
          <p className="auth-subtitle">
            No audit events match the current filters.
          </p>
        </Card>
      )}

      {auditQuery.isSuccess && events.length > 0 && (
        <Card className="mt-md">
          <DataTable<AuditEventResponse>
            getKey={(e) => String(e.audit_event_id)}
            columns={[
              {
                label: "Event",
                value: (e) => e.event_type.replaceAll("_", " "),
              },
              {
                label: "Occurred",
                value: (e) => new Date(e.occurred_at).toLocaleString(),
              },
              {
                label: "Actor",
                value: (e) => e.actor_id ?? "system",
              },
              {
                label: "Matter",
                value: (e) =>
                  e.request_id ? (
                    <Link
                      className="text-link"
                      to={`/requests/${encodeURIComponent(e.request_id)}`}
                    >
                      {e.request_id}
                    </Link>
                  ) : (
                    <span title="Obligation-level event: no matter attached">
                      — (no matter)
                    </span>
                  ),
              },
              {
                label: "Reference",
                value: (e) => e.detail_reference ?? "—",
              },
              {
                label: "Metadata",
                value: (e) =>
                  e.detail_json
                    ? Object.entries(e.detail_json)
                        .map(([k, v]) => `${k}: ${String(v)}`)
                        .join(", ")
                    : "—",
              },
            ]}
            items={events}
          />

          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "center",
              marginTop: "16px",
            }}
          >
            <button
              type="button"
              className="logout-button"
              disabled={offset === 0 || auditQuery.isFetching}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              ← Previous
            </button>
            <span className="auth-subtitle">
              Showing {offset + 1}–{offset + events.length}
            </span>
            <button
              type="button"
              className="logout-button"
              disabled={events.length < PAGE_SIZE || auditQuery.isFetching}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
