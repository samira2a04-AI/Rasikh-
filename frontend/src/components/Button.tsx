"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface ButtonProps {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "outline";
  size?: "sm" | "md" | "lg";
  className?: string;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
}

export function Button({
  children,
  onClick,
  variant = "primary",
  size = "md",
  className = "",
  disabled = false,
  type = "button",
}: ButtonProps) {
  const baseClasses = "button";
  
  const variantClasses = {
    primary: "bg-navy text-white hover:bg-navy/90",
    secondary: "bg-emerald text-white hover:bg-emerald/90",
    outline: "bg-white border border-line text-navy hover:bg-ivory",
  };
  
  const sizeClasses = {
    sm: "px-sm py-xs text-body-small",
    md: "px-md py-sm text-button",
    lg: "px-lg py-md text-button",
  };
  
  const disabledClasses = disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer";
  
  const classes = `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${disabledClasses} ${className}`;
  
  return (
    <button
      type={type}
      className={classes}
      onClick={!disabled ? onClick : undefined}
      disabled={disabled}
      style={{
        borderRadius: designTokens.borderRadius.md,
        transition: designTokens.transitions.fast,
      }}
    >
      {children}
    </button>
  );
}