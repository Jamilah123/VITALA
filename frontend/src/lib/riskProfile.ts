// Risk factors are stored for the patient and the doctor. The screening engine
// does not read them, and nothing here interprets them clinically.

import { api } from "../api/client";
import type { FamilyHistoryField, RiskProfile, RiskProfileInput, SmokingStatus, YesNoUnknown } from "../api/types";
import type { BrowserProfile } from "./session";
import { parseNumber, rangeError, type FieldErrors } from "./validation";

export const SMOKING_LABELS: Record<SmokingStatus, string> = {
  current: "مدخّن حالياً",
  former: "مدخّن سابقاً",
  never: "غير مدخّن",
  unknown: "غير معروف",
};

export const YES_NO_LABELS: Record<YesNoUnknown, string> = { yes: "نعم", no: "لا", unknown: "غير معروف" };

export const FAMILY_CONDITIONS: { field: FamilyHistoryField; label: string; browserLabel: string }[] = [
  { field: "family_diabetes", label: "السكري", browserLabel: "سكري" },
  { field: "family_heart_disease", label: "أمراض القلب", browserLabel: "أمراض القلب" },
  { field: "family_breast_cancer", label: "سرطان الثدي", browserLabel: "سرطان الثدي" },
  { field: "family_colorectal_cancer", label: "سرطان القولون", browserLabel: "القولون" },
];

export interface RiskDraft extends Record<FamilyHistoryField, YesNoUnknown> {
  smoking_status: SmokingStatus;
  height: string;
  weight: string;
  activity: string;
  raised_lipids: YesNoUnknown;
  pregnancy_status: YesNoUnknown;
}

export const UNKNOWN_DRAFT: RiskDraft = {
  smoking_status: "unknown",
  height: "",
  weight: "",
  activity: "",
  raised_lipids: "unknown",
  pregnancy_status: "unknown",
  family_diabetes: "unknown",
  family_heart_disease: "unknown",
  family_breast_cancer: "unknown",
  family_colorectal_cancer: "unknown",
};

const text = (value: number | null) => (value === null ? "" : String(value));

export function draftFromRisk(profile: RiskProfile): RiskDraft {
  return {
    smoking_status: profile.smoking_status,
    height: text(profile.height_cm),
    weight: text(profile.weight_kg),
    activity: text(profile.activity_minutes_per_week),
    raised_lipids: profile.raised_lipids,
    pregnancy_status: profile.pregnancy_status,
    family_diabetes: profile.family_diabetes,
    family_heart_disease: profile.family_heart_disease,
    family_breast_cancer: profile.family_breast_cancer,
    family_colorectal_cancer: profile.family_colorectal_cancer,
  };
}

/** Error keys match the API field names, so server errors land on the same inputs. */
export function validateRiskDraft(draft: Pick<RiskDraft, "height" | "weight" | "activity">): FieldErrors {
  const errors: FieldErrors = {};
  if (draft.height.trim()) {
    const error = rangeError(draft.height, 50, 250, "سم");
    if (error) errors.height_cm = error;
  }
  if (draft.weight.trim()) {
    const error = rangeError(draft.weight, 2, 350, "كجم");
    if (error) errors.weight_kg = error;
  }
  if (draft.activity.trim()) {
    const minutes = parseNumber(draft.activity);
    if (minutes === null || !Number.isInteger(minutes) || minutes > 10080) {
      errors.activity_minutes_per_week = "يلزم إدخال عدد صحيح من الدقائق بين 0 و10080.";
    }
  }
  return errors;
}

export const numberOrNull = (value: string) => (value.trim() ? parseNumber(value) : null);

export function riskInputFromDraft(draft: RiskDraft): RiskProfileInput {
  return {
    smoking_status: draft.smoking_status,
    height_cm: numberOrNull(draft.height),
    weight_kg: numberOrNull(draft.weight),
    activity_minutes_per_week: numberOrNull(draft.activity),
    raised_lipids: draft.raised_lipids,
    pregnancy_status: draft.pregnancy_status,
    family_diabetes: draft.family_diabetes,
    family_heart_disease: draft.family_heart_disease,
    family_breast_cancer: draft.family_breast_cancer,
    family_colorectal_cancer: draft.family_colorectal_cancer,
  };
}

export function saveRiskProfile(patientId: number, stored: boolean, input: Partial<RiskProfileInput>): Promise<RiskProfile> {
  return stored ? api.updateRiskProfile(patientId, input) : api.createRiskProfile(patientId, input);
}

export function hasBrowserData(browser: BrowserProfile): boolean {
  return Boolean(browser.height.trim() || browser.weight.trim() || browser.dyslipidemia || browser.familyHistory.length > 0);
}

export interface ImportPlan {
  input: Partial<RiskProfileInput>;
  imported: string[];
  skipped: string[];
}

/**
 * What the one-time import would send. It only fills values the server does not
 * have, and it never turns an unselected option into "no".
 */
export function planBrowserImport(browser: BrowserProfile, server: RiskProfile): ImportPlan {
  const plan: ImportPlan = { input: {}, imported: [], skipped: [] };

  const measurement = (raw: string, field: "height_cm" | "weight_kg", label: string, min: number, max: number) => {
    if (!raw.trim()) return;
    const value = parseNumber(raw);
    if (value === null || value < min || value > max) plan.skipped.push(`${label}: قيمة غير صالحة`);
    else if (server[field] !== null) plan.skipped.push(`${label}: محفوظ في الخادم مسبقاً`);
    else {
      plan.input[field] = value;
      plan.imported.push(label);
    }
  };
  measurement(browser.height, "height_cm", "الطول", 50, 250);
  measurement(browser.weight, "weight_kg", "الوزن", 2, 350);

  const yes = (field: "raised_lipids" | FamilyHistoryField, label: string) => {
    if (server[field] !== "unknown") plan.skipped.push(`${label}: محفوظ في الخادم مسبقاً`);
    else {
      plan.input[field] = "yes";
      plan.imported.push(label);
    }
  };
  if (browser.dyslipidemia) yes("raised_lipids", "ارتفاع الدهون");
  for (const condition of FAMILY_CONDITIONS) {
    if (browser.familyHistory.includes(condition.browserLabel)) yes(condition.field, `تاريخ العائلة: ${condition.label}`);
  }
  return plan;
}
