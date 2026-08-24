import { fetchJson, jsonBody } from "./client";
import type { ReviewRequest, ReviewResponse } from "./types";

export function runReview(
  requestId: string,
  body: ReviewRequest,
): Promise<ReviewResponse> {
  return fetchJson<ReviewResponse>(
    `/requests/${encodeURIComponent(requestId)}/review`,
    { method: "POST", ...jsonBody(body) },
  );
}
