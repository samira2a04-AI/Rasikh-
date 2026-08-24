"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface TabsProps {
  tabs: string[];
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onTabChange, className = "" }: TabsProps) {
  return (
    <div className={`tabs ${className}`} style={{ display: "flex", gap: designTokens.spacing.sm, borderBottom: `1px solid ${designTokens.colors.border.line}` }}>
      {tabs.map((tab, index) => {
        const isActive = activeTab === tab || (index === 0 && !activeTab);
        return (
          <button
            key={tab}
            onClick={() => onTabChange && onTabChange(tab)}
            style={{
              padding: `${designTokens.spacing.md} ${designTokens.spacing.lg}`,
              border: "none",
              backgroundColor: "transparent",
              cursor: "pointer",
              borderBottom: isActive ? `2px solid ${designTokens.colors.primary.navy}` : "2px solid transparent",
              color: isActive ? designTokens.colors.primary.navy : designTokens.colors.text.secondary,
              fontWeight: isActive ? designTokens.typography.fontWeight.medium : designTokens.typography.fontWeight.normal,
              fontSize: designTokens.typography.fontSize.body,
              transition: designTokens.transitions.fast,
            }}
          >
            {tab}
          </button>
        );
      })}
    </div>
  );
}