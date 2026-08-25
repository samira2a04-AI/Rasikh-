import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { listRequests, submitRequest } from "../api/requests";
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

  const requestsQuery = useQuery({
    queryKey: ["requests"],
    queryFn: () => listRequests(),
  });

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
        <h1>Submit a request</h1>
        <p className="page-description">
          Send a legal instruction to the intake workflow. Rasikh classifies it
          and creates a matter record you can track.
        </p>
      </header>

      <div className="card">
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

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <label className="auth-field">
              Request type
              <select
                value={requestType}
                onChange={(e) => setRequestType(e.target.value as "" | RequestType)}
              >
                {REQUEST_TYPES.map((t) => (
                  <option key={t.label} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="auth-field">
              Organisation (optional)
              <input
                type="text"
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                placeholder="org identifier"
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

      <h2 style={{ marginTop: "32px", fontSize: "20px" }}>Existing requests</h2>

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
        (requestsQuery.data.length === 0 ? (
          <div className="card" style={{ marginTop: "12px" }}>
            <p className="auth-subtitle">
              No requests yet. Submit your first instruction above.
            </p>
          </div>
        ) : (
          <div className="card" style={{ marginTop: "12px", overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["Request", "Status", "Type", "Requester", "Organisation", "Created"].map(
                    (heading) => (
                      <th
                        key={heading}
                        style={{
                          textAlign: "left",
                          padding: "8px",
                          borderBottom: "1px solid rgba(0,0,0,0.1)",
                          fontSize: "13px",
                        }}
                      >
                        {heading}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {requestsQuery.data.map((row) => (
                  <tr key={row.request_id}>
                    <td style={{ padding: "8px" }}>
                      <Link className="text-link" to={`/requests/${encodeURIComponent(row.request_id)}`}>
                        {row.request_id}
                      </Link>
                    </td>
                    <td style={{ padding: "8px" }}>
                      <StatusIndicator status={row.status} />
                    </td>
                    <td style={{ padding: "8px" }}>
                      {row.request_type?.replaceAll("_", " ") ?? "Unclassified"}
                    </td>
                    <td style={{ padding: "8px" }}>{row.requester_id}</td>
                    <td style={{ padding: "8px" }}>{row.org_id ?? "—"}</td>
                    <td style={{ padding: "8px" }}>
                      {new Date(row.created_at).toLocaleString()}
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
    </div>
  );
}
