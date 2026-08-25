import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError, extractErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const from =
    (location.state as { from?: string } | null)?.from ?? "/dashboard";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(
        extractErrorMessage(err, "Unable to sign in. Please try again."),
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card card">
        <div className="brand-lockup auth-brand">
          <div className="brand-mark" aria-hidden="true">R</div>
          <span>
            <strong>Rasikh</strong>
            <small>Legal knowledge</small>
          </span>
        </div>

        <h2>Sign in</h2>
        <p className="auth-subtitle">Access the Rasikh legal workspace.</p>

        {error && (
          <p className="auth-error" role="alert">{error}</p>
        )}

        <form onSubmit={handleSubmit}>
          <label className="auth-field">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </label>
          <label className="auth-field">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          <Button type="submit" disabled={pending} className="auth-submit">
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="auth-switch">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </div>
    </div>
  );
}