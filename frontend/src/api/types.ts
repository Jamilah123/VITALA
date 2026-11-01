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
