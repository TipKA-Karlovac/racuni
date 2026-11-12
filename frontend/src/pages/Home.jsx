import { Link } from "react-router-dom";

import { formatMoney } from "../money.js";
import { ErrorMessage, Loading, useLoad } from "../ui.jsx";

export default function Home() {
  const summary = useLoad("/summary/");
  const company = useLoad("/company/");

  if (summary.error || company.error) {
    return <ErrorMessage>{summary.error || company.error}</ErrorMessage>;
  }
  if (!summary.data || !company.data) return <Loading />;

  const data = summary.data;
  const missing = company.data.missing_for_issuing;

  return (
    <>
      {missing.length > 0 && (
        <p className="alert">
          Prije izdavanja prvog dokumenta upišite podatke izdavatelja ({missing.join(", ")}) u{" "}
          <Link to="/postavke">postavkama</Link>.
        </p>
      )}

      <div className="cards">
        <Card label="Nenaplaćeno" value={formatMoney(data.unpaid_total)}>
          <Link to="/racuni?status=issued">Računa: {data.unpaid_count}</Link>
        </Card>
        <Card label="Kasni s plaćanjem" value={formatMoney(data.overdue_total)} warn={data.overdue_count > 0}>
          <Link to="/racuni?overdue=1">Računa: {data.overdue_count}</Link>
        </Card>
        <Card label="Izdano ove godine" value={formatMoney(data.invoiced_this_year)}>
          <Link to="/racuni">Svi računi</Link>
        </Card>
        <Card label="Ponude bez odgovora" value={data.open_quotes}>
          <Link to="/ponude?status=issued">Otvori ponude</Link>
        </Card>
      </div>

      <div className="actions actions-start">
        <Link className="button button-primary" to="/novi/invoice">
          Novi račun
        </Link>
        <Link className="button button-quiet" to="/novi/quote">
          Nova ponuda
        </Link>
      </div>
    </>
  );
}

function Card({ label, value, warn = false, children }) {
  return (
    <section className={warn ? "card card-warn" : "card"}>
      <h2>{label}</h2>
      <p className="card-value">{value}</p>
      <p className="card-link">{children}</p>
    </section>
  );
}
