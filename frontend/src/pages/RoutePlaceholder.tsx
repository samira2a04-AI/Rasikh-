import { EmptyState, PageHeader } from "../components/ui";

export function RoutePlaceholder({ title }: { title: string }) {
  return (
    <><PageHeader eyebrow="Rasikh workspace" title={title} /><EmptyState title={`${title} workspace`} description="This workspace is prepared for the next implementation phase." /></>
  );
}
