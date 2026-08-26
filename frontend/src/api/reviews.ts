import { fetchJson, jsonBody } from "./client";
import type { FindingResponse, ReviewRequest, ReviewResponse } from "./types";

export function runReview(
  requestId: string,
  body: ReviewRequest,
): Promise<ReviewResponse> {
  return fetchJson<ReviewResponse>(
    `/requests/${encodeURIComponent(requestId)}/review`,
    { method: "POST", ...jsonBody(body) },
  );
}

export function getReview(requestId: string): Promise<ReviewResponse> {
  return fetchJson<ReviewResponse>(
    `/requests/${encodeURIComponent(requestId)}/review`,
  );
}

export function reviewFinding(
  requestId: string,
  findingId: string,
  body: { status?: string; reviewer_notes?: string },
): Promise<FindingResponse> {
  return fetchJson<FindingResponse>(
    `/requests/${encodeURIComponent(requestId)}/findings/${encodeURIComponent(findingId)}/review`,
    { method: "PATCH", ...jsonBody(body) },
  );
}
