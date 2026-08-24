"use client";

import { type ReactNode } from "react";
import { designTokens } from "../tokens";

export function Logo() {
  return (
    <div className="brand-lockup">
      <div className="brand-mark">
        R
      </div>
      <span>
        <strong>Rasikh</strong>
        <small>Legal knowledge</small>
      </span>
    </div>
  );
}