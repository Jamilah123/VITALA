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
  /** "archived": outside the metformin + ACE inhibitor scope; kept so recorded uses keep their names. */
  status?: "active" | "archived";
}

export type SmokingStatus = "current" | "former" | "never" | "unknown";
export type YesNoUnknown = "yes" | "no" | "unknown";

export type FamilyHistoryField = "family_diabetes" | "family_heart_disease" | "family_breast_cancer" | "family_colorectal_cancer";

/** Not read by the screening engine. "unknown" and null never mean "no". */
export interface RiskProfileInput extends Record<FamilyHistoryField, YesNoUnknown> {
  smoking_status: SmokingStatus;
  height_cm: number | null;
  weight_kg: number | null;
  activity_minutes_per_week: number | null;
  raised_lipids: YesNoUnknown;
  pregnancy_status: YesNoUnknown;
}

export interface RiskProfile extends RiskProfileInput {
  patient_id: number;
  /** False when nothing is saved yet; every value is then unknown. */
  stored: boolean;
  bmi: number | null;
}

// Clinic workspace. Every clinic row is synthetic in this prototype; choosing the
// clinic entry grants no access and protects nothing.

export interface Clinic {
  id: number;
  name_ar: string;
  city_ar: string | null;
  /** IANA name used to show appointment times, which arrive in UTC. */
  time_zone: string;
  is_demo: boolean;
}

export interface Doctor {
  id: number;
  clinic_id: number;
  name_ar: string;
  specialty_ar: string | null;
}

export interface ClinicPatient {
  id: number;
  clinic_id: number;
  display_name_ar: string;
  file_number: string | null;
  patient: Patient;
}

export type AppointmentStatus = "scheduled" | "completed" | "cancelled" | "no_show";
export type BookingSource = "vitala" | "clinic" | "unknown";

export interface Appointment {
  id: number;
  clinic_id: number;
  doctor_id: number;
  clinic_patient_id: number;
  scheduled_at: string;
  status: AppointmentStatus;
  booking_source: BookingSource;
  visit_reason_ar: string | null;
}

/** Demo only: no authentication. The server sets status and booking source itself. */
export interface AppointmentCreate {
  clinic_patient_id: number;
  doctor_id: number;
  /** ISO 8601 with an offset; the server stores UTC. */
  scheduled_at: string;
  visit_reason_ar: string | null;
}

export type AppointmentUpdate = Partial<Omit<AppointmentCreate, "clinic_patient_id">>;
export type AppointmentOutcome = Exclude<AppointmentStatus, "scheduled">;

export interface AppointmentDetail {
  appointment: Appointment;
  doctor: Doctor;
  patient: ClinicPatient;
}

export interface SummaryMedication {
  id: number;
  medication_id: string;
  /** Null when the id is not in the catalogue. Medication records store no source. */
  name_ar: string | null;
  generic_name: string | null;
  drug_class: string | null;
  dose_text: string;
  start_date: string | null;
  last_dose_change_date: string | null;
}

/** Read-only, built from existing records. Never clinically validated. */
export interface PreAppointmentSummary {
  clinic: Clinic;
  visit: AppointmentDetail;
  risk_profile: RiskProfile;
  medications: SummaryMedication[];
  screening: ScreeningSummary;
  smartwatch_data_available: false;
  clinically_validated: false;
}

export interface Health {
  status: string;
  database: string;
}

// Screening: every rule and mapping is an unreviewed draft. The backend sends no
// due dates, and the UI must not derive any.

export type RuleStatus = "candidate" | "needs_information" | "not_applicable" | "not_triggered";
export type RecordSource = "patient_reported" | "lab_report" | "clinician_entered" | "device";
export type MissingReason = "unknown" | "not_collected" | "recorded_pending_review";

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

/** A clinic-entered result: the server sets source to clinician_entered and the patient from the link. */
export type ClinicScreeningRecordCreate = Omit<ScreeningRecordCreate, "source">;

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
