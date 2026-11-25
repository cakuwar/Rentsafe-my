// E3: re-score blind cases 3, 4, 5, 12 and 14 against the full baseline and the
// baseline rebuilt without the scraped rows, with the production scorer
// (scoreAgainstBaseline / isScorable from the copied price.service.js).
// Reads each case's recorded stratum and listed price from the repo (read-only);
// prints no personal data.  node rescore_blind.mjs
// The two baseline builds live in working copies OUTSIDE the repo
// (~/rentsafe_experiments_data/e3_price/{full,no_scraped}); see scripts/e3/README.md.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WORK = path.join(os.homedir(), "rentsafe_experiments_data", "e3_price");
const OUT = path.join(HERE, "..", "..", "results", "e3", "rescore_blind.json");
const { isScorable, scoreAgainstBaseline } = await import(
  pathToFileURL(path.join(WORK, "full/backend/src/services/price.service.js")).href);
const CASES = "C:/Users/U S E R/Documents/fyp/rentsafe-my/data/test_real/cases";
const read = (p) => JSON.parse(fs.readFileSync(p, "utf8").replace(/^\uFEFF/, ""));
const builds = {
  current: read(path.join(WORK, "full/data/processed/external_coverage.json")),
  no_scraped: read(path.join(WORK, "no_scraped/data/processed/external_coverage.json")),
};

function cell(cov, s) {
  if (s.propertyType === "room") {
    return cov.rooms.cells.find((c) => c.area === s.area && c.room_type === s.roomType);
  }
  return cov.whole_units.cells.find((c) => c.area === s.area && c.property_type === s.propertyType
    && Number(c.bedrooms) === Number(s.bedrooms));
}

const out = [];
for (const id of ["case03", "case04", "case05", "case12", "case14"]) {
  const recorded = read(path.join(CASES, id, "api_result.json")).evidence.price;
  const s = recorded.stratum;
  const row = { case: id, stratum: s, price: recorded.listedPrice,
    recorded: { median: recorded.baseline.median, p25: recorded.baseline.p25,
      n: recorded.baseline.sampleSize, buildings: recorded.baseline.buildings,
      sources: recorded.baseline.sources, deviation: recorded.deviation, points: recorded.points,
      guard: recorded.guard } };
  for (const [name, cov] of Object.entries(builds)) {
    const c = cell(cov, s);
    if (!c) { row[name] = { status: "no stratum" }; continue; }
    const base = { median: c.median, p25: c.p25, n: c.listings, buildings: c.buildings, sources: c.sources };
    if (!isScorable(c.listings, c.buildings)) { row[name] = { ...base, status: c.status, points: 0, scored: false }; continue; }
    const sc = scoreAgainstBaseline(recorded.listedPrice, { median: c.median, p25: c.p25 });
    row[name] = { ...base, status: c.status, scored: true, deviation: sc.deviation, points: sc.points, guard: sc.guard };
  }
  out.push(row);
}
fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
for (const r of out) {
  const f = (x) => x.scored === false ? `${x.status}, not scored (n=${x.n}, ${x.buildings} bldg)`
    : `median ${x.median}, p25 ${x.p25}, n=${x.n}/${x.buildings} bldg, dev ${x.deviation}, ${x.points} pts${x.guard ? " (guard)" : ""}`;
  console.log(`${r.case} ${JSON.stringify(r.stratum)} RM${r.price}`);
  console.log(`   recorded:   median ${r.recorded.median}, p25 ${r.recorded.p25}, n=${r.recorded.n}/${r.recorded.buildings} bldg, dev ${r.recorded.deviation}, ${r.recorded.points} pts [${r.recorded.sources}]`);
  console.log(`   current:    ${f(r.current)} [${r.current.sources}]`);
  console.log(`   no scraped: ${f(r.no_scraped)} [${r.no_scraped.sources}]`);
}
