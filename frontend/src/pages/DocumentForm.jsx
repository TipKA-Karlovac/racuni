import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api.js";
import { dateFromToday, formatMoney, lineCents, totals } from "../money.js";
import { ErrorMessage, Field, Loading, useLoad } from "../ui.jsx";

const EMPTY_ITEM = {
  description: "",
  quantity: "1",
  unit: "kom",
  unit_price: "",
  discount_percent: "0",
  vat_rate: "25",
};
const VAT_RATES = ["25", "13", "5", "0"];

/** Novi dokument (/novi/:kind) ili uređivanje nacrta (/dokument/:id/uredi). */
export default function DocumentForm() {
  const { id, kind } = useParams();
  const company = useLoad("/company/");
  const clients = useLoad("/clients/");
  const existing = useLoad(id ? `/documents/${id}/` : null);

  const error = company.error || clients.error || existing.error;
  if (error) return <ErrorMessage>{error}</ErrorMessage>;
  if (!company.data || !clients.data || (id && !existing.data)) return <Loading />;
  if (!id && kind !== "invoice" && kind !== "quote") return <p>Stranica ne postoji.</p>;
  if (existing.data && existing.data.status !== "draft") {
    return (
      <p className="alert">
        Izdani dokument se ne može mijenjati.{" "}
        <Link to={`/dokument/${id}`}>Povratak na dokument</Link>
      </p>
    );
  }
  return (
    <Editor
      key={id ?? kind}
      company={company.data}
      clients={clients.data}
      document={existing.data}
      kind={existing.data?.kind ?? kind}
    />
  );
}

function Editor({ company, clients, document, kind }) {
  const navigate = useNavigate();
  const isInvoice = kind === "invoice";
  const [form, setForm] = useState({
    client: document ? String(document.client) : "",
    due_date: document?.due_date ?? dateFromToday(isInvoice ? company.due_days : 15),
    delivery_date: document?.delivery_date ?? "",
    note: document?.note ?? "",
  });
  const [items, setItems] = useState(
    document?.items.length
      ? document.items.map((item) => ({
          description: item.description,
          quantity: trimZeros(item.quantity),
          unit: item.unit,
          unit_price: item.unit_price.replace(".", ","),
          discount_percent: trimZeros(item.discount_percent),
          vat_rate: trimZeros(item.vat_rate),
        }))
      : [EMPTY_ITEM],
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Klijent nacrta možda je u međuvremenu arhiviran, pa ga nema na popisu.
  const options = [...clients];
  if (document && !options.some((client) => client.id === document.client)) {
    options.push({ id: document.client, name: document.client_name });
  }

  const sum = totals(items, company.vat_registered);

  const change = (event) => setForm({ ...form, [event.target.name]: event.target.value });
  const changeItem = (index, name, value) =>
    setItems(items.map((item, at) => (at === index ? { ...item, [name]: value } : item)));

  function submit(event) {
    event.preventDefault();
    if (!form.client) return setError("Odaberite klijenta.");
    if (items.some((item) => !item.description.trim() || lineCents(item) === null)) {
      return setError("Provjerite stavke: svaka treba opis, količinu i cijenu.");
    }
    setError("");
    setSaving(true);
    const body = {
      kind,
      client: Number(form.client),
      due_date: form.due_date,
      delivery_date: isInvoice && form.delivery_date ? form.delivery_date : null,
      note: form.note.trim(),
      items: items.map((item) => ({
        description: item.description.trim(),
        unit: item.unit.trim() || "kom",
        quantity: decimal(item.quantity),
        unit_price: decimal(item.unit_price),
        discount_percent: decimal(item.discount_percent || "0"),
        vat_rate: company.vat_registered ? item.vat_rate : "0",
      })),
    };
    const request = document
      ? api(`/documents/${document.id}/`, { method: "PUT", body })
      : api("/documents/", { method: "POST", body });
    return request
      .then((saved) => navigate(`/dokument/${saved.id}`))
      .catch((err) => {
        setError(err.message);
        setSaving(false);
      });
  }

  if (clients.length === 0 && !document) {
    return (
      <p className="alert">
        Najprije <Link to="/klijenti">dodajte klijenta</Link>, a zatim izradite dokument.
      </p>
    );
  }

  const title = `${document ? "Uređivanje nacrta" : "Novi nacrt"} – ${isInvoice ? "račun" : "ponuda"}`;
  return (
    <form className="step form" onSubmit={submit} noValidate>
      <h2>{title}</h2>

      <div className="grid">
        <Field label="Klijent" className="span-2">
          <select name="client" value={form.client} onChange={change}>
            <option value="">– odaberite –</option>
            {options.map((client) => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label={isInvoice ? "Rok plaćanja" : "Ponuda vrijedi do"}>
          <input type="date" name="due_date" value={form.due_date} onChange={change} required />
        </Field>
        {isInvoice && (
          <Field label="Datum isporuke" hint="Prazno = datum izdavanja">
            <input type="date" name="delivery_date" value={form.delivery_date} onChange={change} />
          </Field>
        )}
      </div>

      <div className="table-wrap">
        <table className="table items">
          <thead>
            <tr>
              <th>Opis</th>
              <th className="number">Količina</th>
              <th>Jed.</th>
              <th className="number">Cijena (€)</th>
              <th className="number">Popust %</th>
              {company.vat_registered && <th>PDV %</th>}
              <th className="number">Iznos</th>
              <th>
                <span className="visually-hidden">Ukloni</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => {
              const cents = lineCents(item);
              const input = (name, label, extra = {}) => (
                <input
                  aria-label={`${label}, stavka ${index + 1}`}
                  value={item[name]}
                  onChange={(event) => changeItem(index, name, event.target.value)}
                  {...extra}
                />
              );
              return (
                <tr key={index}>
                  <td className="wide">{input("description", "Opis", { maxLength: 200 })}</td>
                  <td>{input("quantity", "Količina", { inputMode: "decimal", className: "number" })}</td>
                  <td>{input("unit", "Jedinica", { maxLength: 10, className: "short" })}</td>
                  <td>{input("unit_price", "Cijena", { inputMode: "decimal", className: "number" })}</td>
                  <td>
                    {input("discount_percent", "Popust", { inputMode: "decimal", className: "number short" })}
                  </td>
                  {company.vat_registered && (
                    <td>
                      <select
                        aria-label={`PDV, stavka ${index + 1}`}
                        value={item.vat_rate}
                        onChange={(event) => changeItem(index, "vat_rate", event.target.value)}
                      >
                        {VAT_RATES.map((rate) => (
                          <option key={rate}>{rate}</option>
                        ))}
                      </select>
                    </td>
                  )}
                  <td className="number amount">{cents === null ? "–" : formatMoney(cents)}</td>
                  <td>
                    <button
                      type="button"
                      className="link"
                      aria-label={`Ukloni stavku ${index + 1}`}
                      onClick={() => setItems(items.filter((_, at) => at !== index))}
                      disabled={items.length === 1}
                    >
                      ukloni
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div>
        <button type="button" className="button button-quiet" onClick={() => setItems([...items, EMPTY_ITEM])}>
          + Dodaj stavku
        </button>
      </div>

      <dl className="totals">
        {company.vat_registered && (
          <>
            <dt>Osnovica</dt>
            <dd>{formatMoney(sum.net)}</dd>
            {sum.byRate.map((line) => (
              <VatRow key={line.rate} line={line} />
            ))}
          </>
        )}
        <dt className="total">Ukupno</dt>
        <dd className="total">{formatMoney(sum.total)}</dd>
      </dl>

      <Field label="Napomena (ispisuje se na dokumentu)">
        <textarea name="note" value={form.note} onChange={change} rows={3} maxLength={600} />
      </Field>

      <ErrorMessage>{error}</ErrorMessage>
      <div className="actions actions-start">
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? "Spremam…" : "Spremi nacrt"}
        </button>
        <Link className="button button-quiet" to={document ? `/dokument/${document.id}` : "/"}>
          Odustani
        </Link>
      </div>
      <p className="hint">
        Nacrt nema broj i možete ga mijenjati. Broj i datum dobiva tek izdavanjem.
      </p>
    </form>
  );
}

function VatRow({ line }) {
  return (
    <>
      <dt>PDV {line.rate} %</dt>
      <dd>{formatMoney(line.vat)}</dd>
    </>
  );
}

/** "12,5" → "12.5": poslužitelj očekuje decimalnu točku. */
const decimal = (text) => String(text).trim().replace(",", ".");

/** "2.500" → "2,5", "1.000" → "1": prikaz bez suvišnih nula, s decimalnim zarezom. */
function trimZeros(text) {
  const value = String(text);
  const trimmed = value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
  return trimmed.replace(".", ",");
}
