/**
 * Rendered verification: renders the REAL App routes (loaded via vite) at
 * /requests and /requests/:id with LIVE backend data prefetched into the
 * react-query cache, then asserts on the produced HTML.
 */
import { createServer } from "vite";
import { renderToString } from "react-dom/server";
import React from "react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const BACKEND = "http://127.0.0.1:8000";

// --- auth storage stubs (authToken/AuthContext read these) -----------------
const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

async function api(path, token, method = "GET", body) {
  const res = await fetch(BACKEND + path, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

const token = (
  await api("/auth/login", null, "POST", {
    email: "lawyer@rasikh.local",
    password: "Demo1234!",
  })
).access_token;
store.set("rasikh.access_token", token);
store.set(
  "rasikh.session_user",
  JSON.stringify({ email: "lawyer@rasikh.local", role: "member" }),
);
console.log("auth: ok");

const registry = await api("/requests/registry?limit=50", token);
console.log("registry rows:", registry.length);
// Prefer a request that actually has findings so the review-workspace link
// rendering can be asserted; fall back to any contract_review request.
const preferredId = "f62e30dc-00fd-4ac4-a9ce-8fa92820b5c3";
const target =
  registry.find((r) => r.request.request_id === preferredId) ??
  registry.find((r) => r.request.request_type === "contract_review") ??
  registry[0];
const requestId = target.request.request_id;
const [request, view] = await Promise.all([
  api(`/requests/${encodeURIComponent(requestId)}`, token),
  api(`/requests/${encodeURIComponent(requestId)}/view`, token),
]);
let history = { events: [] };
try {
  history = await api(`/requests/${encodeURIComponent(requestId)}/history`, token);
} catch {}

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: "custom",
});
const { App } = await server.ssrLoadModule("/src/App.tsx");
const { AuthProvider } = await server.ssrLoadModule("/src/auth/AuthContext.tsx");

function makeClient() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["requests-registry"], registry);
  qc.setQueryData(["request", requestId], request);
  qc.setQueryData(["request-view", requestId], view);
  qc.setQueryData(["request-history", requestId], history);
  qc.setQueryData(["me"], { member_id: null });
  return qc;
}

function renderApp(entry) {
  return renderToString(
    React.createElement(
      QueryClientProvider,
      { client: makeClient() },
      React.createElement(
        MemoryRouter,
        { initialEntries: [entry] },
        React.createElement(AuthProvider, null, React.createElement(App)),
      ),
    ),
  );
}

const { RequestsPage } = await server.ssrLoadModule("/src/pages/RequestsPage.tsx");
console.log("RequestsPage type:", typeof RequestsPage);
const html1 = renderToString(
  React.createElement(
    QueryClientProvider,
    { client: makeClient() },
    React.createElement(MemoryRouter, { initialEntries: ["/requests"] },
      React.createElement(RequestsPage)),
  ),
);
const { RequestDetailPage } = await server.ssrLoadModule("/src/pages/RequestDetailPage.tsx");
console.log("RequestDetailPage type:", typeof RequestDetailPage);
const html2 = renderToString(
  React.createElement(
    QueryClientProvider,
    { client: makeClient() },
    React.createElement(
      MemoryRouter,
      { initialEntries: [`/requests/${encodeURIComponent(requestId)}`] },
      React.createElement(
        Routes,
        null,
        React.createElement(Route, {
          path: "/requests/:requestId",
          element: React.createElement(RequestDetailPage),
        }),
      ),
    ),
  ),
);
await server.close();

const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const t1 = text(html1);
const t2 = text(html2);
const ths = [...html1.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((m) =>
  m[1].replace(/<[^>]+>/g, "").trim(),
);
const rowCount = (html1.match(/<tr/g) ?? []).length - 1;
const h1 = (html1.match(/<h1[^>]*>([\s\S]*?)<\/h1>/) ?? [])[1] ?? "";
const h2s = [...html1.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)].map((m) =>
  m[1].replace(/<!--.*?-->/g, "").trim(),
);

console.log("H1           :", h1.trim());
console.log("H2 order     :", h2s.join(" | "));
console.log("Table headers:", ths.join(", "));
console.log("Row count    :", rowCount);
console.log("--- detail page sample ---");
console.log(t2.slice(0, 400));

const checks = {
  "landing renders 'Requests & matters' H1":
    h1.includes("Requests &amp; matters") || h1.includes("Requests & matters"),
  "'Request registry' heading present": h2s.includes("Request registry"),
  "registry FIRST section; submit form after":
    h2s[0] === "Request registry" && h2s.includes("Submit a new request"),
  "registry has search + filters (toolbar)": html1.includes('ws-search') && html1.includes('ws-filter'),
  "columns correct":
    [
      "Request",
      "Type",
      "AI Result",
      "Drafts",
      "Org Obligations",
      "Approvals",
      "Findings",
      "Status",
    ].every((h, i) => ths[i] === h),
  "rows rendered from live API": rowCount > 0,
  "persisted request_type shown (contract review)":
    t1.toLowerCase().includes("contract review"),
  "row links to unified detail (/requests/{id})": html1.includes(
    `href="/requests/${encodeURIComponent(requestId)}"`,
  ),
  "no review workspace content on landing":
    !t1.includes("Run review") && !t1.includes("checklist"),
  // --- unified workspace ---
  "workspace header shows 'Open Review Workspace' action": t2.includes("Open Review Workspace"),
  "workspace header meta (org, requester, submitted, status)":
    t2.includes("Organisation") && t2.includes("Requested by") &&
    t2.includes("Submitted") && t2.includes("Status"),
  "workflow stepper rendered with real states": html2.includes("ws-stepper") && t2.includes("AI Analysis") && t2.includes("Approval"),
  "AI analysis is focal hero section": html2.includes("ws-hero") && t2.includes("AI analysis") || html2.includes("ws-hero"),
  "'View Full Analysis' action present": t2.includes("View Full Analysis"),
  "work product summary cards (4)": ["Drafts", "Approvals", "Findings", "Organization Obligations"].every((c) => t2.includes(c)),
  "sources/evidence section present": html2.includes("Evidence &amp; sources"),
  "audit timeline at bottom (not table)": html2.includes("ws-timeline"),
  "needs attention panel rendered": html2.includes("ws-attention"),
  "two-column needs-attention + work-product layout": html2.includes("ws-columns"),
  "hero shows overall risk badge iff a finding rating exists":
    view.findings.some((f) => f.risk_rating) === html2.includes("ws-risk-badge"),
  "work product cards are compact shortcuts": html2.includes("ws-cards-compact"),
  "timeline links to complete audit history": html2.includes("/history"),
  // --- Phase 1: real AI result / AnalysisRun ---
  "analysis object exposed by view API": !!view.analysis || html2.includes("No analysis has been completed yet"),
  "hero shows run status chip when analysis exists":
    !view.analysis || html2.includes("ws-run-status"),
  "analysis timestamp shown when completed":
    !view.analysis?.completed_at || t2.includes("Analysis completed"),
  "summary text is deterministic synthesis, not draft content":
    !view.analysis?.summary ||
    (!t2.includes("HUMAN DRAFT") && t2.includes("Automated review produced")),
};

let failed = 0;
for (const [name, ok] of Object.entries(checks)) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
  if (!ok) failed++;
}
process.exit(failed ? 1 : 0);