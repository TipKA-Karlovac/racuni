import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "./api.js";
import { ErrorMessage, Field, Loading } from "./ui.jsx";

/** Okvir aplikacije: bez prijave prikazuje samo obrazac za prijavu. */
export default function Shell() {
  const [user, setUser] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    // Ovaj poziv usput postavlja CSRF kolačić potreban za prijavu.
    api("/auth/me/", { signal: controller.signal })
      .then(setUser)
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, []);

  function logout() {
    api("/auth/logout/", { method: "POST" })
      .then(setUser)
      .catch((err) => setError(err.message));
  }

  let content;
  if (error) content = <ErrorMessage>{error}</ErrorMessage>;
  else if (!user) content = <Loading />;
  else if (!user.authenticated) content = <Login onLogin={setUser} />;
  else content = <Outlet />;

  return (
    <div className="page page-wide">
      <header className="header">
        <span className="brand">Ponude i računi</span>
        {user?.authenticated && (
          <>
            <nav className="nav" aria-label="Glavni izbornik">
              <NavLink to="/" end>
                Pregled
              </NavLink>
              <NavLink to="/racuni">Računi</NavLink>
              <NavLink to="/ponude">Ponude</NavLink>
              <NavLink to="/klijenti">Klijenti</NavLink>
              <NavLink to="/postavke">Postavke</NavLink>
            </nav>
            <span className="muted user">
              {user.username} ·{" "}
              <button type="button" className="link" onClick={logout}>
                Odjava
              </button>
            </span>
          </>
        )}
      </header>
      <main className="main">{content}</main>
    </div>
  );
}

function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function submit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    api("/auth/login/", { method: "POST", body: { username, password } })
      .then(onLogin)
      .catch((err) => {
        setError(err.message);
        setSubmitting(false);
      });
  }

  return (
    <section className="step narrow" aria-labelledby="login-title">
      <h2 id="login-title">Prijava</h2>
      <form className="form" onSubmit={submit}>
        <Field label="Korisničko ime">
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
          />
        </Field>
        <Field label="Lozinka">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>
        <ErrorMessage>{error}</ErrorMessage>
        <button type="submit" className="button button-primary" disabled={submitting}>
          {submitting ? "Prijavljujem…" : "Prijava"}
        </button>
      </form>
    </section>
  );
}
