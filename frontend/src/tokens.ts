import { type ReactNode } from "react";

// Design Tokens
export const designTokens = {
  colors: {
    primary: {
      navy: "#0F2C59",      // Deep Navy - primary navigation, headings, primary actions
      emerald: "#2A6F6F",   // Muted Emerald - secondary actions, positive states
      ivory: "#F8F5F0",     // Warm Ivory - application background, warm surfaces
    },
    surface: {
      paper: "#FFFFFF",     // White - cards and content surfaces
      background: "#F8F5F0", // ivory - main background
    },
    text: {
      primary: "#183046",   // ink - primary text
      secondary: "#647381", // muted - secondary text, disabled states
      inverse: "#FFFFFF",    // white - text on dark backgrounds
    },
    border: {
      line: "#d9ddd8",      // line - borders, dividers
      subtle: "#ffffff99",   // subtle border for hover states
    },
    semantic: {
      danger: "#9b3d35",    // danger states
      warning: "#F4B400",   // warning states
      positive: "#2A6F6F",  // positive states (emerald)
      info: "#0F2C59",      // info states (navy)
    }
  },
  typography: {
    fontFamily: {
      primary: "'IBM Plex Sans', Arial, sans-serif",
      display: "'Georgia', serif",
    },
    fontSize: {
      h1: "38px",           // page titles
      h2: "32px",           // section headings
      body: "16px",         // body text
      bodySmall: "14px",    // metadata
      label: "12px",        // labels
      button: "14px",       // buttons
    },
    fontWeight: {
      normal: 400,
      medium: 500,
      bold: 700,
    },
    lineHeight: {
      tight: 1.2,
      normal: 1.5,
      loose: 1.8,
    }
  },
  spacing: {
    xs: "4px",
    sm: "8px",
    md: "16px",
    lg: "24px",
    xl: "32px",
    xxl: "40px",
    xxxl: "48px",
  },
  borderRadius: {
    sm: "4px",
    md: "8px",
    lg: "12px",
    full: "9999px",
  },
  shadows: {
    small: "0 2px 4px rgba(15, 44, 89, 0.05)",
    medium: "0 4px 8px rgba(15, 44, 89, 0.08)",
    large: "0 10px 25px rgba(15, 44, 89, 0.12)",
  },
  transitions: {
    fast: "0.15s ease",
    normal: "0.3s ease",
    slow: "0.5s ease",
  },
  layout: {
    sidebarWidth: "260px",
    maxContentWidth: "1440px",
  }
};

// Theme interface for TypeScript typing
export interface Theme {
  colors: typeof designTokens.colors;
  typography: typeof designTokens.typography;
  spacing: typeof designTokens.spacing;
  borderRadius: typeof designTokens.borderRadius;
  shadows: typeof designTokens.shadows;
  transitions: typeof designTokens.transitions;
  layout: typeof designTokens.layout;
}