/**
 * Access-token storage for the API client.
 *
 * The JWT lives in sessionStorage so it does not outlive the browser session.
 * It is never logged or rendered by the UI. The backend remains the security
 * authority; this module only decides whether requests are sent authenticated.
 */

const TOKEN_KEY = "rasikh.access_token";

export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

/** Paths that must never trigger the automatic unauthenticated handling. */
export function isAuthPath(path: string): boolean {
  return path.startsWith("/auth/");
}
