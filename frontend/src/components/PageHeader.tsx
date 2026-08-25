import { designTokens } from "../tokens";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  className?: string;
}

export function PageHeader({ eyebrow, title, description, className = "" }: PageHeaderProps) {
  return (
    <header className={`page-header ${className}`}>
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1
        style={{
          color: designTokens.colors.primary.navy,
          fontFamily: designTokens.typography.fontFamily.display,
          fontSize: designTokens.typography.fontSize.h1,
          fontWeight: designTokens.typography.fontWeight.medium,
          lineHeight: designTokens.typography.lineHeight.tight,
        }}
      >
        {title}
      </h1>
      {description && <p className="page-header-description">{description}</p>}
    </header>
  );
}