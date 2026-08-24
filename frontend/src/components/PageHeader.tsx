"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  className?: string;
}

export function PageHeader({ eyebrow, title, description, className = "" }: PageHeaderProps) {
  return (
    <header className={`page-header ${className}`} style={{ marginBottom: designTokens.spacing.xxl }}>
      {eyebrow && (
        <p
          className="eyebrow"
          style={{
            color: designTokens.colors.primary.emerald,
            fontSize: designTokens.typography.fontSize.label,
            fontWeight: designTokens.typography.fontWeight.bold,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            marginBottom: designTokens.spacing.sm,
          }}
        >
          {eyebrow}
        </p>
      )}
      <h1
        style={{
          color: designTokens.colors.primary.navy,
          fontFamily: designTokens.typography.fontFamily.display,
          fontSize: designTokens.typography.fontSize.h1,
          fontWeight: designTokens.typography.fontWeight.medium,
          lineHeight: designTokens.typography.lineHeight.tight,
          margin: 0,
        }}
      >
        {title}
      </h1>
      {description && (
        <p
          style={{
            color: designTokens.colors.text.secondary,
            fontSize: designTokens.typography.fontSize.body,
            lineHeight: designTokens.typography.lineHeight.normal,
            marginTop: designTokens.spacing.sm,
          }}
        >
          {description}
        </p>
      )}
    </header>
  );
}