import {
  clearAccessToken,
  getAccessToken,
  isAuthPath,
} from "./authToken";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const API_BASE_URL = "";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(`API request failed with status ${status}`);
  }
}

export function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") {
      return err.detail;
    }
    if (typeof err.detail === "object" && err.detail !== null) {
      const obj = err.detail as Record<string, unknown>;
      if (typeof obj.detail === "string") {
        return obj.detail;
      }
      if (Array.isArray(obj.detail)) {
        const messages = obj.detail
          .map((item) => {
            if (typeof item === "object" && item !== null && "msg" in item) {
              return String(item.msg);
            }
            return null;
          })
          .filter(Boolean);
        if (messages.length > 0) {
          return messages.join(". ");
        }
      }
      if (typeof obj.message === "string") {
        return obj.message;
      }
    }
    if (err.status === 409) {
      return "An account with this email already exists.";
    }
    if (err.status === 422) {
      return "Please check your details: the email must be valid and the password at least 8 characters.";
    }
    if (err.status === 401) {
      return "Incorrect email or password.";
    }
    return fallback;
  }
  if (err instanceof Error) {
    if (
      err.message.includes("Failed to fetch") ||
      err.message.includes("NetworkError") ||
      err.name === "TypeError"
    ) {
      console.error("[fetchJson] Network Error or Browser block:", err);
      return `Network error: Unable to reach the server.`;
    }
    return err.message;
  }
  return fallback;
}

/**
 * Fired when the backend rejects an authenticated request with 401 so the
 * auth layer can log the user out and the router can redirect to /login.
 */
export const UNAUTHORIZED_EVENT = "rasikh:unauthorized";

function notifyUnauthorized(): void {
  clearAccessToken();
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}

export async function fetchJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // Attach the Bearer token automatically to every request when present.
  if (!headers.has("Authorization")) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const url = `${API_BASE_URL}${path}`;
  console.log(`[fetchJson] fetching: ${url}`);
  const response = await fetch(url, {
    ...options,
    headers,
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    // A 401 from a business endpoint means our token is missing/expired:
    // drop the session so subsequent navigation lands on /login.
    if (response.status === 401 && !isAuthPath(path)) {
      notifyUnauthorized();
    }
    throw new ApiError(response.status, payload);
  }

  return payload as T;
}

export function jsonBody(body: unknown): Pick<RequestInit, "body"> {
  return { body: JSON.stringify(body) };
}
