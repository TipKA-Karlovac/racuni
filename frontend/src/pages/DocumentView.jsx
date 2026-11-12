import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api.js";
import { formatDate, formatMoney } from "../money.js";
import { ConfirmDialog, ErrorMessage, Loading, StatusBadge, useLoad } from "../ui.jsx";

// Radnje koje traže potvrdu, s tekstom koji objašnjava posljedicu.
const CONFIRMATIONS = {
  issue: {
    title: "Izdati dokument?",
    label: "Izdaj",
    text: "Dokument dobiva sljedeći broj i današnji datum. Nakon izdavanja ga više ne možete mijenjati ni obrisati, samo stornirati.",
  },
  cancel: {
    title: "Stornirati dokument?",
    label: "Storniraj",
    danger: true,
    text: "Dokument ostaje u evidenciji kao storniran, a njegov broj se ne koristi ponovno. Storno se ne može poništiti.",
  },
  delete: {
    title: "Obrisati nacrt?",
    label: "Obriši",
    danger: true,
    text: "Nacrt se trajno briše. Ovo se ne može poništiti.",
  },
};

export default function DocumentView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, error: loadError, reload } = useLoad(`/documents/${id}/`);
  const [fresh, setFresh] = useState(null);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(null);
  const [busy, setBusy] = useState(false);

  if (loadError) return <ErrorMessage>{loadError}</ErrorMessage>;
  if (!data) return <Loading />;

  // Nakon radnje poslužitelj vrati novo stanje dokumenta; ono ima prednost.
  const document = fresh?.id === data.id ? fresh : data;
  const { kind, status } = document;
  const isInvoice = kind === "invoice";
  const base = `/documents/${document.id}/`;

  function run(action) {
    setBusy(true);
    setError("");
    const request =
      action === "delete"
        ? api(base, { method: "DELETE" }).then(() => navigate(isInvoice ? "/racuni" : "/ponude"))
        : api(`${base}${action}/`, { method: "POST" }).then((result) => {
            if (action === "to-invoice") navigate(`/dokument/${result.id}`);
            else setFresh(result);
          });
    request
      .catch((err) => {
        setError(err.message);
        reload();
      })
      .finally(() => {
        setBusy(false);
        setConfirming(null);
      });
  }

  const button = (label, onClick, style = "button-quiet") => (
    <button type="button" className={`button ${style}`} onClick={onClick} disabled={busy}>
      {label}
    </button>
  );

  const name = isInvoice ? "Račun" : "Ponuda";
  const confirmation = confirming && CONFIRMATIONS[confirming];
  return (
    <section className="step">
      <div className="toolbar">
        <h2>
          {name} {document.number || "(nacrt)"}
        </h2>
        <StatusBadge status={status} />
      </div>

      <div className="actions actions-start">
        {status === "draft" && (
          <>
            {button("Izdaj", () => setConfirming("issue"), "button-primary")}
            <Link className="button button-quiet" to={`/dokument/${document.id}/uredi`}>
              Uredi
            </Link>
          </>
        )}
        <a className="button button-quiet" href={`/api${base}pdf/`} target="_blank" rel="noreferrer">
          PDF
        </a>
        {isInvoice && status === "issued" && button("Označi plaćenim", () => run("mark-paid"), "button-primary")}
        {!isInvoice && status === "issued" && (
          <>
            {button("Prihvaćena", () => run("accept"), "button-primary")}
            {button("Odbijena", () => run("reject"))}
          </>
        )}
        {!isInvoice && (status === "issued" || status === "accepted") && button("Izradi račun", () => run("to-invoice"))}
        {status === "draft" && button("Obriši", () => setConfirming("delete"))}
        {status !== "draft" && status !== "cancelled" && button("Storniraj", () => setConfirming("cancel"))}
      </div>

      <ErrorMessage>{error}</ErrorMessage>

      <dl className="details">
        <dt>Klijent</dt>
        <dd>{document.client_name}</dd>
        <dt>Datum izdavanja</dt>
        <dd>{formatDate(document.issue_date)}</dd>
        {isInvoice && document.delivery_date && (
          <>
            <dt>Datum isporuke</dt>
            <dd>{formatDate(document.delivery_date)}</dd>
          </>
        )}
        <dt>{isInvoice ? "Rok plaćanja" : "Vrijedi do"}</dt>
        <dd>{formatDate(document.due_date)}</dd>
        {document.source && (
          <>
            <dt>Nastalo iz</dt>
            <dd>
              <Link to={`/dokument/${document.source}`}>ponude</Link>
            </dd>
          </>
        )}
      </dl>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Opis</th>
              <th className="number">Količina</th>
              <th className="number">Cijena</th>
              <th className="number">Popust</th>
              <th className="number">Iznos</th>
            </tr>
          </thead>
          <tbody>
            {document.items.map((item, index) => (
              <tr key={index}>
                <td>{item.description}</td>
                <td className="number">
                  {Number(item.quantity).toLocaleString("hr-HR")} {item.unit}
                </td>
                <td className="number">{formatMoney(item.unit_price)}</td>
                <td className="number">
                  {Number(item.discount_percent) ? `${Number(item.discount_percent).toLocaleString("hr-HR")} %` : ""}
                </td>
                <td className="number">{formatMoney(item.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <dl className="totals">
        {Number(document.vat_total) > 0 && (
          <>
            <dt>Osnovica</dt>
            <dd>{formatMoney(document.net_total)}</dd>
            {document.vat_breakdown.map((line) => (
              <VatRow key={line.rate} line={line} />
            ))}
          </>
        )}
        <dt className="total">Ukupno</dt>
        <dd className="total">{formatMoney(document.total)}</dd>
      </dl>

      {document.note && <p className="note-block">{document.note}</p>}

      <ConfirmDialog
        open={confirming !== null}
        title={confirmation?.title}
        confirmLabel={confirmation?.label}
        danger={confirmation?.danger}
        busy={busy}
        onConfirm={() => run(confirming)}
        onClose={() => setConfirming(null)}
      >
        <p>{confirmation?.text}</p>
      </ConfirmDialog>
    </section>
  );
}

function VatRow({ line }) {
  return (
    <>
      <dt>PDV {Number(line.rate).toLocaleString("hr-HR")} %</dt>
      <dd>{formatMoney(line.vat)}</dd>
    </>
  );
}
