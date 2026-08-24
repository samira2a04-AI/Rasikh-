"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface LoadingStateProps {
  message?: string;
  className?: string;
}

export function LoadingState({ message = "Loading information...", className = "" }: LoadingStateProps) {
  return (
    <div
      className={`state-panel ${className}`}
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
          width: "40px",
          height: "40px",
          border: `3px solid ${designTokens.colors.border.line}`,
          borderTop: `3px solid ${designTokens.colors.primary.navy}`,
          borderRadius: "50%",
          animation: "spin 1s linear infinite",
          marginBottom: designTokens.spacing.md,
        }}
      />
      <p style={{ color: designTokens.colors.text.secondary, fontSize: designTokens.typography.fontSize.body }}>{message}</p>
      <style>
        {`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}
      </style>
    </div>
  );
}