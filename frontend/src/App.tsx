import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { RequestDetailPage } from "./pages/RequestDetailPage";
import { RoutePlaceholder } from "./pages/RoutePlaceholder";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { RequestsPage } from "./pages/RequestsPage";
import { ReviewsPage } from "./pages/ReviewsPage";
import { DraftsPage } from "./pages/DraftsPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ObligationsPage } from "./pages/ObligationsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { useAuth } from "./auth/AuthContext";
import type { ReactNode } from "react";

/** Redirects unauthenticated visitors to /login, preserving the destination. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return (
      <Navigate
        replace
        to="/login"
        state={{ from: location.pathname + location.search }}
      />
    );
  }
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/requests" element={<RequestsPage />} />
        <Route
          path="/requests/:requestId"
          element={<RequestDetailPage />}
        />
        <Route path="/reviews" element={<ReviewsPage />} />
        <Route path="/drafts" element={<DraftsPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/obligations" element={<ObligationsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="*" element={<Navigate replace to="/dashboard" />} />
      </Route>
    </Routes>
  );
}
