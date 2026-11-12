// Izračun iznosa za pregled dok se dokument uređuje. Ista pravila kao na
// poslužitelju (billing/money.py), koji ostaje mjerodavan. Računa se u cijelim
// brojevima (BigInt), jer decimalni brojevi u JavaScriptu griješe na centima.

/** "12,5" ili "12.5" → cijeli broj u jedinicama 10^-decimals; null ako nije broj. */
export function parseScaled(text, decimals) {
  const value = String(text ?? "").trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  if (fraction.length > decimals) return null;
  return BigInt(whole + fraction.padEnd(decimals, "0"));
}

function divideRoundHalfUp(numerator, denominator) {
  return (numerator * 2n + denominator) / (denominator * 2n);
}

/** Iznos stavke u centima, ili null ako neko polje nije ispravan broj. */
export function lineCents(item) {
  const quantity = parseScaled(item.quantity, 3);
  const price = parseScaled(item.unit_price, 2);
  const discount = parseScaled(item.discount_percent || "0", 2);
  if (quantity === null || price === null || discount === null || discount > 10000n) return null;
  // količina/1000 × cijena × (10000 − popust)/10000
  return divideRoundHalfUp(quantity * price * (10000n - discount), 1000n * 10000n);
}

/** Zbroj dokumenta u centima: osnovica, PDV po stopama (na osnovicu) i ukupno. */
export function totals(items, vatRegistered) {
  const bases = new Map();
  for (const item of items) {
    const cents = lineCents(item);
    if (cents === null) continue;
    const rate = vatRegistered ? Number(item.vat_rate || 0) : 0;
    bases.set(rate, (bases.get(rate) ?? 0n) + cents);
  }
  let net = 0n;
  let vat = 0n;
  const byRate = [...bases.entries()]
    .sort(([a], [b]) => a - b)
    .map(([rate, base]) => {
      const amount = divideRoundHalfUp(base * BigInt(rate), 100n);
      net += base;
      vat += amount;
      return { rate, base, vat: amount };
    });
  return { net, vat, total: net + vat, byRate };
}

/** Centi (BigInt) ili iznos s poslužitelja ("1234.50") → "1.234,50 €". */
export function formatMoney(value) {
  const cents = typeof value === "bigint" ? value : parseScaled(value, 2);
  if (cents === null) return "–";
  const text = cents.toString().padStart(3, "0");
  const whole = text.slice(0, -2).replace(/\B(?=(\d{3})+$)/g, ".");
  return `${whole},${text.slice(-2)} €`;
}

/** "2026-03-02" → "2. 3. 2026." */
export function formatDate(iso) {
  if (!iso) return "–";
  const [year, month, day] = iso.split("-").map(Number);
  return `${day}. ${month}. ${year}.`;
}

/** Današnji datum pomaknut za `days`, kao "GGGG-MM-DD" (lokalno vrijeme preglednika). */
export function dateFromToday(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
