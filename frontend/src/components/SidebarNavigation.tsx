import { NavLink } from "react-router-dom";
import { designTokens } from "../tokens";

const navigation = [["Dashboard", "/dashboard"], ["Requests & matters", "/requests"], ["Reviews", "/reviews"], ["Drafts", "/drafts"], ["Approvals", "/approvals"], ["Obligations", "/obligations"], ["History", "/history"]] as const;

export function SidebarNavigation() {
  return <aside className="sidebar"><NavLink className="brand-lockup" to="/dashboard"><div className="brand-mark">R</div><span><strong>Rasikh</strong><small>Legal knowledge</small></span></NavLink><nav aria-label="Primary navigation"><p>Workspace</p>{navigation.map(([label, to], index) => <NavLink className="sidebar-link" key={to} to={to}><em>0{index + 1}</em>{label}</NavLink>)}</nav><footer><div className="status-indicator" style={{ background: "#8eb8b1" }}></div>System connected</footer></aside>;
}
