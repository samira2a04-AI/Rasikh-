import { fetchJson } from "./client";
import type { Organisation } from "./types";

export function listOrganisations(): Promise<Organisation[]> {
  return fetchJson<Organisation[]>("/organisations");
}
