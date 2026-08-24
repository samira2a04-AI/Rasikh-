"use client";

import { useQuery } from "@tanstack/react-query";
import { getRequest } from "../../api/requests";
import { Card, PageHeader, Tabs, StatusIndicator } from "../../components/ui";
import { Link, useParams } from "react-router-dom";

export function RequestDetailFeature() {
  const { requestId = "" } = useParams<{ requestId: string }>();
  
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["request", requestId],
    queryFn: () => getRequest(requestId),
    enabled: Boolean(requestId),
  });

  if (isPending) {
    return <div className="state-panel">Loading request information...</div>;
  }

  if (error || !data) {
    return <div className="state-panel"><strong>Unable to load this request.</strong><button className="button mt-md" onClick={() => refetch()}>Try again</button></div>;
  }

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
          <p>Review findings, draft work, and audit history remain connected to this record.</p>
          <Link className="text-link" to="/reviews">Open reviews workspace →</Link>
        </Card>
      </div>
    </div>
  );
}