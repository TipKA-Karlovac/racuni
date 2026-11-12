import { useState } from "react";

import { api } from "../api.js";
import { ErrorMessage, Field, Loading, useLoad } from "../ui.jsx";

export default function Settings() {
  const { data, error } = useLoad("/company/");
  if (error) return <ErrorMessage>{error}</ErrorMessage>;
  if (!data) return <Loading />;
  return <CompanyForm company={data} />;
}

function CompanyForm({ company }) {
  const [form, setForm] = useState(company);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  function change(event) {
    const { name, type, checked, value } = event.target;
    setForm({ ...form, [name]: type === "checkbox" ? checked : value });
    setSaved(false);
  }

  function submit(event) {
    event.preventDefault();
    setError("");
    setSaving(true);
    api("/company/", { method: "PUT", body: { ...form, due_days: Number(form.due_days) } })
      .then((result) => {
        setForm(result);
        setSaved(true);
      })
      .catch((err) => setError(err.message))
      .finally(() => setSaving(false));
  }

  const text = (name, label, extra = {}) => (
    <Field label={label} hint={extra.hint} className={extra.className}>
      <input name={name} value={form[name]} onChange={change} maxLength={extra.maxLength} />
    </Field>
  );

  return (
    <form className="step form" onSubmit={submit} noValidate>
      <h2>Podaci izdavatelja</h2>
      <p className="muted">Ovi podaci ispisuju se u zaglavlju svake ponude i računa.</p>

      <div className="grid">
        {text("name", "Naziv obrta ili tvrtke", { className: "span-2", maxLength: 120 })}
        {text("owner", "Vlasnik", { maxLength: 80 })}
        {text("oib", "OIB", { maxLength: 11 })}
        {text("address", "Adresa", { maxLength: 120 })}
        {text("city", "Poštanski broj i mjesto", { maxLength: 80 })}
        {text("iban", "IBAN", { hint: "Na ovaj račun kupci plaćaju; ulazi u barkod.", maxLength: 34 })}
        {text("email", "E-pošta")}
        {text("phone", "Telefon", { maxLength: 30 })}
      </div>

      <h3>Računi</h3>
      <label className="check">
        <input type="checkbox" name="vat_registered" checked={form.vat_registered} onChange={change} />
        Izdavatelj je u sustavu PDV-a
      </label>
      <div className="grid">
        {text("premise_code", "Oznaka poslovnog prostora", { maxLength: 10 })}
        {text("device_code", "Oznaka naplatnog uređaja", { maxLength: 10 })}
        <Field label="Rok plaćanja (dana)">
          <input name="due_days" type="number" min="0" max="365" value={form.due_days} onChange={change} />
        </Field>
      </div>
      <p className="hint">
        Broj računa ima oblik redni broj / poslovni prostor / naplatni uređaj, npr. 12/
        {form.premise_code || "1"}/{form.device_code || "1"}.
      </p>
      <Field
        label="Napomena na dnu svakog dokumenta"
        hint="Npr. napomena o oslobođenju od PDV-a za izdavatelje izvan sustava PDV-a."
      >
        <textarea name="footer_note" value={form.footer_note} onChange={change} rows={3} maxLength={600} />
      </Field>

      <ErrorMessage>{error}</ErrorMessage>
      {saved && (
        <p className="alert alert-ok" role="status">
          Postavke su spremljene.
        </p>
      )}
      <div>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? "Spremam…" : "Spremi postavke"}
        </button>
      </div>
    </form>
  );
}
