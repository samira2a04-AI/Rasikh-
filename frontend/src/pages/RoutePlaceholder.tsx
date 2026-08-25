import { Card, EmptyState, PageHeader } from "../components/ui";
import { useAuth } from "../auth/AuthContext";

const pageDescriptions: Record<string, string> = {
  Requests: "Track incoming legal requests and active matters.",
  Reviews: "Review submitted requests before drafting begins.",
  Drafts: "Manage and review generated legal drafts.",
  Approvals: "Approve or return drafts awaiting sign-off.",
  Obligations: "Monitor compliance obligations and reminders.",
  History: "Inspect the audit history of requests and matters.",
};

export function RoutePlaceholder({ title }: { title: string }) {
  const { role } = useAuth();
  const description =
    pageDescriptions[title] ?? "This workspace is part of the Rasikh platform.";

  return (
    <>
      <PageHeader eyebrow="Rasikh workspace" title={title} description={description} />
      <Card>
        <EmptyState
          title={`No ${title.toLowerCase()} yet`}
          description="This feature is prepared for an upcoming implementation phase. Items will appear here once it becomes available."
        />
        {title === "Obligations" && role !== "admin" && (
          <p className="role-note">
            Running the obligation sweep is restricted to administrators.
          </p>
        )}
      </Card>
    </>
  );
}
