import { fetchJson, jsonBody } from "./client";
import type { RequestResponse, RequestSubmit } from "./types";

export function submitRequest(body: RequestSubmit): Promise<RequestResponse> {
  return fetchJson<RequestResponse>("/requests", {
    method: "POST",
    ...jsonBody(body),
  });
}

export function listRequests(
  limit = 50,
  offset = 0,
): Promise<RequestResponse[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return fetchJson<RequestResponse[]>(`/requests?${params.toString()}`);
}

export function getRequest(requestId: string): Promise<RequestResponse> {
  return fetchJson<RequestResponse>(`/requests/${encodeURIComponent(requestId)}`);
}
