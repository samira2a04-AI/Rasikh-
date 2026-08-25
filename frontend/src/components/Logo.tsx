import { designTokens } from "../tokens";

export function Logo() {
  return (
    <div className="brand-lockup">
      {/* Replace this placeholder mark with the official Rasikh SVG logo when available. */}
      <div
        className="brand-mark"
        aria-hidden="true"
      >
        R
      </div>
      <span>
        <strong
          style={{
            fontFamily: designTokens.typography.fontFamily.display,
          }}
        >
          Rasikh
        </strong>
        <small>Legal knowledge</small>
      </span>
    </div>
  );
}