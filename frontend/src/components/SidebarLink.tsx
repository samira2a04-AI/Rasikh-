import { NavLink } from "react-router-dom";
import { type ReactNode } from "react";

interface SidebarLinkProps {
  to: string;
  index: number;
  children: ReactNode;
}

export function SidebarLink({ to, index, children }: SidebarLinkProps) {
  const number = String(index + 1).padStart(2, "0");

  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        isActive ? "sidebar-link active" : "sidebar-link"
      }
    >
      <em>{number}</em>
      <span>{children}</span>
    </NavLink>
  );
}