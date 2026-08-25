import { fetchJson } from "./client";
import type { AuditEventResponse, RequestHistoryResponse } from "./types";

export function getRequestHistory(
  requestId: string,
): Promise<RequestHistoryResponse> {
  return fetchJson<RequestHistoryResponse>(
    `/requests/${encodeURIComponent(requestId)}/history`,
  );
}

export interface AuditQuery {
  event_type?: string;
  request_id?: string;
  actor_id?: string;
  limit?: number;
  offset?: number;
}

/** Global audit feed across all matters, newest first (GET /audit). */
export function listAuditEvents(query: AuditQuery = {}): Promise<AuditEventResponse[]> {
  const params = new URLSearchParams();
  if (query.event_type?.trim()) params.set("event_type", query.event_type.trim());
  if (query.request_id?.trim()) params.set("request_id", query.request_id.trim());
  if (query.actor_id?.trim()) params.set("actor_id", query.actor_id.trim());
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return fetchJson<AuditEventResponse[]>(`/audit${qs ? `?${qs}` : ""}`);
}
