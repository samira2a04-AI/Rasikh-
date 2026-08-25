"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRequest } from "../../api/requests";
import { getRequestHistory } from "../../api/history";
import { runReview } from "../../api/reviews";
import { me } from "../../api/auth";
import { ApiError } from "../../api/client";
import type { ReviewResponse } from "../../api/types";
import { Card, PageHeader, Tabs, StatusIndicator } from "../../components/ui";
import { Link, useParams } from "react-router-dom";
import { ReviewResults } from "./../reviews/ReviewResults";

export function RequestDetailFeature() {
  const { requestId = "" } = useParams<{ requestId: string }>();
  const queryClient = useQueryClient();
  const [activeReview, setActiveReview] = useState<ReviewResponse | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const requestQuery = useQuery({
    queryKey: ["request", requestId],
    queryFn: () => getRequest(requestId),
    enabled: Boolean(requestId),
  });

  const historyQuery = useQuery({
    queryKey: ["request-history", requestId],
    queryFn: () => getRequestHistory(requestId),
    enabled: Boolean(requestId),
  });

  const meQuery = useQuery({ queryKey: ["me"], queryFn: me });

  const runMutation = useMutation({
    mutationFn: () =>
      runReview(requestId, {
        member_id: meQuery.data?.member_id ?? "",
        org_id: requestQuery.data?.org_id ?? "",
      }),
    onSuccess: (data) => {
      setActiveReview(data);
      setReviewError(null);
      void queryClient.invalidateQueries({
        queryKey: ["request-history", requestId],
      });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setReviewError(
            "Your account is not authorised to review this organisation's matters.",
          );
        } else {
          setReviewError(
            "Unable to run the review. Please try again or contact support.",
          );
        }
      } else {
        setReviewError(
          "Unable to run the review. Please try again or contact support.",
        );
      }
    },
  });

  const { data, isPending, error, refetch } = requestQuery;

  if (isPending) {
    return <div className="state-panel">Loading request information...</div>;
  }

  if (error || !data) {
    return (
      <div className="state-panel">
        <strong>Unable to load this request.</strong>
        <button className="button mt-md" onClick={() => refetch()}>Try again</button>
      </div>
    );
  }

  const canReview = Boolean(data.org_id && meQuery.data?.member_id);

  return (
    <div>
      <PageHeader
        eyebrow="Matter record"
        title={data.request_id}
        description="A structured view of request context and workflow status."
      />

      <Tabs tabs={["Overview", "Review", "Drafts", "History"]} />

      <div className="detail-grid">
        <Card>
          <p className="eyebrow">Request details</p>
          <dl>
            {[
              ["Requester", data.requester_id],
              ["Organisation", data.org_id ?? "Not assigned"],
              ["Request type", data.request_type?.replaceAll("_", " ") ?? "Unclassified"],
              ["Created", new Date(data.created_at).toLocaleString()],
            ].map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
            <div>
              <dt>Status</dt>
              <dd><StatusIndicator status={data.status} /></dd>
            </div>
          </dl>
        </Card>

        <Card>
          <p className="eyebrow">Next workflow</p>
          <h2>Review this matter</h2>
          <p>Run the contract review for this request, then open the reviews workspace.</p>
          {canReview ? (
            <>
              <button
                type="button"
                className="button"
                disabled={runMutation.isPending}
                onClick={() => runMutation.mutate()}
              >
                {runMutation.isPending ? "Reviewing…" : "Run review"}
              </button>
              <Link className="text-link" to="/reviews">Open reviews workspace →</Link>
            </>
          ) : (
            <p className="auth-subtitle">
              A review requires both an assigned organisation and a linked firm
              member on your account.
            </p>
          )}
          {reviewError && <p className="auth-error" role="alert">{reviewError}</p>}
        </Card>
      </div>

      {activeReview && (
        <Card className="mt-md">
          <p className="eyebrow">Review result</p>
          <h2 style={{ marginTop: "4px", fontSize: "20px" }}>{activeReview.request_id}</h2>
          <ReviewResults review={activeReview} />
        </Card>
      )}

      <Card className="mt-md">
        <p className="eyebrow">Audit history</p>
        {historyQuery.isPending && <p>Loading audit events…</p>}
        {historyQuery.error && (
          <p>Unable to load the audit history for this matter.</p>
        )}
        {historyQuery.data &&
          (historyQuery.data.events.length === 0 ? (
            <p>No audit events recorded yet.</p>
          ) : (
            <dl>
              {historyQuery.data.events.map((event) => (
                <div key={event.audit_event_id}>
                  <dt>{event.event_type.replaceAll("_", " ")}</dt>
                  <dd>
                    {new Date(event.occurred_at).toLocaleString()}
                    {event.detail_reference ? ` — ${event.detail_reference}` : ""}
                  </dd>
                </div>
              ))}
            </dl>
          ))}
      </Card>
    </div>
  );
}
