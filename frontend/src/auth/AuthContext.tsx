import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { login as loginApi, me as meApi, register as registerApi } from "../api/auth";
import { clearAccessToken, getAccessToken, setAccessToken } from "../api/authToken";
import { UNAUTHORIZED_EVENT } from "../api/client";
import type { AuthUserResponse, UserRole } from "../api/types";

const SESSION_USER_KEY = "rasikh.session_user";

interface SessionUser {
  email: string;
  role: UserRole;
  memberId?: string;
  memberName?: string;
  memberRole?: string;
}

function loadSessionUser(): SessionUser | null {
  const raw = sessionStorage.getItem(SESSION_USER_KEY);
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as SessionUser).email === "string" &&
      ((parsed as SessionUser).role === "member" ||
        (parsed as SessionUser).role === "admin")
    ) {
      return parsed as SessionUser;
    }
  } catch {
    // Corrupted session data — treat as logged out.
  }
  return null;
}

function persistSessionUser(user: SessionUser | null): void {
  if (user) {
    sessionStorage.setItem(SESSION_USER_KEY, JSON.stringify(user));
  } else {
    sessionStorage.removeItem(SESSION_USER_KEY);
  }
}

interface AuthContextValue {
  isAuthenticated: boolean;
  user: SessionUser | null;
  role: UserRole | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<AuthUserResponse>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getAccessToken());
  const [user, setUser] = useState<SessionUser | null>(() => loadSessionUser());
  const navigate = useNavigate();

  const logout = useCallback(() => {
    clearAccessToken();
    setToken(null);
    persistSessionUser(null);
    setUser(null);
    navigate("/login", { replace: true });
  }, [navigate]);

  // The API client broadcasts when the backend rejects a request with 401
  // (expired/invalid token): end the session and return to /login.
  useEffect(() => {
    const onUnauthorized = () => {
      clearAccessToken();
      setToken(null);
      persistSessionUser(null);
      setUser(null);
      navigate("/login", { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [navigate]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await loginApi({ email, password });
    setAccessToken(tokens.access_token);
    setToken(tokens.access_token);
    const normalizedEmail = email.trim().toLowerCase();
    const existing = loadSessionUser();
    const sessionUser: SessionUser =
      existing && existing.email === normalizedEmail
        ? existing
        : { email: normalizedEmail, role: "member" };
    // Enrich with the mapped firm/team member (best-effort; login still
    // succeeds if /auth/me is unavailable). This is display-only — the backend
    // always resolves the requester server-side.
    try {
      const profile = await meApi();
      sessionUser.role = profile.role;
      sessionUser.memberId = profile.member_id ?? undefined;
      sessionUser.memberName = profile.member?.name ?? undefined;
      sessionUser.memberRole = profile.member?.role ?? undefined;
    } catch {
      // Keep the fallback session; the backend enforces real role/authz.
    }
    persistSessionUser(sessionUser);
    setUser(sessionUser);
  }, []);

  const register = useCallback(
    async (email: string, password: string): Promise<AuthUserResponse> => {
      const created = await registerApi({ email, password });
      return created;
    },
    [],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: Boolean(token && user),
      user,
      role: user?.role ?? null,
      login,
      register,
      logout,
    }),
    [token, user, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return ctx;
}