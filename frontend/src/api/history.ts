import { fetchJson } from "./client";
import type { RequestHistoryResponse } from "./types";

export function getRequestHistory(
  requestId: string,
): Promise<RequestHistoryResponse> {
  return fetchJson<RequestHistoryResponse>(
    `/requests/${encodeURIComponent(requestId)}/history`,
  );
}
