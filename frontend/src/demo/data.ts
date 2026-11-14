// DEMO DATA ONLY. Invented content copied from docs/Vitala_App_Screens.pdf for an
// invented person. It is not computed from any profile, not clinically reviewed,
// and must never be merged with API data. Nothing under src/api imports this folder.

export interface ResultEntry {
  date: string;
  value: string;
}

/** Newest first. Blood pressure values read systolic/diastolic. */
export const BASE_RESULTS: Record<string, ResultEntry[]> = {
  hba1c: [
    { date: "2026-07-15", value: "7.4%" },
    { date: "2026-04-15", value: "7.9%" },
  ],
  bp: [
    { date: "2026-09-15", value: "132/84 mmHg" },
    { date: "2026-06-15", value: "138/88 mmHg" },
  ],
  lipid: [{ date: "2026-03-15", value: "LDL 110 mg/dL" }],
};

export const HBA1C_TARGET = "أقل من 7.0%";

export const ACTIVITY = {
  goalMinutes: 150,
  doneMinutes: 98,
  /** Saturday first, as drawn in the PDF. These add up to doneMinutes. */
  days: [
    { label: "س", name: "السبت", minutes: 15 },
    { label: "أ", name: "الأحد", minutes: 19 },
    { label: "ن", name: "الاثنين", minutes: 9 },
    { label: "ث", name: "الثلاثاء", minutes: 21 },
    { label: "ر", name: "الأربعاء", minutes: 12 },
    { label: "خ", name: "الخميس", minutes: 17 },
    { label: "ج", name: "الجمعة", minutes: 5 },
  ],
  highlightDay: "ث",
  stepsToday: "6,420",
  averagePulse: "74",
  sleep: "6.8 س",
};

export const WATCH_OPTIONS = [
  { id: "steps", title: "الخطوات والدقائق النشطة", detail: "لمتابعة هدفك الأسبوعي", icon: "walk", tone: "blue" },
  { id: "pulse", title: "معدل النبض", detail: "اتجاه عام وليس تشخيصاً", icon: "heart", tone: "rose" },
  { id: "sleep", title: "النوم", detail: "مدة النوم التقديرية", icon: "moon", tone: "green" },
] as const;

export type WatchOption = (typeof WATCH_OPTIONS)[number]["id"];
