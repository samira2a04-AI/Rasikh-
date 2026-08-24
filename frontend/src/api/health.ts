import { fetchJson } from "./client";
import type { HealthResponse } from "./types";

export function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}
