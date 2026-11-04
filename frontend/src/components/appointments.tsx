import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import { ApiError, errorMessage } from "../api/errors";
import type { Appointment, AppointmentOutcome, AppointmentUpdate, Clinic, ClinicPatient, Doctor } from "../api/types";
import {
  clinicDayKey,
  clinicTimeValue,
  OUTCOME_ACTIONS,
  validateAppointmentForm,
  zonedTimeToUtc,
  type AppointmentFormInput,
} from "../lib/clinic";
import { formatDate, isValidIsoDate } from "../lib/dates";
import type { FieldErrors } from "../lib/validation";
import { FormError } from "./feedback";
import { clearErrorOnEdit, Field, Modal, SelectField } from "./forms";

const DEMO_WRITE_NOTE = "تعديل تجريبي على بيانات اصطناعية. لا يوجد تسجيل دخول، ولا يحمي هذا النموذج بيانات حقيقية.";

export function AppointmentFormDialog({
  clinic,
  doctors,
  patients,
  editing,
  onSaved,
  onClose,
}: {
  clinic: Clinic;
  doctors: Doctor[];
  patients: ClinicPatient[];
  editing?: Appointment;
  onSaved: (appointment: Appointment) => void;
  onClose: () => void;
}) {
  const now = new Date();
  const today = clinicDayKey(now.toISOString(), clinic.time_zone);
  const original: AppointmentFormInput = {
    clinic_patient_id: editing ? String(editing.clinic_patient_id) : "",
    doctor_id: editing ? String(editing.doctor_id) : "",
    date: editing ? clinicDayKey(editing.scheduled_at, clinic.time_zone) : "",
    time: editing ? clinicTimeValue(editing.scheduled_at, clinic.time_zone) : "",
    visit_reason_ar: editing?.visit_reason_ar ?? "",
  };
  const [input, setInput] = useState(original);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (field: keyof AppointmentFormInput) => (value: string) => setInput((previous) => ({ ...previous, [field]: value }));
  const timeChanged = !editing || input.date !== original.date || input.time !== original.time;
  const patientName = patients.find((item) => String(item.id) === input.clinic_patient_id)?.display_name_ar;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateAppointmentForm(input, clinic.time_zone, new Date(), timeChanged);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;

    const scheduled_at = zonedTimeToUtc(input.date, input.time, clinic.time_zone);
    const visit_reason_ar = input.visit_reason_ar.trim() || null;
    setSaving(true);
    try {
      let saved: Appointment;
      if (editing) {
        // Only what changed, so an unchanged past time is never re-validated.
        const changes: AppointmentUpdate = { visit_reason_ar };
        if (input.doctor_id !== original.doctor_id) changes.doctor_id = Number(input.doctor_id);
        if (timeChanged) changes.scheduled_at = scheduled_at;
        saved = await api.updateAppointment(clinic.id, editing.id, changes);
      } else {
        saved = await api.createAppointment(clinic.id, {
          clinic_patient_id: Number(input.clinic_patient_id),
          doctor_id: Number(input.doctor_id),
          scheduled_at,
          visit_reason_ar,
        });
      }
      onSaved(saved);
    } catch (error) {
      if (error instanceof ApiError) setErrors(error.fieldErrors);
      setFormError(errorMessage(error));
      setSaving(false);
    }
  };

  return (
    <Modal title={editing ? "تعديل الموعد" : "إضافة موعد"} onClose={onClose}>
      <form onSubmit={submit} onChange={clearErrorOnEdit(setErrors)} noValidate className="stack">
        <p className="note note--warn">{DEMO_WRITE_NOTE}</p>
        {editing ? (
          <p className="modal__subject">{patientName ?? `ملف ${editing.clinic_patient_id}`}</p>
        ) : (
          <SelectField
            name="clinic_patient_id"
            label="المريض"
            value={input.clinic_patient_id}
            onChange={set("clinic_patient_id")}
            error={errors.clinic_patient_id}
            hint="المرضى المسجّلون في هذه العيادة فقط."
          >
            <option value="">اختيار المريض</option>
            {patients.map((item) => (
              <option key={item.id} value={item.id}>
                {item.display_name_ar}
                {item.file_number ? ` · ${item.file_number}` : ""}
              </option>
            ))}
          </SelectField>
        )}
        <SelectField name="doctor_id" label="الطبيب" value={input.doctor_id} onChange={set("doctor_id")} error={errors.doctor_id}>
          <option value="">اختيار الطبيب</option>
          {doctors.map((doctor) => (
            <option key={doctor.id} value={doctor.id}>
              {doctor.name_ar}
              {doctor.specialty_ar ? ` · ${doctor.specialty_ar}` : ""}
            </option>
          ))}
        </SelectField>
        <Field
          name="scheduled_at"
          type="date"
          label="التاريخ"
          value={input.date}
          onChange={set("date")}
          error={errors.scheduled_at}
          min={today}
          hint={isValidIsoDate(input.date) ? formatDate(input.date) : undefined}
        />
        <Field
          name="time"
          type="time"
          label="الوقت"
          value={input.time}
          onChange={set("time")}
          error={errors.time}
          step={300}
          hint={`بتوقيت ${clinic.city_ar ?? "العيادة"}. يفصل 30 دقيقة على الأقل بين مواعيد الطبيب الواحد.`}
        />
        <Field
          name="visit_reason_ar"
          label="سبب الزيارة"
          value={input.visit_reason_ar}
          onChange={set("visit_reason_ar")}
          error={errors.visit_reason_ar}
          maxLength={200}
          hint="اختياري."
        />
        <FormError message={formError} />
        <div className="btn-row">
          <button type="button" className="btn btn--outline" onClick={onClose} disabled={saving}>
            إلغاء
          </button>
          <button type="submit" className="btn btn--primary btn--grow" disabled={saving}>
            {saving ? "جارٍ الحفظ…" : "حفظ الموعد"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function OutcomeDialog({
  clinic,
  appointment,
  outcome,
  onDone,
  onClose,
}: {
  clinic: Clinic;
  appointment: Appointment;
  outcome: AppointmentOutcome;
  onDone: (appointment: Appointment) => void;
  onClose: () => void;
}) {
  const action = OUTCOME_ACTIONS[outcome];
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const confirm = async () => {
    setSaving(true);
    setError(null);
    try {
      onDone(await api.changeAppointmentStatus(clinic.id, appointment.id, outcome));
    } catch (failure) {
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  return (
    <Modal title={action.label} onClose={onClose}>
      <p className="stack-text">{action.confirm}</p>
      <FormError message={error} />
      <div className="btn-row">
        <button type="button" className="btn btn--outline" onClick={onClose} disabled={saving}>
          رجوع
        </button>
        <button type="button" className={`btn btn--${action.tone} btn--grow`} onClick={confirm} disabled={saving}>
          {saving ? "جارٍ الحفظ…" : `تأكيد: ${action.label}`}
        </button>
      </div>
    </Modal>
  );
}
