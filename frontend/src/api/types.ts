// Mirrors backend/app/schemas.py. Unknown is not negative: only "not_diagnosed"
// says that a condition is absent, and a null date means not known.

export type Sex = "male" | "female" | "unknown";
export type ConditionStatus = "diagnosed" | "not_diagnosed" | "unknown";
export type DiabetesType = "type_1" | "type_2" | "other" | "unknown";

export interface Patient {
  id: number;
  date_of_birth: string | null;
  sex: Sex;
  diabetes_status: ConditionStatus;
  diabetes_type: DiabetesType;
  diabetes_diagnosis_date: string | null;
  hypertension_status: ConditionStatus;
  hypertension_diagnosis_date: string | null;
}

export type PatientInput = Partial<Omit<Patient, "id">>;

export interface MedicationUse {
  id: number;
  patient_id: number;
  medication_id: string;
  dose_text: string;
  start_date: string | null;
  last_dose_change_date: string | null;
}

export interface MedicationUseCreate {
  medication_id: string;
  dose_text: string;
  start_date: string | null;
  last_dose_change_date: string | null;
}

export type MedicationUseUpdate = Partial<Omit<MedicationUseCreate, "medication_id">>;

export interface CatalogueMedication {
  id: string;
  generic_name: string;
  name_ar: string;
  drug_class: string;
  brand_names: string[];
}

export interface Health {
  status: string;
  database: string;
}

// Screening: every rule and mapping is an unreviewed draft. The backend sends no
// due dates, and the UI must not derive any.

export type RuleStatus = "candidate" | "needs_information" | "not_applicable" | "not_triggered";
export type RecordSource = "patient_reported" | "lab_report" | "clinician_entered" | "device";
export type MissingReason = "unknown" | "not_collected";

export interface MissingInput {
  field: string;
  reason: MissingReason;
  affects_eligibility: boolean;
}

export interface SummaryMissingInput extends MissingInput {
  rule_ids: string[];
}

export interface SourceReference {
  source_id: string;
  locator: string;
  title: string;
  issuer: string;
  url: string;
  version: string | null;
  limitation_ar: string;
}

export interface ScreeningAction {
  rule_id: string;
  track: string;
  action_id: string;
  action_name_ar: string;
  eligibility_ar: string;
  status: RuleStatus;
  reasons: string[];
  missing_inputs: MissingInput[];
  matched_medication_ids: string[];
  schedule_text_ar: string;
  notes_ar: string;
  review_flags: string[];
  conflict_ids: string[];
  knowledge_ids: string[];
  sources: SourceReference[];
  review_status: string;
  auto_schedule_enabled: false;
}

export interface ScreeningRecord {
  id: number;
  patient_id: number;
  test_id: string;
  test_name: string;
  completed_on: string;
  result: string | null;
  unit: string | null;
  source: RecordSource;
  notes: string | null;
}

export interface ScreeningRecordCreate {
  test_id: string;
  test_name: string;
  completed_on: string;
  result: string | null;
  unit: string | null;
  source: RecordSource;
  notes: string | null;
}

export interface ScreeningTest {
  id: string;
  name_ar: string;
  rule_ids: string[];
  possible_overlap_test_ids: string[];
  mapping_status: string;
}

export interface HistoryInput {
  mapping_id: string;
  version: number;
  field: string;
  kind: "completion_date" | "test_on_record";
  status: "pending_review" | "approved";
  applied: boolean;
  changes_eligibility: boolean;
  rule_ids: string[];
  record_count: number;
  latest_completed_on: string | null;
  latest_record_id: number | null;
}

export interface AmbiguousHistoryField {
  test_id: string;
  field: string;
  rule_ids: string[];
  reason: string;
}

export interface ScreeningTestSummary {
  test_id: string;
  name_ar: string;
  mapping_status: string;
  recorded_tests: ScreeningRecord[];
  history_inputs: HistoryInput[];
  ambiguous_history_fields: AmbiguousHistoryField[];
  candidate_rule_ids: string[];
  needs_information_rule_ids: string[];
  not_applicable_rule_ids: string[];
  not_triggered_rule_ids: string[];
  missing_inputs: SummaryMissingInput[];
  review_reasons: string[];
  conflict_ids: string[];
  possible_overlap_test_ids: string[];
  rules: ScreeningAction[];
}

export interface ScreeningSummary {
  patient_id: number;
  evaluated_on: string;
  clinically_approved: false;
  auto_schedule_enabled: false;
  notice_ar: string;
  tests: ScreeningTestSummary[];
  unmapped_records: ScreeningRecord[];
}
