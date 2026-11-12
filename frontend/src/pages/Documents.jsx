import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { formatDate, formatMoney } from "../money.js";
import { ErrorMessage, Loading, StatusBadge, useLoad } from "../ui.jsx";

const FILTERS = {
  invoice: [
    ["", "Svi"],
    ["draft", "Nacrti"],
    ["issued", "Nenaplaćeni"],
    ["overdue", "Kasne"],
    ["paid", "Plaćeni"],
    ["cancelled", "Stornirani"],
  ],
  quote: [
    ["", "Sve"],
    ["draft", "Nacrti"],
    ["issued", "Bez odgovora"],
    ["accepted", "Prihvaćene"],
    ["rejected", "Odbijene"],
    ["cancelled", "Stornirane"],
  ],
};

export default function Documents({ kind }) {
  const [params, setParams] = useSearchParams();
  const active = params.get("overdue") === "1" ? "overdue" : (params.get("status") ?? "");
  const search = params.get("search") ?? "";
  const [typed, setTyped] = useState(search);

  // Pretraga kreće tek kad korisnik zastane s tipkanjem.
  useEffect(() => {
    if (typed === search) return undefined;
    const timer = setTimeout(() => {
      const next = new URLSearchParams(params);
      if (typed) next.set("search", typed);
      else next.delete("search");
      setParams(next, { replace: true });
    }, 300);
    return () => clearTimeout(timer);
  }, [typed, search, params, setParams]);

  const query = new URLSearchParams({ kind });
  if (active === "overdue") query.set("overdue", "1");
  else if (active) query.set("status", active);
  if (search) query.set("search", search);
  const { data, error } = useLoad(`/documents/?${query}`);

  function choose(filter) {
    const next = new URLSearchParams();
    if (filter === "overdue") next.set("overdue", "1");
    else if (filter) next.set("status", filter);
    if (search) next.set("search", search);
    setParams(next);
  }

  const isInvoice = kind === "invoice";
  return (
    <section className="step">
      <div className="toolbar">
        <h2>{isInvoice ? "Računi" : "Ponude"}</h2>
        <Link className="button button-primary" to={`/novi/${kind}`}>
          {isInvoice ? "Novi račun" : "Nova ponuda"}
        </Link>
      </div>

      <div className="filters">
        <div className="tabs" role="group" aria-label="Filtar">
          {FILTERS[kind].map(([value, label]) => (
            <button
              key={value}
              type="button"
              className="tab"
              aria-pressed={active === value}
              onClick={() => choose(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          type="search"
          className="search"
          placeholder="Broj ili klijent"
          aria-label="Pretraga po broju ili klijentu"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
      </div>

      <ErrorMessage>{error}</ErrorMessage>
      {!data && !error && <Loading />}
      {data && data.length === 0 && <p className="muted">Nema dokumenata za ovaj prikaz.</p>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Broj</th>
                <th>Klijent</th>
                <th>Izdano</th>
                <th>{isInvoice ? "Rok plaćanja" : "Vrijedi do"}</th>
                <th className="number">Iznos</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((document) => (
                <tr key={document.id}>
                  <td>
                    <Link to={`/dokument/${document.id}`}>{document.number || "(nacrt)"}</Link>
                  </td>
                  <td>{document.client_name}</td>
                  <td>{formatDate(document.issue_date)}</td>
                  <td>{formatDate(document.due_date)}</td>
                  <td className="number">{formatMoney(document.total)}</td>
                  <td>
                    <StatusBadge status={document.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
