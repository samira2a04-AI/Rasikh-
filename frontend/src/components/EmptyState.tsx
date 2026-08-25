import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, icon, className = "" }: EmptyStateProps) {
  return (
    <div className={`empty-state ${className}`}>
      <div
        className="empty-state-icon"
        style={{
          background: icon
            ? "none"
            : `url("data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22${encodeURIComponent(designTokens.colors.text.secondary)}%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22%3E%3Cpath d=%22M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z%22/%3E%3C/svg%3E") center/contain no-repeat`,
        }}
      >
        {icon}
      </div>
      <h3 className="empty-state-title">{title}</h3>
      <p>{description}</p>
    </div>
  );
}