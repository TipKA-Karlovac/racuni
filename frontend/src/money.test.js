import { describe, expect, it } from "vitest";

import { formatDate, formatMoney, lineCents, parseScaled, totals } from "./money.js";

const item = (quantity, unit_price, discount_percent = "0", vat_rate = "25") => ({
  quantity,
  unit_price,
  discount_percent,
  vat_rate,
});

describe("parseScaled", () => {
  it("prima zarez i točku", () => {
    expect(parseScaled("12,5", 2)).toBe(1250n);
    expect(parseScaled("12.5", 2)).toBe(1250n);
    expect(parseScaled("7", 3)).toBe(7000n);
  });

  it("odbija ono što nije broj ili ima previše decimala", () => {
    for (const bad of ["", "abc", "-1", "1.2.3", "1,005"]) expect(parseScaled(bad, 2)).toBeNull();
  });
});

describe("lineCents", () => {
  // Isti primjeri kao u testovima poslužitelja (billing/tests/test_money.py).
  it.each([
    ["1", "100", "0", 10000n],
    ["2.5", "30", "0", 7500n],
    ["12", "25", "10", 27000n],
    ["1", "99.99", "100", 0n],
    ["0.333", "10", "0", 333n],
    ["3", "0.33", "0.5", 99n], // 0,98505 → 0,99
  ])("%s × %s uz popust %s %%", (quantity, price, discount, expected) => {
    expect(lineCents(item(quantity, price, discount))).toBe(expected);
  });

  it("vraća null za neispravan unos", () => {
    expect(lineCents(item("", "100"))).toBeNull();
    expect(lineCents(item("1", "abc"))).toBeNull();
    expect(lineCents(item("1", "100", "101"))).toBeNull();
  });

  it("ne griješi na velikim iznosima", () => {
    expect(lineCents(item("9999999.999", "9999999999.99"))).toBe(9999999998990000000n);
  });
});

describe("totals", () => {
  it("računa PDV na osnovicu po stopi, ne po stavci", () => {
    const result = totals([item("1", "0.10"), item("1", "0.10"), item("1", "0.10")], true);
    expect([result.net, result.vat, result.total]).toEqual([30n, 8n, 38n]);
  });

  it("grupira po stopi", () => {
    const result = totals([item("1", "100"), item("2", "50", "0", "13"), item("1", "40")], true);
    expect(result.byRate).toEqual([
      { rate: 13, base: 10000n, vat: 1300n },
      { rate: 25, base: 14000n, vat: 3500n },
    ]);
    expect(result.total).toBe(28800n);
  });

  it("izvan sustava PDV-a nema PDV-a", () => {
    const result = totals([item("1", "100")], false);
    expect([result.net, result.vat, result.total]).toEqual([10000n, 0n, 10000n]);
  });

  it("preskače nedovršene stavke", () => {
    expect(totals([item("1", "100"), item("", "")], false).total).toBe(10000n);
  });
});

describe("prikaz", () => {
  it("piše iznose na hrvatski način", () => {
    expect(formatMoney(0n)).toBe("0,00 €");
    expect(formatMoney(5n)).toBe("0,05 €");
    expect(formatMoney(123450n)).toBe("1.234,50 €");
    expect(formatMoney("1234567.89")).toBe("1.234.567,89 €");
  });

  it("piše datume na hrvatski način", () => {
    expect(formatDate("2026-03-02")).toBe("2. 3. 2026.");
    expect(formatDate(null)).toBe("–");
  });
});
