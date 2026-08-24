import { fetchJson, jsonBody } from "./client";
import type { ApprovalRequest, ApprovalResponse } from "./types";

function decideDraft(
  draftId: string,
  decision: "approve" | "reject",
  body: ApprovalRequest,
): Promise<ApprovalResponse> {
  return fetchJson<ApprovalResponse>(
    `/drafts/${encodeURIComponent(draftId)}/${decision}`,
    { method: "POST", ...jsonBody(body) },
  );
}

export function approveDraft(
  draftId: string,
  body: ApprovalRequest,
): Promise<ApprovalResponse> {
  return decideDraft(draftId, "approve", body);
}

export function rejectDraft(
  draftId: string,
  body: ApprovalRequest,
): Promise<ApprovalResponse> {
  return decideDraft(draftId, "reject", body);
}
