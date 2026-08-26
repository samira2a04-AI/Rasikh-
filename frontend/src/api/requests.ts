import { fetchJson, jsonBody } from "./client";
import type {
  RequestRegistryRow,
  RequestResolve,
  RequestResponse,
  RequestSubmit,
  RequestView,
} from "./types";

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

export function getRequestView(requestId: string): Promise<RequestView> {
  return fetchJson<RequestView>(`/requests/${encodeURIComponent(requestId)}/view`);
}

export function getRequestRegistry(
  limit = 50,
  offset = 0,
): Promise<RequestRegistryRow[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return fetchJson<RequestRegistryRow[]>(`/requests/registry?${params.toString()}`);
}

export function resolveRequest(requestId: string, body: RequestResolve): Promise<RequestResponse> {
  return fetchJson<RequestResponse>(`/requests/${encodeURIComponent(requestId)}/resolve`, {
    method: "PATCH",
    ...jsonBody(body),
  });
}
