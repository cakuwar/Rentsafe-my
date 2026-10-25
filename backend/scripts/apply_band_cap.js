// Apply the backend's real scoring + band cap to a batch of NLP results.
// Used by nlp-service/eval/cap_cost.py so the cost of the cap is measured with
// the production code, not a re-implementation of it.
//
//   stdin:  [{ p, status, confidence, redFlags: [...] }, ...]
//   stdout: [{ uncapped: { total, band }, capped: { total, band, bandCap } }, ...]
//
// Only the NLP signal is supplied: OSINT and price are not implemented, so
// production requests are scored on NLP alone today (maxPossible 60).
import { aggregateScore, capUnsupportedScore } from "../src/services/scoring.service.js";

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const rows = JSON.parse(input);
  const out = rows.map(({ p, status, confidence, redFlags }) => {
    const nlp = { scamProbability: p, status, confidence };
    const scoring = aggregateScore({ nlp });
    const capped = capUnsupportedScore(scoring, { scamProbability: p, status, redFlags });
    return {
      uncapped: { total: scoring.total, band: scoring.band },
      capped: { total: capped.total, band: capped.band, bandCap: capped.bandCap },
    };
  });
  process.stdout.write(JSON.stringify(out));
});
