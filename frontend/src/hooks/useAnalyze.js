// Hook managing the analyse request lifecycle.
import { useCallback, useState } from "react";
import { analyzeText, analyzeScreenshot, describeError } from "../api/client.js";

/**
 * useAnalyze() -> { result, loading, error, runText, runScreenshot, reset }
 * - runText(text, language, details) / runScreenshot(files, details) set
 *   loading, clear the error, call the matching api/client function, store the
 *   result or the error (see describeError), and clear loading in a finally
 *   block. Each resolves to the result, or null when the request failed.
 */
export function useAnalyze() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async (call) => {
    setLoading(true);
    setError(null);
    try {
      const data = await call();
      setResult(data);
      return data;
    } catch (failure) {
      setError(describeError(failure));
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const runText = useCallback(
    (text, language = "auto", details = {}) => run(() => analyzeText(text, language, details)),
    [run],
  );
  const runScreenshot = useCallback(
    (files, details = {}) => run(() => analyzeScreenshot(files, details)),
    [run],
  );
  const reset = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return { result, loading, error, runText, runScreenshot, reset };
}
