export type RequestType =
  | "contract_review"
  | "consultation"
  | "meeting_prep"
  | "obligation_check";

export interface RequestSubmit {
  request_id: string;
  /**
   * Optional: when omitted the backend derives it from the authenticated
   * user's mapped firm/team member. Do not require the user to type it.
   */
  requester_id?: string | null;
  raw_content: string;
  org_id?: string | null;
  request_type?: RequestType | null;
  created_at?: string | null;
}

export interface RequestResponse {
  request_id: string;
  requester_id: string;
  org_id: string | null;
  request_type: RequestType | null;
  status: string;
  created_at: string;
}

export interface ReviewRequest {
  member_id: string;
  org_id: string;
  contract_id?: string | null;
  reference_date?: string | null;
  suppressed_obligation_ids?: string[] | null;
}

export interface CitationResponse {
  citation_id: string;
  source_type: string;
  contract_clause_id: string | null;
  standard_clause_id: string | null;
}

export interface FindingResponse {
  finding_id: string;
  checklist_area: string | null;
  statement: string;
  grounded: boolean;
  risk_rating: string | null;
  sharia_sensitive_flag: boolean;
  tricky_case_type: string | null;
  citations: CitationResponse[];
}

export interface ObligationResponse {
  obligation_id: string;
  org_id: string;
  owner_id: string;
  due_date: string;
  stored_band: string;
  computed_band: string | null;
}

export interface EscalationResponse {
  escalation_id: string;
  obligation_id: string | null;
  request_id: string | null;
  reason: string;
  routed_to_id: string;
}

export interface ReviewResponse {
  request_id: string;
  access_decision: string;
  findings: FindingResponse[];
  obligations: ObligationResponse[];
  escalations: EscalationResponse[];
}

export interface DraftCreate {
  content: string;
  created_at?: string | null;
}

export interface DraftResponse {
  draft_id: string;
  request_id: string;
  content: string;
  version: number;
  approval_state: string;
  created_at: string;
  updated_at: string;
}

export interface ApprovalRequest {
  reviewer_id: string;
}

export interface ApprovalResponse {
  approval_decision_id: string;
  draft_id: string;
  reviewer_id: string;
  decision: string;
  draft_version: number;
  decided_at: string;
}

export interface ObligationSweepRequest {
  reference_date: string;
  org_id?: string | null;
  owner_id?: string | null;
  suppressed_obligation_ids?: string[] | null;
}

export interface ObligationSnapshotResponse extends ObligationResponse {}

export interface EscalationCreatedResponse {
  escalation_id: string;
  obligation_id: string;
  reason: string;
  routed_to_id: string;
}

export interface ObligationSweepResponse {
  reference_date: string;
  inspected: ObligationSnapshotResponse[];
  on_track: string[];
  reminder: string[];
  urgent: string[];
  overdue: string[];
  suppressed: string[];
  escalations_created: EscalationCreatedResponse[];
  already_escalated: string[];
  band_drift: [string, string, string][];
}

export interface AuditEventResponse {
  audit_event_id: string;
  request_id: string | null;
  event_type: string;
  actor_id: string | null;
  detail_reference: string | null;
  detail_json: Record<string, unknown> | null;
  occurred_at: string;
}

export interface RequestHistoryResponse {
  request_id: string;
  events: AuditEventResponse[];
}

export interface CountsResponse {
  requests_by_status: Record<string, number>;
  drafts_by_approval_state: Record<string, number>;
  obligations_by_band: Record<string, number>;
  items_awaiting_approval: number;
}

export interface HealthResponse {
  status: string;
}

// ---------------------------------------------------------------------------
// Authentication / authorization
// ---------------------------------------------------------------------------

export type UserRole = "member" | "admin";

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

/** Public representation of a user returned by POST /auth/register. */
export interface AuthUserResponse {
  id: number;
  email: string;
  is_active: boolean;
  role: UserRole;
  created_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

/** Public representation of the firm/team member an account maps to. */
export interface TeamMemberInfo {
  member_id: string;
  name: string;
  role: string;
  practice: string | null;
  can_approve: boolean;
}

/** Profile of the authenticated user, including their mapped team member. */
export interface MeResponse {
  id: number;
  email: string;
  role: UserRole;
  is_active: boolean;
  member_id: string | null;
  member: TeamMemberInfo | null;
}
