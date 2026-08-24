"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Card({ children, className = "", onClick }: CardProps) {
  const baseClasses = "card";
  const interactiveClasses = onClick ? "cursor-pointer" : "";
  
  const classes = `${baseClasses} ${interactiveClasses} ${className}`;
  
  const handleClick = onClick ? (e: React.MouseEvent) => {
    e.stopPropagation();
    onClick();
  } : undefined;
  
  return (
    <section
      className={classes}
      onClick={handleClick}
      style={{
        borderRadius: designTokens.borderRadius.md,
        boxShadow: designTokens.shadows.small,
        backgroundColor: designTokens.colors.surface.paper,
        transition: designTokens.transitions.normal,
        padding: designTokens.spacing.lg,
      }}
    >
      {children}
    </section>
  );
}