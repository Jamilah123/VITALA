import { errorFromResponse, networkError } from "./errors";
import type {
  Appointment,
  AppointmentCreate,
  AppointmentDetail,
  AppointmentOutcome,
  AppointmentUpdate,
  CatalogueMedication,
  Clinic,
  ClinicPatient,
  Doctor,
  Health,
  MedicationUse,
  MedicationUseCreate,
  MedicationUseUpdate,
  Patient,
  PatientInput,
  PreAppointmentSummary,
  RiskProfile,
  RiskProfileInput,
  ScreeningRecord,
  ScreeningRecordCreate,
  ScreeningSummary,
  ScreeningTest,
} from "./types";

const TIMEOUT_MS = 15_000;

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: init.body ? { "Content-Type": "application/json" } : undefined,
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw networkError();
  }

  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => undefined);
  if (!response.ok) throw errorFromResponse(response.status, body);
  if (body === undefined) throw errorFromResponse(502, undefined);
  return body as T;
}

const jsonBody = (method: string, value: unknown): RequestInit => ({ method, body: JSON.stringify(value) });

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", {}, signal),

  createPatient: (input: PatientInput) => request<Patient>("/patients", jsonBody("POST", input)),
  getPatient: (id: number, signal?: AbortSignal) => request<Patient>(`/patients/${id}`, {}, signal),
  updatePatient: (id: number, input: PatientInput) => request<Patient>(`/patients/${id}`, jsonBody("PATCH", input)),

  getRiskProfile: (patientId: number, signal?: AbortSignal) =>
    request<RiskProfile>(`/patients/${patientId}/risk-profile`, {}, signal),
  createRiskProfile: (patientId: number, input: Partial<RiskProfileInput>) =>
    request<RiskProfile>(`/patients/${patientId}/risk-profile`, jsonBody("POST", input)),
  updateRiskProfile: (patientId: number, input: Partial<RiskProfileInput>) =>
    request<RiskProfile>(`/patients/${patientId}/risk-profile`, jsonBody("PATCH", input)),

  listCatalogue: (signal?: AbortSignal) => request<CatalogueMedication[]>("/medications", {}, signal),

  listMedications: (patientId: number, signal?: AbortSignal) =>
    request<MedicationUse[]>(`/patients/${patientId}/medications`, {}, signal),
  addMedication: (patientId: number, input: MedicationUseCreate) =>
    request<MedicationUse>(`/patients/${patientId}/medications`, jsonBody("POST", input)),
  updateMedication: (patientId: number, useId: number, input: MedicationUseUpdate) =>
    request<MedicationUse>(`/patients/${patientId}/medications/${useId}`, jsonBody("PATCH", input)),
  removeMedication: (patientId: number, useId: number) =>
    request<void>(`/patients/${patientId}/medications/${useId}`, { method: "DELETE" }),

  listClinics: (signal?: AbortSignal) => request<Clinic[]>("/clinics", {}, signal),
  listDoctors: (clinicId: number, signal?: AbortSignal) => request<Doctor[]>(`/clinics/${clinicId}/doctors`, {}, signal),
  listClinicPatients: (clinicId: number, signal?: AbortSignal) =>
    request<ClinicPatient[]>(`/clinics/${clinicId}/patients`, {}, signal),
  listAppointments: (clinicId: number, signal?: AbortSignal) =>
    request<Appointment[]>(`/clinics/${clinicId}/appointments`, {}, signal),
  getAppointment: (clinicId: number, appointmentId: number, signal?: AbortSignal) =>
    request<AppointmentDetail>(`/clinics/${clinicId}/appointments/${appointmentId}`, {}, signal),
  getPreAppointmentSummary: (clinicId: number, appointmentId: number, signal?: AbortSignal) =>
    request<PreAppointmentSummary>(`/clinics/${clinicId}/appointments/${appointmentId}/summary`, {}, signal),
  createAppointment: (clinicId: number, input: AppointmentCreate) =>
    request<Appointment>(`/clinics/${clinicId}/appointments`, jsonBody("POST", input)),
  updateAppointment: (clinicId: number, appointmentId: number, input: AppointmentUpdate) =>
    request<Appointment>(`/clinics/${clinicId}/appointments/${appointmentId}`, jsonBody("PATCH", input)),
  changeAppointmentStatus: (clinicId: number, appointmentId: number, status: AppointmentOutcome) =>
    request<Appointment>(`/clinics/${clinicId}/appointments/${appointmentId}/status`, jsonBody("POST", { status })),

  listScreeningTests: (signal?: AbortSignal) => request<ScreeningTest[]>("/screening-tests", {}, signal),
  getScreeningSummary: (patientId: number, signal?: AbortSignal) =>
    request<ScreeningSummary>(`/patients/${patientId}/screening-summary`, {}, signal),

  listScreeningRecords: (patientId: number, signal?: AbortSignal) =>
    request<ScreeningRecord[]>(`/patients/${patientId}/screening-records`, {}, signal),
  addScreeningRecord: (patientId: number, input: ScreeningRecordCreate) =>
    request<ScreeningRecord>(`/patients/${patientId}/screening-records`, jsonBody("POST", input)),
  removeScreeningRecord: (patientId: number, recordId: number) =>
    request<void>(`/patients/${patientId}/screening-records/${recordId}`, { method: "DELETE" }),
};
