"use client";

import { designTokens } from "../tokens";
import { type ReactNode } from "react";

interface DataTableProps<T> {
  columns: { label: string; value: (item: T) => ReactNode }[];
  items: T[];
  getKey: (item: T) => string;
  className?: string;
}

export function DataTable<T>({ columns, items, getKey, className = "" }: DataTableProps<T>) {
  return (
    <div className={`table-wrap ${className}`} style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          backgroundColor: designTokens.colors.surface.paper,
          borderRadius: designTokens.borderRadius.md,
          overflow: "hidden",
          boxShadow: designTokens.shadows.small,
        }}
      >
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.label}
                style={{
                  padding: designTokens.spacing.md,
                  textAlign: "left",
                  borderBottom: `1px solid ${designTokens.colors.border.line}`,
                  backgroundColor: designTokens.colors.primary.ivory,
                  fontWeight: designTokens.typography.fontWeight.medium,
                  color: designTokens.colors.text.secondary,
                  fontSize: designTokens.typography.fontSize.label,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                }}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={getKey(item)}
              style={{
                transition: designTokens.transitions.fast,
              }}
            >
              {columns.map((column) => (
                <td
                  key={column.label}
                  style={{
                    padding: designTokens.spacing.md,
                    textAlign: "left",
                    borderBottom: `1px solid ${designTokens.colors.border.line}`,
                  }}
                >
                  {column.value(item)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}