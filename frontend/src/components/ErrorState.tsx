"use client";

import { designTokens } from "../tokens";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({ message = "Unable to load this information.", onRetry, className = "" }: ErrorStateProps) {
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
          fontSize: designTokens.typography.fontSize.h2,
          fontWeight: designTokens.typography.fontWeight.medium,
          color: designTokens.colors.text.primary,
          marginBottom: designTokens.spacing.sm,
        }}
      >
        {message}
      </h3>
      <p style={{ color: designTokens.colors.text.secondary, marginBottom: designTokens.spacing.lg }}>
        Please try again or contact support if the problem persists.
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            backgroundColor: designTokens.colors.primary.navy,
            color: "white",
            border: "none",
            borderRadius: designTokens.borderRadius.md,
            padding: `${designTokens.spacing.sm} ${designTokens.spacing.md}`,
            cursor: "pointer",
            fontSize: designTokens.typography.fontSize.button,
            fontWeight: designTokens.typography.fontWeight.medium,
            transition: designTokens.transitions.fast,
          }}
        >
          Try again
        </button>
      )}
    </div>
  );
}