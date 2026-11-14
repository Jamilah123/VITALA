// How the pre-appointment summary presents each recorded value. "absent" is only
// ever an explicit negative from the record; anything not recorded is "unknown".

import type { ConditionStatus, DiabetesType, PreAppointmentSummary, ScreeningRecord, Sex, SmokingStatus, YesNoUnknown } from "../api/types";
import { ageFrom, formatDate } from "./dates";
import { DIABETES_TYPE_LABELS, SEX_LABELS } from "./profile";
import { SMOKING_LABELS } from "./riskProfile";
import { testGroup } from "./screening";

export type FactState = "documented" | "absent" | "unknown";

export interface Fact {
  text: string;
  state: FactState;
}

const UNKNOWN: Fact = { text: "غير معروف", state: "unknown" };

export function conditionFact(status: ConditionStatus): Fact {
  if (status === "diagnosed") return { text: "مشخّص", state: "documented" };
  if (status === "not_diagnosed") return { text: "غير مشخّص", state: "absent" };
  return UNKNOWN;
}

export function yesNoFact(value: YesNoUnknown): Fact {
  if (value === "yes") return { text: "نعم", state: "documented" };
  if (value === "no") return { text: "لا", state: "absent" };
  return UNKNOWN;
}

export function diabetesTypeFact(type: DiabetesType): Fact {
  return type === "unknown" ? UNKNOWN : { text: DIABETES_TYPE_LABELS[type], state: "documented" };
}

export function smokingFact(status: SmokingStatus): Fact {
  if (status === "unknown") return UNKNOWN;
  return { text: SMOKING_LABELS[status], state: status === "never" ? "absent" : "documented" };
}

export function sexFact(sex: Sex): Fact {
  return sex === "unknown" ? UNKNOWN : { text: SEX_LABELS[sex], state: "documented" };
}

export function ageFact(dateOfBirth: string | null): Fact {
  return dateOfBirth ? { text: `${ageFrom(dateOfBirth)} سنة · ${formatDate(dateOfBirth)}`, state: "documented" } : UNKNOWN;
}

export function measureFact(value: number | null, unit: string): Fact {
  return value === null ? UNKNOWN : { text: `${value} ${unit}`, state: "documented" };
}

export function dateFact(iso: string | null): Fact {
  return iso ? { text: formatDate(iso), state: "documented" } : UNKNOWN;
}

export interface SummaryRecord extends ScreeningRecord {
  test_name_ar: string;
}

/** Every recorded screening, newest first, including records whose test is no longer mapped. */
export function allRecords(summary: PreAppointmentSummary): SummaryRecord[] {
  const names = Object.fromEntries(summary.screening.tests.map((test) => [test.test_id, test.name_ar]));
  const records = [...summary.screening.tests.flatMap((test) => test.recorded_tests), ...summary.screening.unmapped_records];
  return records
    .map((record) => ({ ...record, test_name_ar: names[record.test_id] ?? record.test_id }))
    .sort((a, b) => b.completed_on.localeCompare(a.completed_on) || b.id - a.id);
}

export function screeningGroups(summary: PreAppointmentSummary) {
  const tests = summary.screening.tests;
  return {
    candidates: tests.filter((test) => testGroup(test) === "candidate"),
    undecided: tests.filter((test) => testGroup(test) === "needs_information"),
    otherCount: tests.filter((test) => testGroup(test) === "other").length,
  };
}

/** The catalogue name, plus the name on the report only when it differs. */
export function recordLabel(catalogueName: string, reportName: string): string {
  return reportName.trim() === catalogueName ? catalogueName : `${catalogueName} · ${reportName}`;
}
