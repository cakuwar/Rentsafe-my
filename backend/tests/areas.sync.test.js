// The backend's area / property vocabulary must match scripts/scrapers/config.py,
// which builds the baseline: an area spelled differently on each side would
// never find its stratum.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it, expect } from "vitest";
import {
  CANONICAL_AREAS,
  DUAL_STATE_AREAS,
  PROPERTY_TYPES,
  ROOM_TYPES,
} from "../src/config/areas.js";

const CONFIG = fs.readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../scripts/scrapers/config.py"),
  "utf8",
);

/** The text of a top-level Python assignment `NAME = <literal>`. */
function block(name, open, close) {
  const start = CONFIG.indexOf(`\n${name} = ${open}`);
  if (start < 0) throw new Error(`${name} not found in config.py`);
  let depth = 0;
  for (let i = CONFIG.indexOf(open, start); i < CONFIG.length; i += 1) {
    if (CONFIG[i] === open) depth += 1;
    if (CONFIG[i] === close) depth -= 1;
    if (depth === 0) return CONFIG.slice(start, i + 1);
  }
  throw new Error(`${name} is not closed`);
}

const pairs = (text) => [...text.matchAll(/"([^"]+)":\s*"([^"]*)"/g)].map(([, k, v]) => [k, v]);

describe("areas.js mirrors scripts/scrapers/config.py", () => {
  it("has the same canonical areas and states", () => {
    expect(Object.fromEntries(pairs(block("CANONICAL_AREAS", "{", "}")))).toEqual(CANONICAL_AREAS);
  });

  it("has the same dual-state names, each resolving to two canonical areas", () => {
    const names = [...block("DUAL_STATE_AREAS", "{", "}").matchAll(/"([A-Za-z ]+)"/g)].map((m) => m[1])
      .filter((n) => !["Kuala Lumpur", "Selangor"].includes(n));
    expect(names.map((n) => n.toLowerCase()).sort()).toEqual(Object.keys(DUAL_STATE_AREAS).sort());
    for (const options of Object.values(DUAL_STATE_AREAS)) {
      for (const area of Object.values(options)) expect(CANONICAL_AREAS[area], area).toBeTruthy();
    }
  });

  it("has the same property types (studio aside) and room types", () => {
    const types = [...block("PROPERTY_TYPES", "(", ")").matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
    expect(types.filter((t) => t !== "studio").sort()).toEqual([...PROPERTY_TYPES].sort());
    expect([...block("ROOM_TYPES", "(", ")").matchAll(/"([a-z]+)"/g)].map((m) => m[1])).toEqual([...ROOM_TYPES]);
  });
});
