"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface ModalProps {
  children: ReactNode;
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  className?: string;
}

export function Modal({ children, isOpen, onClose, title, className = "" }: ModalProps) {
  if (!isOpen) return null;
  
  return (
    <div
      className={`dialog-backdrop ${className}`}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(15, 44, 89, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        opacity: 0,
        animation: "fadeIn 0.3s ease forwards",
      }}
    >
      <div
        className="dialog-panel"
        style={{
          backgroundColor: designTokens.colors.surface.paper,
          borderRadius: designTokens.borderRadius.lg,
          boxShadow: designTokens.shadows.large,
          padding: designTokens.spacing.xl,
          width: "90%",
          maxWidth: "500px",
          maxHeight: "90vh",
          overflow: "auto",
        }}
      >
        {title && onClose ? (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: designTokens.spacing.lg,
            }}
          >
            <h2
              style={{
                fontSize: designTokens.typography.fontSize.h2,
                fontWeight: designTokens.typography.fontWeight.medium,
                color: designTokens.colors.text.primary,
                margin: 0,
              }}
            >
              {title}
            </h2>
            {onClose && (
              <button
                onClick={onClose}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: "24px",
                  cursor: "pointer",
                  color: designTokens.colors.text.secondary,
                }}
              >
                ×
              </button>
            )}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
}