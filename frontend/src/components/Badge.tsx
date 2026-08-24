"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: "navy" | "emerald" | "danger" | "warning" | "neutral";
  className?: string;
}

export function Badge({ children, variant = "neutral", className = "" }: BadgeProps) {
  const baseClasses = "badge";
  
  const variantClasses = {
    navy: "badge--navy",
    emerald: "badge--emerald",
    danger: "badge--danger",
    warning: "badge--warning",
    neutral: "badge--neutral",
  };
  
  const classes = `${baseClasses} ${variantClasses[variant]} ${className}`;
  
  return (
    <span
      className={classes}
      style={{
        borderRadius: designTokens.borderRadius.sm,
        fontSize: designTokens.typography.fontSize.label,
        fontWeight: designTokens.typography.fontWeight.medium,
        padding: `${designTokens.spacing.xs} ${designTokens.spacing.sm}`,
      }}
    >
      {children}
    </span>
  );
}