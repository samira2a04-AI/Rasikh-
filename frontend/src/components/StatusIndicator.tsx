"use client";

import { designTokens } from "../tokens";

interface StatusIndicatorProps {
  status: string;
  className?: string;
}

export function StatusIndicator({ status, className = "" }: StatusIndicatorProps) {
  const getStatusColor = (status: string) => {
    if (["approved", "authorized", "on_track"].includes(status)) {
      return designTokens.colors.primary.emerald;
    } else if (["overdue", "rejected"].includes(status)) {
      return designTokens.colors.semantic.danger;
    } else {
      return designTokens.colors.primary.navy;
    }
  };
  
  const getStatusLabel = (status: string) => {
    return status.replaceAll("_", " ");
  };
  
  return (
    <span className={`status-indicator ${className}`} style={{ display: "flex", alignItems: "center", gap: designTokens.spacing.xs }}>
      <span
        style={{
          width: "8px",
          height: "8px",
          borderRadius: "50%",
          backgroundColor: getStatusColor(status),
        }}
      />
      <span style={{ color: designTokens.colors.text.primary, fontSize: designTokens.typography.fontSize.bodySmall }}>
        {getStatusLabel(status)}
      </span>
    </span>
  );
}