import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { readJson, removeKey, writeJson } from "../lib/browserStore";
import { ACTIVITY, BASE_RESULTS, type ResultEntry, type WatchOption } from "./data";

// DEMO ONLY. What the user does on demo screens stays in this browser under its
// own key, apart from the patient id and browser profile. Nothing here reaches the API.

const STORAGE_KEY = "vitala.demo.v1";

export type PrivacySetting = "watch" | "reminders" | "sharing";

interface DemoState {
  addedResults: Record<string, ResultEntry[]>;
  watch: Record<WatchOption, boolean>;
  privacy: Record<PrivacySetting, boolean>;
  reminders: string[];
  activityGoal: number;
}

const INITIAL: DemoState = {
  addedResults: {},
  watch: { steps: true, pulse: true, sleep: false },
  privacy: { watch: true, reminders: true, sharing: false },
  reminders: [],
  activityGoal: ACTIVITY.goalMinutes,
};

interface DemoStore extends DemoState {
  update: (changes: Partial<DemoState>) => void;
  addResult: (checkId: string, entry: ResultEntry) => void;
  resultsFor: (checkId: string) => ResultEntry[];
  hasAddedResults: (checkId: string) => boolean;
  reset: () => void;
}

const DemoContext = createContext<DemoStore | null>(null);

export function DemoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DemoState>(() => ({ ...INITIAL, ...readJson<Partial<DemoState>>(STORAGE_KEY) }));

  useEffect(() => writeJson(STORAGE_KEY, state), [state]);

  const store = useMemo<DemoStore>(
    () => ({
      ...state,
      update: (changes) => setState((previous) => ({ ...previous, ...changes })),
      addResult: (checkId, entry) =>
        setState((previous) => ({
          ...previous,
          addedResults: {
            ...previous.addedResults,
            [checkId]: [...(previous.addedResults[checkId] ?? []), entry],
          },
        })),
      resultsFor: (checkId) =>
        [...(state.addedResults[checkId] ?? []), ...(BASE_RESULTS[checkId] ?? [])].sort((a, b) =>
          b.date.localeCompare(a.date),
        ),
      hasAddedResults: (checkId) => (state.addedResults[checkId]?.length ?? 0) > 0,
      reset: () => {
        removeKey(STORAGE_KEY);
        setState(INITIAL);
      },
    }),
    [state],
  );

  return <DemoContext.Provider value={store}>{children}</DemoContext.Provider>;
}

export function useDemo(): DemoStore {
  const store = useContext(DemoContext);
  if (!store) throw new Error("useDemo must be used inside DemoProvider");
  return store;
}
