import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { me } from "../api/auth";
import { ApiError } from "../api/client";
import { sweepObligations } from "../api/obligations";
import type { ObligationSweepResponse } from "../api/types";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { RequestContextBar } from "../components/RequestContextBar";
import { StatusIndicator } from "../components/StatusIndicator";

export function ObligationsPage() {
  const { requestId: routeRequestId } = useParams<{ requestId?: string }>();
  const [searchParams] = useSearchParams();
  const queryRequestId = searchParams.get("request");
  const contextRequestId = routeRequestId || queryRequestId || null;
  const meQuery = useQuery({ queryKey: ["me"], queryFn: me });
  const role = meQuery.data?.role ?? null;

  // The dataset's documented reference date (data README); overridable in-form.
  const [referenceDate, setReferenceDate] = useState("2026-07-01");
  const [orgFilter, setOrgFilter] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ObligationSweepResponse | null>(null);

  const sweepMutation = useMutation({
    mutationFn: () =>
      sweepObligations({
        reference_date: referenceDate,
        org_id: orgFilter.trim() ? orgFilter.trim() : null,
      }),
    onSuccess: (data) => {
      setResult(data);
      setErrorMessage(null);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 403) {
        setErrorMessage(
          "Running the obligation sweep is restricted to administrators.",
        );
      } else {
        setErrorMessage(
          "Unable to run the obligation sweep. Please try again or contact support if the problem persists.",
        );
      }
    },
  });

  function handleSweep(event: React.FormEvent) {
    event.preventDefault();
    setErrorMessage(null);
    sweepMutation.mutate();
  }

  if (meQuery.isPending) {
    return <LoadingState message="Loading obligations…" />;
  }

  if (meQuery.error) {
    return (
      <ErrorState
        message="Unable to load obligations."
        onRetry={() => void meQuery.refetch()}
      />
    );
  }
  if (role !== "admin") {
    return (
      <div>
        <PageHeader
          eyebrow="Rasikh workspace"
          title="Obligations"
          description="The obligation calendar and threshold sweeps."
        />
        <Card>
          <p className="auth-subtitle">
            The obligation calendar itself is not exposed through a listing API.
            The only obligation operation is the threshold sweep, which is
            restricted to administrators by the backend. Ask an administrator to
            run a sweep; its report covers every obligation's owner, deadline,
            and band.
          </p>
          {errorMessage && (
            <p className="auth-error" role="alert">{errorMessage}</p>
          )}
        </Card>
      </div>
    );
  }

  return (
    <div>
      {contextRequestId && (
        <RequestContextBar requestId={contextRequestId} />
      )}
      <PageHeader
        eyebrow="Rasikh workspace"
        title="Obligations"
        description="Run the rulebook 6.2 threshold sweep over the obligation calendar and inspect banding, deadlines, owners, and escalations."
      />

      {errorMessage && (
        <p className="auth-error" role="alert">{errorMessage}</p>
      )}

      <Card>
        <form onSubmit={handleSweep}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <label className="auth-field">
              Reference date
              <input
                type="date"
                value={referenceDate}
                onChange={(e) => setReferenceDate(e.target.value)}
                required
              />
            </label>
            <label className="auth-field">
              Organisation (optional)
              <input
                type="text"
                value={orgFilter}
                onChange={(e) => setOrgFilter(e.target.value)}
                placeholder="e.g. ORG-1007"
              />
            </label>
          </div>
          <button
            type="submit"
            className="button"
            disabled={sweepMutation.isPending}
          >
            {sweepMutation.isPending ? "Sweeping…" : "Run sweep"}
          </button>
          {sweepMutation.isPending && (
            <p className="auth-subtitle">Running the obligation sweep…</p>
          )}
        </form>
      </Card>

      {result && (
        <>
          <Card className="mt-md">
            <p className="eyebrow">
              Sweep report — reference date {result.reference_date}
            </p>
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginTop: "8px" }}>
              <StatusIndicator status={`on track: ${result.on_track.length}`} />
              <StatusIndicator status={`reminder: ${result.reminder.length}`} />
              <StatusIndicator status={`urgent: ${result.urgent.length}`} />
              <StatusIndicator status={`overdue: ${result.overdue.length}`} />
              <StatusIndicator status={`suppressed: ${result.suppressed.length}`} />
            </div>
            <p className="auth-subtitle" style={{ marginTop: "12px" }}>
              Escalations created: {result.escalations_created.length} · already
              escalated: {result.already_escalated.length} · band drift:
              {" "}
              {result.band_drift.length}
            </p>
          </Card>

          <Card className="mt-md">
            <p className="eyebrow">Inspected obligations ({result.inspected.length})</p>
            {result.inspected.length === 0 ? (
              <p className="auth-subtitle">No obligations matched this sweep.</p>
            ) : (
              <DataTable<ObligationSweepResponse["inspected"][number]>
                getKey={(o) => o.obligation_id}
                columns={[
                  { label: "Obligation", value: (o) => o.obligation_id },
                  { label: "Organisation", value: (o) => o.org_id },
                  { label: "Owner", value: (o) => o.owner_id },
                  { label: "Due date", value: (o) => o.due_date },
                  {
                    label: "Stored band",
                    value: (o) => <StatusIndicator status={o.stored_band} />,
                  },
                  {
                    label: "Computed band",
                    value: (o) =>
                      o.computed_band ? (
                        <StatusIndicator status={o.computed_band} />
                      ) : (
                        "—"
                      ),
                  },
                  {
                    label: "Drift",
                    value: (o) =>
                      o.computed_band && o.computed_band !== o.stored_band
                        ? "yes"
                        : "no",
                  },
                ]}
                items={result.inspected}
              />
            )}
          </Card>

          {result.escalations_created.length > 0 && (
            <Card className="mt-md">
              <p className="eyebrow" style={{ color: "var(--red-11, #e5484d)" }}>
                Escalations created ({result.escalations_created.length})
              </p>
              <p className="auth-subtitle" style={{ marginBottom: "12px" }}>
                Rulebook 6.2 threshold triggered: overdue/urgent obligations have been hard-escalated to senior counsel.
              </p>
              <DataTable<ObligationSweepResponse["escalations_created"][number]>
                getKey={(esc) => esc.escalation_id}
                columns={[
                  { label: "Escalation ID", value: (esc) => <code>{esc.escalation_id}</code> },
                  { label: "Obligation ID", value: (esc) => <code>{esc.obligation_id}</code> },
                  {
                    label: "Reason",
                    value: (esc) => <StatusIndicator status={esc.reason} />,
                  },
                  { label: "Routed Counsel", value: (esc) => <code>{esc.routed_to_id}</code> },
                ]}
                items={result.escalations_created}
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
