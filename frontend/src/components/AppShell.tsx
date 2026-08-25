import { Outlet, useLocation } from "react-router-dom";
import { SidebarNavigation } from "./SidebarNavigation";
import { useAuth } from "../auth/AuthContext";

const pageNames: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/requests": "Requests & matters",
  "/reviews": "Reviews",
  "/drafts": "Drafts",
  "/approvals": "Approvals",
  "/obligations": "Obligations",
  "/history": "History",
};

function getPageName(pathname: string): string {
  if (pathname.startsWith("/requests/")) {
    return "Matter record";
  }
  return pageNames[pathname] ?? "Rasikh";
}

export function AppShell() {
  const { pathname } = useLocation();
  const { user, role, logout } = useAuth();

  return (
    <div className="app-shell">
      <SidebarNavigation />

      <div className="app-workspace">
        <header className="topbar">
          <p className="topbar-context">Rasikh workspace</p>
          <div className="topbar-session">
            <p className="topbar-page">{getPageName(pathname)}</p>
            {user && (
              <span className={`role-badge role-badge--${role ?? "member"}`}>
                {role === "admin" ? "Admin" : "Member"}
              </span>
            )}
            {user && <span className="topbar-user">{user.email}</span>}
            {user && user.memberName && (
              <span className="topbar-user">· {user.memberName}</span>
            )}
            {user && (
              <button type="button" className="logout-button" onClick={logout}>
                Sign out
              </button>
            )}
          </div>
        </header>

        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}