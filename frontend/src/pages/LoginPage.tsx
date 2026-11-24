import { ArrowLeft, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Brand } from "../components/Brand";
import { useAuth } from "../lib/auth";
import { navigate } from "../lib/router";

export function LoginPage() {
  const { authenticated, login } = useAuth();
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (authenticated) navigate("/");
  }, [authenticated]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(password);
      navigate("/");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <div className="login-page__contours" aria-hidden="true" />
      <section className="login-panel">
        <Brand />
        <div className="login-panel__rule" />
        <span className="system-state system-state--large"><i />System operational</span>
        <div className="login-panel__copy">
          <h1>Officer sign-in</h1>
          <p>Use the administrator credentials configured for this installation.</p>
        </div>
        <form onSubmit={submit} className="login-form">
          <label htmlFor="password">Password</label>
          <div className="password-field">
            <input
              id="password"
              type={visible ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              autoFocus
            />
            <button type="button" onClick={() => setVisible((value) => !value)} aria-label={visible ? "Hide password" : "Show password"}>
              {visible ? <EyeOff /> : <Eye />}
            </button>
          </div>
          {error && <div className="form-message form-message--error" role="alert">{error}</div>}
          <button className="button button--primary button--large" type="submit" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <button className="back-link" onClick={() => navigate("/")}><ArrowLeft size={20} />Return to overview</button>
      </section>
      <div className="login-security"><LockKeyhole size={20} />Protected by server-side sessions and CSRF validation.</div>
    </main>
  );
}
