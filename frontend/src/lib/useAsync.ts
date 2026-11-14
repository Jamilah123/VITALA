import { useCallback, useEffect, useState, type DependencyList } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

/** Run a read when the component mounts or `deps` change, cancelling any stale one. */
export function useAsync<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList): AsyncState<T> {
  const [state, setState] = useState<{ data?: T; error?: unknown; loading: boolean }>({ loading: true });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => ({ ...previous, error: undefined, loading: true }));
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ data, loading: false });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ error, loading: false });
      },
    );
    return () => controller.abort();
    // `load` is a new function each render; `deps` lists what it depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  const setData = useCallback((data: T) => setState({ data, loading: false }), []);

  return { data: state.data, error: state.error, loading: state.loading, reload, setData };
}
