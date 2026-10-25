// Helpers shared by the price evaluation scripts, matching scripts/baseline
// (the Python build) so a stratum here is the stratum the database holds.

/** Same folding as scripts/baseline/schema.building_key. */
export function buildingKey(name) {
  const key = (name ?? "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  return key || null;
}

/** pandas' default (linear) quantile, on an ascending array. */
export function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}
