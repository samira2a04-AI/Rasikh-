import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, extractErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";

export function RegisterPage() {
  const { register, login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setPending(true);
    try {
      await register(email, password);
      // Registration succeeded: sign straight in with the same credentials.
      await login(email, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(
        extractErrorMessage(err, "Unable to create the account. Please try again."),
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

        <h2>Create account</h2>
        <p className="auth-subtitle">Join the Rasikh legal workspace.</p>

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
              minLength={8}
              autoComplete="new-password"
            />
          </label>
          <label className="auth-field">
            Confirm password
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
          </label>
          <Button type="submit" disabled={pending} className="auth-submit">
            {pending ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}