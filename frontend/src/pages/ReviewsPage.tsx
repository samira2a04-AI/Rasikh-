import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { me } from "../api/auth";
import { ApiError } from "../api/client";
import { listRequests } from "../api/requests";
import { getReview, runReview } from "../api/reviews";
import type { RequestResponse } from "../api/types";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { StatusIndicator } from "../components/StatusIndicator";

/**
 * Per-row action cell. Checks whether a persisted review exists and renders
 * either "View Review" (navigates to the dedicated review page) or
 * "Run Review" (POSTs, then navigates only on success).
 */
function ReviewActionCell({
  request,
  memberId,
  runMutation,
}: {
  request: RequestResponse;
  memberId: string | null;
  runMutation: ReturnType<
    typeof useMutation<{ request: RequestResponse }, Error, unknown>
  >;
}) {
  const navigate = useNavigate();
  const existingQuery = useQuery({
    queryKey: ["review", request.request_id],
    queryFn: () => getReview(request.request_id),
    enabled: Boolean(memberId && request.org_id),
    retry: false,
    staleTime: 60_000,
  });

  if (!memberId) {
    return <span className="auth-subtitle">No linked member</span>;
  }
  if (request.status === "intake" || request.status === "insufficient") {
    return <span className="auth-subtitle">Needs clarification</span>;
  }
  if (!request.org_id) {
    return <span className="auth-subtitle">Missing organisation</span>;
  }

  if (existingQuery.data) {
    return (
      <Link
        className="button button--secondary"
        to={`/requests/${encodeURIComponent(request.request_id)}/review`}
      >
        View Review
      </Link>
    );
  }

  return (
    <button
      type="button"
      className="button"
      disabled={runMutation.isPending}
      onClick={(e) => {
        e.preventDefault();
        if (runMutation.isPending) return;
        runMutation.mutate(
          { request },
          {
            onSuccess: () =>
              navigate(
                `/requests/${encodeURIComponent(request.request_id)}/review`,
              ),
          },
        );
      }}
    >
      {runMutation.isPending ? "Analyzing contract…" : "Run Review"}
    </button>
  );
}

export function ReviewsPage() {
  const queryClient = useQueryClient();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: me });
  const requestsQuery = useQuery({
    queryKey: ["requests"],
    queryFn: () => listRequests(),
  });

  const memberId = meQuery.data?.member_id ?? null;

  const runMutation = useMutation({
    mutationFn: async (args: { request: RequestResponse }) =>
      runReview(args.request.request_id, {
        member_id: memberId ?? "",
        org_id: args.request.org_id ?? "",
      }),
    onSuccess: (data) => {
      setErrorMessage(null);
      void queryClient.invalidateQueries({
        queryKey: ["request-history", data.request_id],
      });
      void queryClient.invalidateQueries({
        queryKey: ["review", data.request_id],
      });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setErrorMessage(
            "Your account is not authorised to review this organisation's matters.",
          );
        } else if (err.status === 404) {
          setErrorMessage("This matter could not be found or reviewed.");
        } else {
          setErrorMessage(
            "Unable to run the review. Please try again or contact support if the problem persists.",
          );
        }
      } else {
        setErrorMessage(
          "Unable to run the review. Please try again or contact support if the problem persists.",
        );
      }
    },
  });

  if (requestsQuery.isPending || meQuery.isPending) {
    return <LoadingState message="Loading reviews…" />;
  }

  if (requestsQuery.error || meQuery.error || !requestsQuery.data) {
    return (
      <ErrorState
        message="Unable to load reviews."
        onRetry={() => {
          void requestsQuery.refetch();
          void meQuery.refetch();
        }}
      />
    );
  }

  const reviewable = requestsQuery.data;

  return (
    <div>
      <PageHeader
        eyebrow="Rasikh workspace"
        title="Reviews"
        description="Run and inspect contract reviews for submitted matters. Each review opens in its dedicated contract review workspace."
      />

      {errorMessage && (
        <p className="auth-error" role="alert">{errorMessage}</p>
      )}

      {runMutation.isPending && (
        <p className="auth-subtitle">Analyzing contract…</p>
      )}

      {reviewable.length === 0 ? (
        <Card>
          <EmptyState
            title="No reviews available"
            description="There are no working matters with an organisation assigned yet. Submit a request first, then run its review here."
          />
        </Card>
      ) : (
        <Card>
          <DataTable<RequestResponse>
            getKey={(r) => r.request_id}
            columns={[
              {
                label: "Matter",
                value: (r) => (
                  <Link
                    className="text-link"
                    to={`/requests/${encodeURIComponent(r.request_id)}`}
                  >
                    {r.request_id}
                  </Link>
                ),
              },
              {
                label: "Status",
                value: (r) => <StatusIndicator status={r.status} />,
              },
              {
                label: "Type",
                value: (r) => r.request_type?.replaceAll("_", " ") ?? "Unclassified",
              },
              { label: "Requester", value: (r) => r.requester_id },
              { label: "Organisation", value: (r) => r.org_id ?? "—" },
              {
                label: "Created",
                value: (r) => new Date(r.created_at).toLocaleString(),
              },
              {
                label: "Action",
                value: (r) => (
                  <ReviewActionCell
                    request={r}
                    memberId={memberId}
                    runMutation={runMutation as any}
                  />
                ),
              },
            ]}
            items={reviewable}
          />
        </Card>
      )}
    </div>
  );
}