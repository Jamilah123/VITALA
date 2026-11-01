import type { ConditionStatus, DiabetesType, Patient, PatientInput, Sex } from "../api/types";

export const SEX_LABELS: Record<Sex, string> = { female: "أنثى", male: "ذكر", unknown: "غير محدد" };

export const STATUS_LABELS: Record<ConditionStatus, string> = {
  diagnosed: "مشخّص",
  not_diagnosed: "غير مشخّص",
  unknown: "غير معروف",
};

export const DIABETES_TYPE_LABELS: Record<DiabetesType, string> = {
  type_1: "النوع الأول",
  type_2: "النوع الثاني",
  other: "نوع آخر",
  unknown: "غير معروف",
};

const DRUG_CLASS_LABELS: Record<string, string> = {
  biguanide: "بيغوانيد",
  ace_inhibitor: "مثبطات الإنزيم المحوّل للأنجيوتنسين",
  arb: "حاصرات مستقبلات الأنجيوتنسين",
  thiazide_diuretic: "مدرّات البول الثيازيدية",
  statin: "الستاتينات",
  vitamin_k_antagonist: "مضادات فيتامين K",
  csdmard: "الأدوية المعدّلة لمسار المرض",
};

export const drugClassLabel = (drugClass: string): string => DRUG_CLASS_LABELS[drugClass] ?? drugClass;

/**
 * The status fields as the API needs them. Leaving "diagnosed" must clear the
 * type and dates in the same request, or the backend rejects the update.
 */
export function conditionFields(diabetes: ConditionStatus, hypertension: ConditionStatus): PatientInput {
  return {
    diabetes_status: diabetes,
    hypertension_status: hypertension,
    ...(diabetes !== "diagnosed" && { diabetes_type: "unknown" as const, diabetes_diagnosis_date: null }),
    ...(hypertension !== "diagnosed" && { hypertension_diagnosis_date: null }),
  };
}

export interface ProfileDraft {
  date_of_birth: string;
  sex: Sex;
  diabetes_status: ConditionStatus;
  diabetes_type: DiabetesType;
  diabetes_diagnosis_date: string;
  hypertension_status: ConditionStatus;
  hypertension_diagnosis_date: string;
}

export function draftFromPatient(patient: Patient): ProfileDraft {
  return {
    date_of_birth: patient.date_of_birth ?? "",
    sex: patient.sex,
    diabetes_status: patient.diabetes_status,
    diabetes_type: patient.diabetes_type,
    diabetes_diagnosis_date: patient.diabetes_diagnosis_date ?? "",
    hypertension_status: patient.hypertension_status,
    hypertension_diagnosis_date: patient.hypertension_diagnosis_date ?? "",
  };
}

export function draftToUpdate(draft: ProfileDraft): PatientInput {
  return {
    date_of_birth: draft.date_of_birth || null,
    sex: draft.sex,
    diabetes_type: draft.diabetes_type,
    diabetes_diagnosis_date: draft.diabetes_diagnosis_date || null,
    hypertension_diagnosis_date: draft.hypertension_diagnosis_date || null,
    ...conditionFields(draft.diabetes_status, draft.hypertension_status),
  };
}

/** One line such as "السكري: مشخّص · الضغط: غير معروف". Never hides what is unknown. */
export function conditionsSummary(patient: Patient): string {
  return [
    `السكري: ${STATUS_LABELS[patient.diabetes_status]}`,
    `الضغط: ${STATUS_LABELS[patient.hypertension_status]}`,
  ].join(" · ");
}

export interface BmiResult {
  value: number;
  /** Null when no adult category applies: the WHO adult bands do not fit under-18s. */
  category: string | null;
}

export function computeBmi(heightCm: number, weightKg: number, age: number | null): BmiResult {
  const value = Math.round((weightKg / (heightCm / 100) ** 2) * 10) / 10;
  if (age === null || age < 18) return { value, category: null };
  let category = "ضمن النطاق الطبيعي";
  if (value < 18.5) category = "أقل من النطاق الطبيعي";
  else if (value >= 30) category = "ضمن نطاق السمنة";
  else if (value >= 25) category = "أعلى من النطاق الطبيعي";
  return { value, category };
}
