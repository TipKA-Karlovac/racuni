import { useState } from "react";

import { api } from "../api.js";
import { ErrorMessage, Field, Loading, useLoad } from "../ui.jsx";

const EMPTY = { name: "", address: "", city: "", oib: "", email: "" };

export default function Clients() {
  const [showArchived, setShowArchived] = useState(false);
  const { data, error: loadError, reload } = useLoad(`/clients/${showArchived ? "?archived=1" : ""}`);
  const [editing, setEditing] = useState(null); // null, EMPTY ili klijent
  const [error, setError] = useState("");

  function act(request) {
    setError("");
    request.then(reload).catch((err) => setError(err.message));
  }

  return (
    <section className="step">
      <div className="toolbar">
        <h2>Klijenti</h2>
        <button type="button" className="button button-primary" onClick={() => setEditing(EMPTY)}>
          Novi klijent
        </button>
      </div>

      {editing && (
        <ClientForm
          key={editing.id ?? "novi"}
          client={editing}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}

      <label className="check">
        <input
          type="checkbox"
          checked={showArchived}
          onChange={(event) => setShowArchived(event.target.checked)}
        />
        Prikaži i arhivirane
      </label>

      <ErrorMessage>{loadError || error}</ErrorMessage>
      {!data && !loadError && <Loading />}
      {data && data.length === 0 && <p className="muted">Još nema klijenata.</p>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Naziv</th>
                <th>Adresa</th>
                <th>OIB</th>
                <th>E-pošta</th>
                <th>
                  <span className="visually-hidden">Radnje</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((client) => (
                <tr key={client.id} className={client.archived ? "archived" : ""}>
                  <td>{client.name}</td>
                  <td>{[client.address, client.city].filter(Boolean).join(", ")}</td>
                  <td>{client.oib}</td>
                  <td>{client.email}</td>
                  <td className="row-actions">
                    <button type="button" className="link" onClick={() => setEditing(client)}>
                      uredi
                    </button>
                    <button
                      type="button"
                      className="link"
                      onClick={() =>
                        act(
                          api(`/clients/${client.id}/`, {
                            method: "PUT",
                            body: { ...client, archived: !client.archived },
                          }),
                        )
                      }
                    >
                      {client.archived ? "vrati" : "arhiviraj"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">
        Arhivirani klijent se ne nudi pri izradi novih dokumenata, a postojeći dokumenti ostaju.
      </p>
    </section>
  );
}

function ClientForm({ client, onSaved, onCancel }) {
  const [form, setForm] = useState({ ...EMPTY, ...client });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const change = (event) => setForm({ ...form, [event.target.name]: event.target.value });

  function submit(event) {
    event.preventDefault();
    if (!form.name.trim()) return setError("Upišite naziv klijenta.");
    if (form.oib && !/^\d{11}$/.test(form.oib.trim())) return setError("OIB ima točno 11 znamenaka.");
    setError("");
    setSaving(true);
    const body = Object.fromEntries(
      Object.entries(form).map(([key, value]) => [key, typeof value === "string" ? value.trim() : value]),
    );
    const request = client.id
      ? api(`/clients/${client.id}/`, { method: "PUT", body })
      : api("/clients/", { method: "POST", body });
    return request.then(onSaved).catch((err) => {
      setError(err.message);
      setSaving(false);
    });
  }

  return (
    <form className="form panel" onSubmit={submit} noValidate>
      <h3>{client.id ? "Uređivanje klijenta" : "Novi klijent"}</h3>
      <div className="grid">
        <Field label="Naziv ili ime i prezime" className="span-2">
          <input name="name" value={form.name} onChange={change} maxLength={120} autoFocus />
        </Field>
        <Field label="Adresa">
          <input name="address" value={form.address} onChange={change} maxLength={120} />
        </Field>
        <Field label="Poštanski broj i mjesto">
          <input name="city" value={form.city} onChange={change} maxLength={80} />
        </Field>
        <Field label="OIB" hint="Nije obavezan za građane">
          <input name="oib" value={form.oib} onChange={change} maxLength={11} inputMode="numeric" />
        </Field>
        <Field label="E-pošta">
          <input name="email" type="email" value={form.email} onChange={change} />
        </Field>
      </div>
      <ErrorMessage>{error}</ErrorMessage>
      <div className="actions actions-start">
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? "Spremam…" : "Spremi"}
        </button>
        <button type="button" className="button button-quiet" onClick={onCancel}>
          Odustani
        </button>
      </div>
    </form>
  );
}
