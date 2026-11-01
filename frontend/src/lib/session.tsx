import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { readJson, removeKey, writeJson } from "./browserStore";

// The backend has no login yet, so "the current patient" is just an id this
// browser remembers. Health data itself is read from the API, not cached here.

const PATIENT_KEY = "vitala.patientId";

/**
 * Details the backend has no fields for yet. They stay in this browser and are
 * labelled that way wherever they appear. They are not demo data: the user typed them.
 */
export interface BrowserProfile {
  height: string;
  weight: string;
  dyslipidemia: boolean;
  familyHistory: string[];
}

const EMPTY_BROWSER_PROFILE: BrowserProfile = { height: "", weight: "", dyslipidemia: false, familyHistory: [] };

const browserProfileKey = (patientId: number) => `vitala.browserProfile.${patientId}`;

export function readBrowserProfile(patientId: number | null): BrowserProfile {
  if (patientId === null) return EMPTY_BROWSER_PROFILE;
  return { ...EMPTY_BROWSER_PROFILE, ...readJson<Partial<BrowserProfile>>(browserProfileKey(patientId)) };
}

export function saveBrowserProfile(patientId: number, changes: Partial<BrowserProfile>): void {
  writeJson(browserProfileKey(patientId), { ...readBrowserProfile(patientId), ...changes });
}

interface Session {
  patientId: number | null;
  setPatientId: (id: number) => void;
  forgetPatient: () => void;
}

const SessionContext = createContext<Session | null>(null);

function readStoredId(): number | null {
  const stored = readJson<unknown>(PATIENT_KEY);
  return typeof stored === "number" && Number.isInteger(stored) && stored > 0 ? stored : null;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [patientId, setId] = useState<number | null>(readStoredId);

  const setPatientId = useCallback((id: number) => {
    writeJson(PATIENT_KEY, id);
    setId(id);
  }, []);

  const forgetPatient = useCallback(() => {
    removeKey(PATIENT_KEY);
    setId(null);
  }, []);

  const value = useMemo(() => ({ patientId, setPatientId, forgetPatient }), [patientId, setPatientId, forgetPatient]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside SessionProvider");
  return session;
}
