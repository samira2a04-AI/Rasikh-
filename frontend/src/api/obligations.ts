import { fetchJson, jsonBody } from "./client";
import type { ObligationSweepRequest, ObligationSweepResponse } from "./types";

export function sweepObligations(
  body: ObligationSweepRequest,
): Promise<ObligationSweepResponse> {
  return fetchJson<ObligationSweepResponse>("/obligations/sweep", {
    method: "POST",
    ...jsonBody(body),
  });
}
