// Form checks that give immediate feedback in Arabic. They repeat the backend's
// data-entry rules (backend/app/validation.py), which stay the final authority.
// None of this is a clinical judgement.

import { isValidIsoDate, todayIso } from "./dates";

export type FieldErrors = Record<string, string>;

const ARABIC_DIGITS = /[٠-٩۰-۹]/g;

/** Read a number typed with Western or Arabic digits. Returns null if it is not one. */
export function parseNumber(text: string): number | null {
  const normalized = text
    .trim()
    .replace(ARABIC_DIGITS, (digit) => {
      const code = digit.charCodeAt(0);
      return String(code >= 0x06f0 ? code - 0x06f0 : code - 0x0660);
    })
    .replace("٫", ".");
  if (!/^\d+(\.\d+)?$/.test(normalized)) return null;
  return Number(normalized);
}

function dateError(value: string, today = todayIso()): string | null {
  if (!isValidIsoDate(value) || value < "1900-01-01") return "أدخلي تاريخاً صحيحاً.";
  if (value > today) return "لا يمكن أن يكون التاريخ في المستقبل.";
  return null;
}

export function rangeError(text: string, min: number, max: number, unit: string): string | null {
  const value = parseNumber(text);
  if (value === null || value < min || value > max) return `أدخلي رقماً بين ${min} و${max} ${unit}.`;
  return null;
}

export function validateBasics(input: { dateOfBirth: string; height: string; weight: string }): FieldErrors {
  const errors: FieldErrors = {};
  if (input.dateOfBirth) {
    const error = dateError(input.dateOfBirth);
    if (error) errors.date_of_birth = error;
  }
  if (input.height.trim()) {
    const error = rangeError(input.height, 50, 250, "سم");
    if (error) errors.height = error;
  }
  if (input.weight.trim()) {
    const error = rangeError(input.weight, 2, 350, "كجم");
    if (error) errors.weight = error;
  }
  return errors;
}

export interface ProfileDates {
  date_of_birth: string;
  diabetes_diagnosis_date: string;
  hypertension_diagnosis_date: string;
}

export function validateProfileDates(input: ProfileDates): FieldErrors {
  const errors: FieldErrors = {};
  const birth = input.date_of_birth;
  if (birth) {
    const error = dateError(birth);
    if (error) errors.date_of_birth = error;
  }
  for (const field of ["diabetes_diagnosis_date", "hypertension_diagnosis_date"] as const) {
    const value = input[field];
    if (!value) continue;
    const error = dateError(value);
    if (error) errors[field] = error;
    else if (birth && value < birth) errors[field] = "لا يمكن أن يسبق تاريخ التشخيص تاريخ الميلاد.";
  }
  return errors;
}

export interface MedicationInput {
  medication_id: string;
  dose_text: string;
  start_date: string;
  last_dose_change_date: string;
}

export function validateMedication(
  input: MedicationInput,
  birth: string | null,
  takenIds: readonly string[] = [],
): FieldErrors {
  const errors: FieldErrors = {};
  if (!input.medication_id) errors.medication_id = "اختاري دواءً من القائمة.";
  else if (takenIds.includes(input.medication_id)) errors.medication_id = "هذا الدواء مسجّل مسبقاً في ملفك.";

  const dose = input.dose_text.trim();
  if (!dose) errors.dose_text = "اكتبي الجرعة كما وصفها طبيبك.";
  else if (dose.length > 200) errors.dose_text = "يجب ألا تتجاوز الجرعة 200 حرف.";

  for (const field of ["start_date", "last_dose_change_date"] as const) {
    const value = input[field];
    if (!value) continue;
    const error = dateError(value);
    if (error) errors[field] = error;
    else if (birth && value < birth) errors[field] = "لا يمكن أن يسبق التاريخ تاريخ الميلاد.";
  }
  if (
    input.start_date &&
    input.last_dose_change_date &&
    input.last_dose_change_date < input.start_date &&
    !errors.last_dose_change_date
  ) {
    errors.last_dose_change_date = "لا يمكن أن يسبق آخر تغيير للجرعة تاريخ البدء.";
  }
  return errors;
}

export function validateResultDate(value: string): string | null {
  if (!value) return "أدخلي تاريخ النتيجة.";
  return dateError(value);
}

export function validateBloodPressure(systolic: string, diastolic: string): FieldErrors {
  const errors: FieldErrors = {};
  const high = rangeError(systolic, 60, 260, "mmHg");
  const low = rangeError(diastolic, 30, 160, "mmHg");
  if (high) errors.systolic = high;
  if (low) errors.diastolic = low;
  if (!high && !low && parseNumber(diastolic)! >= parseNumber(systolic)!) {
    errors.diastolic = "يجب أن يكون الانبساطي أقل من الانقباضي.";
  }
  return errors;
}
