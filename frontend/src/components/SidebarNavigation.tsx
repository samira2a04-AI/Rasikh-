import { NavLink } from "react-router-dom";
import { Logo } from "./Logo";
import { SidebarLink } from "./SidebarLink";

const navigation = [
  { label: "Dashboard", to: "/dashboard" },
  { label: "Requests & matters", to: "/requests" },
  { label: "Reviews", to: "/reviews" },
  { label: "Drafts", to: "/drafts" },
  { label: "Approvals", to: "/approvals" },
  { label: "Obligations", to: "/obligations" },
  { label: "History", to: "/history" },
] as const;

export function SidebarNavigation() {
  return (
    <aside className="sidebar">
      <NavLink
        to="/dashboard"
        style={{ display: "block" }}
      >
        <Logo />
      </NavLink>
      <nav aria-label="Primary navigation">
        <p className="sidebar-nav-label">Workspace</p>
        <ul className="sidebar-nav-list">
          {navigation.map((item, index) => (
            <li key={item.to}>
              <SidebarLink to={item.to} index={index}>
                {item.label}
              </SidebarLink>
            </li>
          ))}
        </ul>
      </nav>
      <footer className="sidebar-footer">
        <span className="system-status">System connected</span>
      </footer>
    </aside>
  );
}
