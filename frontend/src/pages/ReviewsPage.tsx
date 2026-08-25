import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { me } from "../api/auth";
import { ApiError } from "../api/client";
import { listRequests } from "../api/requests";
import { runReview } from "../api/reviews";
import type { RequestResponse, ReviewResponse } from "../api/types";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { StatusIndicator } from "../components/StatusIndicator";
import { ReviewResults } from "../features/reviews/ReviewResults";

export function ReviewsPage() {
  const queryClient = useQueryClient();
  const [activeReview, setActiveReview] = useState<ReviewResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: me });
  const requestsQuery = useQuery({
    queryKey: ["requests"],
    queryFn: () => listRequests(),
  });

  const memberId = meQuery.data?.member_id ?? null;

  const runMutation = useMutation({
    mutationFn: (args: { request: RequestResponse }) =>
      runReview(args.request.request_id, {
        member_id: memberId ?? "",
        org_id: args.request.org_id ?? "",
      }),
    onSuccess: (data) => {
      setActiveReview(data);
      setErrorMessage(null);
      void queryClient.invalidateQueries({
        queryKey: ["request-history", data.request_id],
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

  function handleReview(request: RequestResponse) {
    if (!memberId || !request.org_id) return;
    setErrorMessage(null);
    runMutation.mutate({ request });
  }

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

  const reviewable = requestsQuery.data.filter((r) => r.org_id);

  return (
    <div>
      <PageHeader
        eyebrow="Rasikh workspace"
        title="Reviews"
        description="Run and inspect contract reviews for submitted matters. Each review is tied to a request and its organisation."
      />

      {errorMessage && (
        <p className="auth-error" role="alert">{errorMessage}</p>
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
                value: (r) =>
                  memberId ? (
                    <button
                      type="button"
                      className="button"
                      disabled={runMutation.isPending}
                      onClick={() => handleReview(r)}
                    >
                      {runMutation.isPending ? "Reviewing…" : "Run review"}
                    </button>
                  ) : (
                    <span className="auth-subtitle">No linked member</span>
                  ),
              },
            ]}
            items={reviewable}
          />
        </Card>
      )}

      <p className="auth-subtitle" style={{ marginTop: "12px" }}>
        Open any matter from the table to see its request details and audit history.
      </p>

      {runMutation.isPending && <p className="auth-subtitle">Running review…</p>}

      {activeReview && (
        <Card className="mt-md">
          <p className="eyebrow">Review result</p>
          <h2 style={{ marginTop: "4px", fontSize: "20px" }}>
            {activeReview.request_id}
          </h2>
          <ReviewResults review={activeReview} />
        </Card>
      )}
    </div>
  );
}
