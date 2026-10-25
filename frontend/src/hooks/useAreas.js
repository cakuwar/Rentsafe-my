// Loads the canonical area list (GET /price/areas) once per visit.
import { useEffect, useState } from "react";
import { getAreas } from "../api/client.js";

// Only a successful load is kept, so a page opened after a failure retries.
let loaded = null;

/** useAreas() -> { areas: [{ name, state }], loaded, failed } */
export function useAreas() {
  const [state, setState] = useState(() => loaded ?? { areas: [], loaded: false, failed: false });

  useEffect(() => {
    if (loaded) return undefined;
    let alive = true;
    getAreas()
      .then((data) => {
        loaded = { areas: data?.areas ?? [], loaded: true, failed: false };
        if (alive) setState(loaded);
      })
      .catch(() => {
        if (alive) setState({ areas: [], loaded: true, failed: true });
      });
    return () => {
      alive = false;
    };
  }, []);

  return state;
}
