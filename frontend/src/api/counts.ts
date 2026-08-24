import { fetchJson } from "./client";
import type { CountsResponse } from "./types";

export function getCounts(): Promise<CountsResponse> {
  return fetchJson<CountsResponse>("/counts");
}
