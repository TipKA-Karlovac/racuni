import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api.js";

export function Loading({ children = "Učitavam…" }) {
  return (
    <p className="muted" role="status">
      {children}
    </p>
  );
}

export function ErrorMessage({ children }) {
  if (!children) return null;
  return (
    <p className="alert alert-error" role="alert">
      {children}
    </p>
  );
}

/** Dohvaća podatke s adrese `path`; `reload()` ih dohvaća ponovno. */
export function useLoad(path) {
  const [state, setState] = useState({ path: null, data: null, error: "" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path) return undefined;
    const controller = new AbortController();
    api(path, { signal: controller.signal })
      .then((data) => setState({ path, data, error: "" }))
      .catch((err) => {
        if (err.name !== "AbortError") setState({ path, data: null, error: err.message });
      });
    return () => controller.abort();
  }, [path, version]);

  const reload = useCallback(() => setVersion((current) => current + 1), []);
  // Dok stiže odgovor za novu adresu, stari podaci se ne prikazuju.
  const current = state.path === path ? state : { data: null, error: "" };
  return { data: current.data, error: current.error, reload };
}

export const STATUS_LABELS = {
  draft: "nacrt",
  issued: "izdano",
  paid: "plaćeno",
  accepted: "prihvaćeno",
  rejected: "odbijeno",
  cancelled: "stornirano",
};

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}

export function Field({ label, error, hint, children, className = "" }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
      {error && (
        <span className="field-error" role="alert">
          {error}
        </span>
      )}
    </label>
  );
}

/** Potvrda prije radnje koja se ne može poništiti. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  danger = false,
  busy,
  onConfirm,
  onClose,
}) {
  const ref = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="dialog" onClose={onClose} aria-labelledby="dialog-title">
      <h2 id="dialog-title">{title}</h2>
      <div className="dialog-body">{children}</div>
      <div className="actions">
        <button type="button" className="button button-quiet" onClick={onClose} disabled={busy}>
          Odustani
        </button>
        <button
          type="button"
          className={`button ${danger ? "button-danger" : "button-primary"}`}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? "Samo trenutak…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
