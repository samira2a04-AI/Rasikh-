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

/**
 * Ask the backend to generate an AI draft from the request's completed
 * analysis and human-reviewed findings. The resulting version enters
 * "awaiting_approval" and flows through the normal approval workflow.
 */
export function generateAIDraft(requestId: string): Promise<DraftResponse> {
  return fetchJson<DraftResponse>(
    `/requests/${encodeURIComponent(requestId)}/drafts/generate`,
    { method: "POST" },
  );
}
