import { fetchJson, jsonBody } from "./client";
import type { RequestResponse, RequestSubmit } from "./types";

export function submitRequest(body: RequestSubmit): Promise<RequestResponse> {
  return fetchJson<RequestResponse>("/requests", {
    method: "POST",
    ...jsonBody(body),
  });
}

export function getRequest(requestId: string): Promise<RequestResponse> {
  return fetchJson<RequestResponse>(`/requests/${encodeURIComponent(requestId)}`);
}
