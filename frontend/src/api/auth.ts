import { fetchJson, jsonBody } from "./client";
import type {
  AuthUserResponse,
  LoginRequest,
  MeResponse,
  RegisterRequest,
  TokenResponse,
} from "./types";

export function register(body: RegisterRequest): Promise<AuthUserResponse> {
  return fetchJson<AuthUserResponse>("/auth/register", {
    method: "POST",
    ...jsonBody(body),
  });
}

export function login(body: LoginRequest): Promise<TokenResponse> {
  return fetchJson<TokenResponse>("/auth/login", {
    method: "POST",
    ...jsonBody(body),
  });
}

/** Profile of the authenticated user, including their mapped team member. */
export function me(): Promise<MeResponse> {
  return fetchJson<MeResponse>("/auth/me");
}
