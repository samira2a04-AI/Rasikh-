"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface SidebarLinkProps {
  to: string;
  children: ReactNode;
  isActive?: boolean;
  onClick?: () => void;
}

export function SidebarLink({ to, children, isActive = false, onClick }: SidebarLinkProps) {
  return (
    <a
      href={to}
      className={`sidebar-link ${isActive ? "active" : ""}`}
      onClick={onClick}
      style={{
        padding: `${designTokens.spacing.sm} ${designTokens.spacing.md}`,
        borderLeft: `2px solid ${isActive ? designTokens.colors.primary.emerald : "transparent"}`,
        display: "flex",
        alignItems: "center",
        gap: designTokens.spacing.sm,
        fontSize: designTokens.typography.fontSize.body,
        color: "white",
        opacity: isActive ? 1 : 0.78,
        backgroundColor: isActive ? "rgba(255, 255, 255, 0.1)" : "transparent",
        transition: designTokens.transitions.fast,
        textDecoration: "none",
      }}
    >
      <em
        style={{
          fontStyle: "normal",
          fontSize: designTokens.typography.fontSize.label,
          opacity: isActive ? 1 : 0.55,
          minWidth: "30px",
          textAlign: "center",
        }}
      >
        0{Math.floor(Math.random() * 99) + 1}
      </em>
      <span>{children}</span>
    </a>
  );
}