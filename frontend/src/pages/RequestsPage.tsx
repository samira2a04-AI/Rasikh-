import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { getRequestRegistry, submitRequest } from "../api/requests";
import type { RequestType } from "../api/types";
import { StatusIndicator } from "../components/StatusIndicator";

const REQUEST_TYPES: { value: "" | RequestType; label: string }[] = [
  { value: "", label: "Classify automatically" },
  { value: "contract_review", label: "Contract review" },
  { value: "consultation", label: "Consultation" },
  { value: "meeting_prep", label: "Meeting preparation" },
  { value: "obligation_check", label: "Obligation check" },
];

function newRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function RequestsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [rawContent, setRawContent] = useState("");
  const [requestType, setRequestType] = useState<"" | RequestType>("");
  const [orgId, setOrgId] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const requestsQuery = useQuery({
    queryKey: ["requests-registry"],
    queryFn: () => getRequestRegistry(),
  });

  // Client-side search & filter over the registry (all data is already loaded).
  const filteredRows = useMemo(() => {
    const rows = requestsQuery.data ?? [];
    const q = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (typeFilter && row.request.request_type !== typeFilter) return false;
      if (statusFilter && row.request.status !== statusFilter) return false;
      if (!q) return true;
      const haystack = [
        row.request.request_id,
        row.request.request_type ?? "",
        row.request.org_id ?? "",
        row.request.status,
        row.request.requester_id,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [requestsQuery.data, search, typeFilter, statusFilter]);

  const availableStatuses = useMemo(
    () => [...new Set((requestsQuery.data ?? []).map((r) => r.request.status))].sort(),
    [requestsQuery.data],
  );

  const mutation = useMutation({
    mutationFn: submitRequest,
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["requests"] });
      navigate(`/requests/${encodeURIComponent(created.request_id)}`, {
        replace: true,
      });
    },
    onError: (err) => {
      if (
        err instanceof ApiError &&
        err.status === 400 &&
        typeof err.detail === "string" &&
        err.detail.includes("requester_id")
      ) {
        setErrorMessage(
          "Your account is not mapped to a firm team member. Contact an administrator.",
        );
      } else if (
        err instanceof ApiError &&
        err.status === 404 &&
        typeof err.detail === "string" &&
        err.detail.includes("org_id")
      ) {
        setErrorMessage("Unknown organisation ID. Leave it empty or correct it.");
      } else if (
        err instanceof ApiError &&
        err.status === 503
      ) {
        setErrorMessage("AI classification is temporarily unavailable. Please try again shortly.");
      } else {
        setErrorMessage(
          "Unable to submit the request. Please try again or contact support if the problem persists.",
        );
      }
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setErrorMessage(null);
    mutation.mutate({
      request_id: newRequestId(),
      raw_content: rawContent.trim(),
      org_id: orgId.trim() ? orgId.trim() : null,
      request_type: requestType ? requestType : null,
    });
  }

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">Rasikh workspace</p>
        <h1>Requests &amp; matters</h1>
        <p className="page-description">
          The request registry: every instruction submitted to the intake
          workflow, with its derived AI result and output counts. Open a
          request to see its unified detail view.
        </p>
      </header>

      <h2 style={{ fontSize: "20px" }}>Request registry</h2>

      <div className="ws-toolbar">
        <input
          type="search"
          className="ws-search"
          placeholder="Search by request ID, organisation, requester…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search requests"
        />
        <select
          className="ws-filter"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          aria-label="Filter by request type"
        >
          <option value="">All types</option>
          <option value="contract_review">Contract review</option>
          <option value="consultation">Consultation</option>
          <option value="meeting_prep">Meeting preparation</option>
          <option value="obligation_check">Obligation check</option>
        </select>
        <select
          className="ws-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {availableStatuses.map((s) => (
            <option key={s} value={s}>
              {s.replaceAll("_", " ")}
            </option>
          ))}
        </select>
        {(search || typeFilter || statusFilter) && (
          <button
            type="button"
            className="button-secondary ws-clear"
            onClick={() => {
              setSearch("");
              setTypeFilter("");
              setStatusFilter("");
            }}
          >
            Clear
          </button>
        )}
      </div>

      {requestsQuery.isPending && <p className="auth-subtitle">Loading requests…</p>}

      {requestsQuery.error && (
        <div className="card" style={{ marginTop: "12px" }}>
          <p className="auth-error" role="alert">
            Unable to load requests.
          </p>
          <button
            type="button"
            className="button"
            onClick={() => void requestsQuery.refetch()}
          >
            Try again
          </button>
        </div>
      )}

      {requestsQuery.data &&
        (filteredRows.length === 0 ? (
          <div className="card" style={{ marginTop: "12px" }}>
            <p className="auth-subtitle">
              {requestsQuery.data.length === 0
                ? "No requests yet. Submit your first instruction below."
                : "No requests match the current search or filters."}
            </p>
          </div>
        ) : (
          <div className="card ws-table-card">
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["Request ID", "Org / Matter", "Request Type", "Decision / Status", "Requester", "Outputs"].map(
                    (heading) => (
                      <th
                        key={heading}
                        style={{
                          textAlign: "left",
                          padding: "10px 8px",
                          borderBottom: "1px solid rgba(0,0,0,0.1)",
                          fontSize: "13px",
                          fontWeight: 600,
                        }}
                      >
                        {heading}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.request.request_id} style={{ borderBottom: "1px solid rgba(0,0,0,0.05)" }}>
                    <td style={{ padding: "10px 8px" }}>
                      <Link className="text-link" to={`/requests/${encodeURIComponent(row.request.request_id)}`}>
                        <code>{row.request.request_id}</code>
                      </Link>
                    </td>
                    <td style={{ padding: "10px 8px" }}>
                      {row.request.org_id ? <strong>{row.request.org_id}</strong> : <span className="auth-subtitle">Unassigned</span>}
                    </td>
                    <td style={{ padding: "10px 8px" }}>
                      <span className="ws-sev" style={{ background: "rgba(0,0,0,0.04)", padding: "2px 6px", borderRadius: "4px", fontSize: "12px" }}>
                        {row.request.request_type ? row.request.request_type.replaceAll("_", " ") : "Unclassified"}
                      </span>
                    </td>
                    <td style={{ padding: "10px 8px" }}>
                      <span
                        className="ws-sev"
                        style={{
                          background: "rgba(0,0,0,0.06)",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 600,
                          color: "var(--color-fg-default)",
                        }}
                      >
                        {row.decision ?? row.request.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: "10px 8px" }}>
                      <code>{row.request.requester_id}</code>
                    </td>
                    <td style={{ padding: "10px 8px", fontSize: "13px" }}>
                      <span style={{ display: "inline-flex", gap: "8px", alignItems: "center" }}>
                        {row.has_answer && <span title="AI Answer generated">✓ Answer</span>}
                        {row.draft_count > 0 && <Link className="text-link" to={`/requests/${encodeURIComponent(row.request.request_id)}/drafts`}>{row.draft_count} draft(s)</Link>}
                        {row.finding_count > 0 && <Link className="text-link" to={`/requests/${encodeURIComponent(row.request.request_id)}/review`}>{row.finding_count} finding(s)</Link>}
                        {row.approval_count > 0 && <Link className="text-link" to={`/requests/${encodeURIComponent(row.request.request_id)}/approvals`}>{row.approval_count} approval(s)</Link>}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}

      <p className="auth-subtitle" style={{ marginTop: "16px" }}>
        Matter records are created per submission; open one from here or from
        its direct link to follow reviews, drafts, and its audit history.
      </p>

      <h2 style={{ marginTop: "32px", fontSize: "20px" }}>Submit a new request</h2>

      <div className="card" style={{ marginTop: "12px" }}>
        <form onSubmit={handleSubmit}>
          <label className="auth-field">
            Instruction
            <textarea
              value={rawContent}
              onChange={(e) => setRawContent(e.target.value)}
              required
              minLength={3}
              rows={6}
              placeholder="e.g. Review the attached distribution agreement for compliance risks before signature."
            />
          </label>

          <div style={{ marginTop: "12px" }}>
            <label className="auth-field">
              Organisation (optional)
              <input
                type="text"
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                placeholder="e.g. ORG-1007"
              />
            </label>
          </div>

          <p className="auth-subtitle">
            This request will be recorded against your firm identity
            (automatically determined from your login).
          </p>

          {mutation.isPending && <p className="auth-subtitle">Submitting…</p>}
          {errorMessage && (
            <p className="auth-error" role="alert">{errorMessage}</p>
          )}

          <button
            type="submit"
            className="button"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Submitting…" : "Submit request"}
          </button>
        </form>
      </div>
    </div>
  );
}
