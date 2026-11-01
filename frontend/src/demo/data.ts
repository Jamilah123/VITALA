// DEMO DATA ONLY. Invented content copied from docs/Vitala_App_Screens.pdf for an
// invented person. It is not computed from any profile, not clinically reviewed,
// and must never be merged with API data. Nothing under src/api imports this folder.

export const PERSONA = {
  name: "نورة",
  age: 31,
  sex: "أنثى",
  bmi: 23.5,
  conditions: "سكري · ضغط",
  medication: "ميتفورمين",
};

export type CheckStatus = "due" | "overdue" | "upcoming" | "done";
export type Tone = "rose" | "amber" | "green" | "blue" | "neutral";
export type CheckIcon = "drop" | "eye" | "pulse" | "flask";

export interface ResultSpec {
  label: string;
  unit: string;
  min: number;
  max: number;
}

export interface ResultEntry {
  date: string;
  value: string;
}

export interface DemoCheck {
  id: string;
  title: string;
  fullTitle: string;
  icon: CheckIcon;
  iconTone: Tone;
  iconLeaf?: boolean;
  cadence: string;
  detailCadence: string;
  status: CheckStatus;
  statusLabel: string;
  statusTone: Tone;
  section: "now" | "later";
  why: string;
  whyPersona: string;
  source: string;
  rule?: string;
  /** How a demo result is entered: a number, a blood-pressure pair, or only a date. */
  result: ResultSpec | "blood_pressure" | "date_only";
}

export const CHECKS: DemoCheck[] = [
  {
    id: "hba1c",
    title: "فحص السكري التراكمي",
    fullTitle: "فحص السكري التراكمي (HbA1c)",
    icon: "drop",
    iconTone: "amber",
    cadence: "لدى نورة سكري: متابعة كل 3 أشهر.",
    detailCadence: "كل 3 أشهر لمن لديهم سكري، أو حسب توجيه الطبيب.",
    status: "due",
    statusLabel: "مستحق بعد 5 أيام",
    statusTone: "amber",
    section: "now",
    why: "يعكس متوسط السكر في آخر 3 أشهر، ويساعد طبيبك على معرفة هل الخطة تعمل.",
    whyPersona: "لأن نورة سجّلت إصابتها بالسكري.",
    source: "ADA Standards of Care 2026 + إرشادات وزارة الصحة",
    rule: "DM-HBA1C-01 · آخر مراجعة: 2026-08-30",
    result: { label: "النتيجة", unit: "%", min: 3, max: 20 },
  },
  {
    id: "eye",
    title: "فحص العين للسكري",
    fullTitle: "فحص العين للسكري",
    icon: "eye",
    iconTone: "rose",
    cadence: "سنوياً لمرضى السكري.",
    detailCadence: "سنوياً لمرضى السكري، أو حسب توجيه الطبيب.",
    status: "overdue",
    statusLabel: "متأخر بأسبوعين",
    statusTone: "rose",
    section: "now",
    why: "قد تبدأ تغيرات العين المرتبطة بالسكري دون أعراض، والفحص يساعد على اكتشافها.",
    whyPersona: "لأن نورة سجّلت إصابتها بالسكري.",
    source: "ADA 2026",
    result: "date_only",
  },
  {
    id: "bp",
    title: "قياس ضغط الدم",
    fullTitle: "قياس ضغط الدم",
    icon: "pulse",
    iconTone: "amber",
    cadence: "في كل زيارة أو حسب مراقبة المنزل.",
    detailCadence: "في كل زيارة، أو حسب مراقبة المنزل التي يحددها الطبيب.",
    status: "due",
    statusLabel: "مستحق الآن",
    statusTone: "rose",
    section: "now",
    why: "قد يرتفع الضغط دون أعراض واضحة، والقياسات المسجّلة تساعد على متابعته.",
    whyPersona: "لأن نورة سجّلت إصابتها بالسكري والضغط.",
    source: "مثال توضيحي",
    result: "blood_pressure",
  },
  {
    id: "uacr",
    title: "وظائف الكلى (UACR)",
    fullTitle: "وظائف الكلى (UACR)",
    icon: "flask",
    iconTone: "blue",
    cadence: "سنوياً لمرضى السكري والضغط.",
    detailCadence: "سنوياً لمرضى السكري والضغط، أو حسب توجيه الطبيب.",
    status: "upcoming",
    statusLabel: "بعد شهرين",
    statusTone: "neutral",
    section: "later",
    why: "يساعد تقييم الكلى في متابعة تأثير السكري، وقد تتأخر الأعراض.",
    whyPersona: "لأن نورة سجّلت إصابتها بالسكري والضغط.",
    source: "ADA / ESC 2024",
    result: { label: "النتيجة", unit: "mg/g", min: 0, max: 5000 },
  },
  {
    id: "lipid",
    title: "ملف الدهون",
    fullTitle: "ملف الدهون",
    icon: "drop",
    iconTone: "green",
    cadence: "تم في مارس 2026.",
    detailCadence: "حسب توجيه الطبيب.",
    status: "done",
    statusLabel: "مكتمل",
    statusTone: "green",
    section: "later",
    why: "متابعة الدهون تساعد على تقييم صحة القلب والاستجابة للعلاج.",
    whyPersona: "لأن نورة سجّلت إصابتها بالسكري.",
    source: "وزارة الصحة",
    result: { label: "LDL", unit: "mg/dL", min: 10, max: 500 },
  },
];

export const getCheck = (id: string | undefined) => CHECKS.find((check) => check.id === id);

export const NEXT_STEP = {
  checkId: "hba1c",
  title: "فحص السكري التراكمي (HbA1c)",
  when: "بعد 5 أيام · الجمعة 6 نوفمبر",
};

export const ATTENTION = {
  checkId: "eye",
  title: "فحص العين للسكري",
  detail: "متأخر بأسبوعين.",
  badge: "متأخر",
};

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

export const LOG_GROUPS = [
  { checkId: "hba1c", title: "HbA1c", status: "في المسار" },
  { checkId: "bp", title: "ضغط الدم", status: "في المسار" },
  { checkId: "lipid", title: "ملف الدهون", status: "في المسار" },
  { checkId: "uacr", title: "UACR", status: "" },
  { checkId: "eye", title: "فحص العين", status: "" },
];

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

export const DOCTOR_CHECKLIST = [
  { id: "hba1c", title: "HbA1c كل 3 أشهر", detail: "بسبب السكري · ADA 2026", badge: "مستحق", tone: "amber" as Tone },
  { id: "eye", title: "قاع العين سنوياً", detail: "بسبب السكري · ADA 2026", badge: "متأخر", tone: "rose" as Tone },
  { id: "uacr", title: "UACR سنوياً", detail: "سكري وضغط · ADA / ESC 2024", badge: "قادم", tone: "amber" as Tone },
  { id: "lipid", title: "ملف الدهون", detail: "تم مارس 2026 · وزارة الصحة", badge: "مكتمل", tone: "green" as Tone },
];

export const DOCTOR_CONFIRMED_DEFAULT = ["hba1c", "uacr", "lipid"];

export const CITED_SOURCES = [
  { title: "وزارة الصحة السعودية", detail: "إرشادات الفحوصات الدورية، كما ذُكرت في شاشات التصميم." },
  { title: "ADA Standards of Care 2026", detail: "ذُكرت في شاشات التصميم مثالاً على مصدر توصية السكري." },
  { title: "ESC 2024", detail: "ذُكرت في شاشات التصميم مثالاً على مصدر توصية الضغط." },
];
