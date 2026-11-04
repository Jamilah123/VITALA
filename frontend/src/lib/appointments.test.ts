import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { parseFieldErrors } from "../api/errors";
import type { Appointment, AppointmentStatus } from "../api/types";
import {
  availableOutcomes,
  canEditAppointment,
  clinicDayKey,
  clinicTimeValue,
  OUTCOME_ACTIONS,
  validateAppointmentForm,
  zonedTimeToUtc,
  type AppointmentFormInput,
} from "./clinic";

const RIYADH = "Asia/Riyadh";
const NOW = new Date("2026-11-05T09:00:00Z");

function appointment(status: AppointmentStatus, scheduled_at: string): Appointment {
  return { id: 1, clinic_id: 1, doctor_id: 1, clinic_patient_id: 1, scheduled_at, status, booking_source: "clinic", visit_reason_ar: null };
}

const valid: AppointmentFormInput = { clinic_patient_id: "2", doctor_id: "1", date: "2026-11-20", time: "09:30", visit_reason_ar: "" };

describe("clinic time conversion", () => {
  it("turns a Riyadh wall-clock time into UTC", () => {
    expect(zonedTimeToUtc("2026-11-09", "09:00", RIYADH)).toBe("2026-11-09T06:00:00Z");
  });

  it("moves to the previous UTC day for early Riyadh times", () => {
    expect(zonedTimeToUtc("2026-11-10", "01:30", RIYADH)).toBe("2026-11-09T22:30:00Z");
  });

  it("follows daylight saving for clinics in other zones", () => {
    expect(zonedTimeToUtc("2026-07-01", "09:00", "Europe/Berlin")).toBe("2026-07-01T07:00:00Z");
    expect(zonedTimeToUtc("2026-01-15", "09:00", "Europe/Berlin")).toBe("2026-01-15T08:00:00Z");
  });

  it("shows the same date and time the user picked", () => {
    for (const [date, time] of [["2026-11-09", "09:00"], ["2026-11-10", "00:15"], ["2026-12-31", "23:55"]]) {
      const utc = zonedTimeToUtc(date, time, RIYADH);
      expect([clinicDayKey(utc, RIYADH), clinicTimeValue(utc, RIYADH)]).toEqual([date, time]);
    }
  });
});

describe("appointment form checks", () => {
  it("accepts a complete future appointment", () => {
    expect(validateAppointmentForm(valid, RIYADH, NOW)).toEqual({});
  });

  it("requires a patient, a doctor, a date, and a time", () => {
    const errors = validateAppointmentForm({ ...valid, clinic_patient_id: "", doctor_id: "", date: "", time: "" }, RIYADH, NOW);
    expect(Object.keys(errors).sort()).toEqual(["clinic_patient_id", "doctor_id", "scheduled_at", "time"]);
  });

  it("rejects past, distant, and impossible times", () => {
    expect(validateAppointmentForm({ ...valid, date: "2026-11-05", time: "11:00" }, RIYADH, NOW).scheduled_at).toContain("المستقبل");
    expect(validateAppointmentForm({ ...valid, date: "2027-11-10" }, RIYADH, NOW).scheduled_at).toContain("سنة");
    expect(validateAppointmentForm({ ...valid, time: "25:00" }, RIYADH, NOW).time).toBeDefined();
    expect(validateAppointmentForm({ ...valid, date: "2026-02-30" }, RIYADH, NOW).scheduled_at).toBeDefined();
  });

  it("does not re-check an unchanged time while editing", () => {
    expect(validateAppointmentForm({ ...valid, date: "2026-10-01" }, RIYADH, NOW, false)).toEqual({});
  });

  it("limits the visit reason", () => {
    expect(validateAppointmentForm({ ...valid, visit_reason_ar: "x".repeat(201) }, RIYADH, NOW).visit_reason_ar).toBeDefined();
  });
});

describe("appointment lifecycle in the interface", () => {
  it("offers only cancellation before the appointment time", () => {
    expect(availableOutcomes(appointment("scheduled", "2026-11-09T06:00:00Z"), NOW)).toEqual(["cancelled"]);
  });

  it("offers completion and no-show once the time has passed", () => {
    expect(availableOutcomes(appointment("scheduled", "2026-11-04T06:00:00Z"), NOW)).toEqual(["completed", "no_show", "cancelled"]);
  });

  it("offers nothing and allows no edits for final statuses", () => {
    for (const status of ["completed", "cancelled", "no_show"] as AppointmentStatus[]) {
      expect(availableOutcomes(appointment(status, "2026-11-04T06:00:00Z"), NOW)).toEqual([]);
      expect(canEditAppointment(appointment(status, "2026-11-09T06:00:00Z"))).toBe(false);
    }
    expect(canEditAppointment(appointment("scheduled", "2026-11-09T06:00:00Z"))).toBe(true);
  });

  it("says cancellation keeps the appointment in the record", () => {
    expect(OUTCOME_ACTIONS.cancelled.confirm).toContain("يبقى في السجل");
  });
});

describe("appointment API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("creates, updates, and changes status on clinic-scoped paths", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const create = { clinic_patient_id: 2, doctor_id: 1, scheduled_at: "2026-11-20T06:30:00Z", visit_reason_ar: null };

    await api.createAppointment(1, create);
    await api.updateAppointment(1, 9, { doctor_id: 3 });
    await api.changeAppointmentStatus(1, 9, "cancelled");

    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([path, init]) => [path, init.method, init.body])).toEqual([
      ["/api/clinics/1/appointments", "POST", JSON.stringify(create)],
      ["/api/clinics/1/appointments/9", "PATCH", JSON.stringify({ doctor_id: 3 })],
      ["/api/clinics/1/appointments/9/status", "POST", JSON.stringify({ status: "cancelled" })],
    ]);
  });

  it("offers no way to delete an appointment", () => {
    expect(Object.keys(api).filter((name) => /delete|remove/i.test(name) && /appointment/i.test(name))).toEqual([]);
  });

  it("translates the server's appointment errors", () => {
    const errors = parseFieldErrors([
      { loc: ["body", "scheduled_at"], msg: "Value error, The doctor already has an appointment within 30 minutes of this time" },
      { loc: ["body", "doctor_id"], msg: "Value error, Doctor does not belong to this clinic" },
      { loc: ["body", "clinic_patient_id"], msg: "Value error, Patient is not registered with this clinic" },
      { loc: ["body", "status"], msg: "Value error, An appointment cannot be marked completed before its time" },
    ]);

    expect(errors.scheduled_at).toBe("لدى الطبيب موعد آخر خلال 30 دقيقة من هذا الوقت.");
    expect(errors.doctor_id).toBe("الطبيب لا يتبع هذه العيادة.");
    expect(errors.clinic_patient_id).toBe("المريض غير مسجّل في هذه العيادة.");
    expect(errors.status).toBe("لا يمكن تسجيل نتيجة الموعد قبل وقته.");
  });
});
