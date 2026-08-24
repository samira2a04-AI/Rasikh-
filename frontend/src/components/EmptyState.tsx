"use client";

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
    <div
      className={`empty-state ${className}`}
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
        className="empty-state-icon"
        style={{
          width: "48px",
          height: "48px",
          marginBottom: designTokens.spacing.md,
          opacity: 0.5,
          background: icon ? "none" : `url("data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22${encodeURIComponent(designTokens.colors.text.secondary)}%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22%3E%3Cpath d=%22M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z%22/%3E%3C/svg%3E") center/contain no-repeat`,
        }}
      >
        {icon}
      </div>
      <h3
        style={{
          fontSize: designTokens.typography.fontSize.h2,
          fontWeight: designTokens.typography.fontWeight.medium,
          marginBottom: designTokens.spacing.sm,
          color: designTokens.colors.text.primary,
        }}
      >
        {title}
      </h3>
      <p
        style={{
          color: designTokens.colors.text.secondary,
          fontSize: designTokens.typography.fontSize.body,
          marginTop: designTokens.spacing.sm,
        }}
      >
        {description}
      </p>
    </div>
  );
}