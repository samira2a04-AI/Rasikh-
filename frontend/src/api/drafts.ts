import { fetchJson, jsonBody } from "./client";
import type { DraftCreate, DraftResponse } from "./types";

export function createDraft(
  requestId: string,
  body: DraftCreate,
): Promise<DraftResponse> {
  return fetchJson<DraftResponse>(
    `/requests/${encodeURIComponent(requestId)}/drafts`,
    { method: "POST", ...jsonBody(body) },
  );
}

export function listDrafts(requestId: string): Promise<DraftResponse[]> {
  return fetchJson<DraftResponse[]>(
    `/requests/${encodeURIComponent(requestId)}/drafts`,
  );
}

export function getDraft(
  requestId: string,
  draftId: string,
): Promise<DraftResponse> {
  return fetchJson<DraftResponse>(
    `/requests/${encodeURIComponent(requestId)}/drafts/${encodeURIComponent(draftId)}`,
  );
}
