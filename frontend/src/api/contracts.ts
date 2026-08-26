import { fetchJson } from "./client";
import type { ContractSummary } from "./types";

export function listContracts(orgId: string): Promise<ContractSummary[]> {
    return fetchJson<ContractSummary[]>(
        `/organisations/${encodeURIComponent(orgId)}/contracts`,
    );
}