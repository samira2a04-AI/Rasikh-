"use client";

import { Outlet, useLocation } from "react-router-dom";
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
];

export function AppShell() {
  const { pathname } = useLocation();
  const pageName = pathname.startsWith("/requests/") 
    ? "Matter record" 
    : pathname === "/dashboard"
    ? "Dashboard"
    : pathname === "/reviews"
    ? "Reviews"
    : pathname === "/drafts"
    ? "Drafts"
    : pathname === "/approvals"
    ? "Approvals"
    : pathname === "/obligations"
    ? "Obligations"
    : pathname === "/history"
    ? "History"
    : "Rasikh";
  
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">R</div>
          <span>
            <strong>Rasikh</strong>
            <small>Legal knowledge</small>
          </span>
        </div>
        <nav aria-label="Primary navigation">
          <p>Workspace</p>
          {navigation.map((item) => {
            const isActive = pathname === item.to || (item.to === "/requests" && pathname.startsWith("/requests/"));
            return (
              <SidebarLink
                key={item.to}
                to={item.to}
                isActive={isActive}
              >
                {item.label}
              </SidebarLink>
            );
          })}
        </nav>
        <footer>
          <div className="status-indicator">
            <div></div>
            System connected
          </div>
        </footer>
      </aside>
      
      <div className="app-workspace">
        <header className="topbar">
          <p><strong>Legal knowledge</strong></p>
          <div>
            <span>{pageName}</span>
            <div className="status-indicator status-indicator--emerald" title="System connected"></div>
          </div>
        </header>
        
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}