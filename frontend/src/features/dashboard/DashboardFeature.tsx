import { useQuery } from "@tanstack/react-query";
import { getCounts } from "../../api/counts";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { designTokens } from "../../tokens";

export function DashboardFeature() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["counts"],
    queryFn: getCounts,
  });

  if (isPending) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: designTokens.spacing.xxl }}>
        <div
          style={{
            width: "40px",
            height: "40px",
            border: `3px solid ${designTokens.colors.border.line}`,
            borderTop: `3px solid ${designTokens.colors.primary.navy}`,
            borderRadius: "50%",
            animation: "spin 1s linear infinite",
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: designTokens.spacing.xxl,
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: "48px",
            height: "48px",
            backgroundColor: designTokens.colors.semantic.danger,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: designTokens.spacing.md,
          }}
        >
          <span style={{ color: "white", fontSize: "24px" }}>!</span>
        </div>
        <h3
          style={{
            fontSize: "24px",
            fontWeight: "500",
            color: designTokens.colors.text.primary,
            marginBottom: designTokens.spacing.sm,
          }}
        >
          Unable to load dashboard data
        </h3>
        <p style={{ color: designTokens.colors.text.secondary, marginBottom: designTokens.spacing.lg }}>
          Please try again or contact support if the problem persists.
        </p>
        <button
          onClick={() => refetch()}
          style={{
            backgroundColor: designTokens.colors.primary.navy,
            color: "white",
            border: "none",
            borderRadius: "8px",
            padding: `${designTokens.spacing.sm} ${designTokens.spacing.md}`,
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const total = (obj: Record<string, number>) => Object.values(obj).reduce((a, b) => a + b, 0);

  return (
    <div style={{ display: "grid", gap: designTokens.spacing.xl }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
          gap: designTokens.spacing.lg,
        }}
      >
        <Card className="metric-card">
          <p style={{ color: designTokens.colors.text.secondary, fontSize: "14px", marginBottom: designTokens.spacing.xs }}>
            Requests in workflow
          </p>
          <strong style={{ fontSize: "32px", color: designTokens.colors.primary.navy }}>
            {total(data.requests_by_status)}
          </strong>
        </Card>
        <Card className="metric-card">
          <p style={{ color: designTokens.colors.text.secondary, fontSize: "14px", marginBottom: designTokens.spacing.xs }}>
            Awaiting approval
          </p>
          <strong style={{ fontSize: "32px", color: designTokens.colors.primary.navy }}>
            {data.items_awaiting_approval}
          </strong>
        </Card>
        <Card className="metric-card">
          <p style={{ color: designTokens.colors.text.secondary, fontSize: "14px", marginBottom: designTokens.spacing.xs }}>
            Tracked obligations
          </p>
          <strong style={{ fontSize: "32px", color: designTokens.colors.primary.navy }}>
            {total(data.obligations_by_band)}
          </strong>
        </Card>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
          gap: designTokens.spacing.lg,
        }}
      >
        <Card>
          <h2
            style={{
              fontSize: "20px",
              fontWeight: "500",
              color: designTokens.colors.text.primary,
              marginBottom: designTokens.spacing.md,
            }}
          >
            Request status
          </h2>
          {Object.entries(data.requests_by_status).map(([k, v]) => (
            <div
              key={k}
              style={{
                display: "flex",
                justifyContent: "space-between",
                margin: "8px 0",
                padding: "8px 0",
                borderBottom: `1px solid ${designTokens.colors.border.line}`,
              }}
            >
              <span style={{ color: designTokens.colors.text.primary }}>{k.replaceAll("_", " ")}</span>
              <b style={{ color: designTokens.colors.primary.navy }}>{v}</b>
            </div>
          ))}
        </Card>
        <Card>
          <h2
            style={{
              fontSize: "20px",
              fontWeight: "500",
              color: designTokens.colors.text.primary,
              marginBottom: designTokens.spacing.md,
            }}
          >
            Obligation bands
          </h2>
          {Object.entries(data.obligations_by_band).map(([k, v]) => (
            <div
              key={k}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: `${designTokens.spacing.sm} 0`,
                borderBottom: `1px solid ${designTokens.colors.border.line}`,
              }}
            >
              <span style={{ color: designTokens.colors.text.primary }}>{k.replaceAll("_", " ")}</span>
              <b style={{ color: designTokens.colors.primary.navy }}>{v}</b>
            </div>
          ))}
        </Card>
      </div>

      <Card>
        <EmptyState
          title="Recent activity is matter-specific"
          description="Open a request record to review its audit history. A global activity feed is not provided by the current API."
        />
      </Card>
    </div>
  );
}
