import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { RequestDetailPage } from "./pages/RequestDetailPage";
import { RoutePlaceholder } from "./pages/RoutePlaceholder";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/requests" element={<RoutePlaceholder title="Requests" />} />
        <Route
          path="/requests/:requestId"
          element={<RequestDetailPage />}
        />
        <Route path="/reviews" element={<RoutePlaceholder title="Reviews" />} />
        <Route path="/drafts" element={<RoutePlaceholder title="Drafts" />} />
        <Route path="/approvals" element={<RoutePlaceholder title="Approvals" />} />
        <Route path="/obligations" element={<RoutePlaceholder title="Obligations" />} />
        <Route path="/history" element={<RoutePlaceholder title="History" />} />
        <Route path="*" element={<Navigate replace to="/dashboard" />} />
      </Route>
    </Routes>
  );
}
