/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Appointment, AppointmentStatus, BookingSource } from "../api/types";
import { PATIENT_TABS } from "../components/layout";
import {
  APPOINTMENT_STATUS,
  BOOKING_SOURCE,
  CLINIC_TABS,
  clinicDayKey,
  formatClinicTime,
  groupByClinicDay,
  upcomingAppointments,
} from "./clinic";

const SRC = join(__dirname, "..");
const read = (path: string) => readFileSync(join(SRC, path), "utf-8");

function appointment(id: number, scheduled_at: string, status: AppointmentStatus = "scheduled"): Appointment {
  return { id, clinic_id: 1, doctor_id: 1, clinic_patient_id: 1, scheduled_at, status, booking_source: "clinic", visit_reason_ar: null };
}

describe("clinic labels", () => {
  it("label every appointment status and booking source", () => {
    for (const status of ["scheduled", "completed", "cancelled", "no_show"] as AppointmentStatus[]) {
      expect(APPOINTMENT_STATUS[status].label).toBeTruthy();
    }
    for (const source of ["vitala", "clinic", "unknown"] as BookingSource[]) expect(BOOKING_SOURCE[source]).toBeTruthy();
  });

  it("mark simulated booking attribution as simulated", () => {
    expect(BOOKING_SOURCE.vitala).toContain("محاكاة");
    expect(BOOKING_SOURCE.clinic).toContain("محاكاة");
  });
});

describe("clinic times", () => {
  const RIYADH = "Asia/Riyadh";

  it("shows UTC times in the clinic's time zone", () => {
    expect(formatClinicTime("2026-11-09T06:00:00Z", RIYADH)).toBe("09:00");
  });

  it("groups by the clinic's calendar day, not the UTC day", () => {
    expect(clinicDayKey("2026-11-08T21:30:00Z", RIYADH)).toBe("2026-11-09");
    const days = groupByClinicDay(
      [appointment(2, "2026-11-09T07:00:00Z"), appointment(1, "2026-11-08T21:30:00Z"), appointment(3, "2026-11-10T06:00:00Z")],
      RIYADH,
    );
    expect(days.map((day) => [day.key, day.appointments.map((item) => item.id)])).toEqual([
      ["2026-11-09", [1, 2]],
      ["2026-11-10", [3]],
    ]);
  });

  it("lists only future scheduled appointments, soonest first", () => {
    const now = new Date("2026-11-05T09:00:00Z");
    const list = [
      appointment(1, "2026-11-12T09:00:00Z"),
      appointment(2, "2026-11-01T09:00:00Z"),
      appointment(3, "2026-11-09T09:00:00Z", "cancelled"),
      appointment(4, "2026-11-08T09:00:00Z"),
      appointment(5, "2026-11-20T09:00:00Z"),
      appointment(6, "2026-11-25T09:00:00Z"),
    ];
    expect(upcomingAppointments(list, now).map((item) => item.id)).toEqual([4, 1, 5]);
  });
});

describe("entry and navigation", () => {
  const routes = read("App.tsx");

  it("gives every clinic tab a route", () => {
    for (const tab of CLINIC_TABS) expect(routes).toContain(`path="${tab.to}"`);
  });

  it("keeps patient and clinic navigation apart", () => {
    expect(PATIENT_TABS.some((tab) => tab.to.startsWith("/clinic"))).toBe(false);
    expect(CLINIC_TABS.every((tab) => tab.to.startsWith("/clinic"))).toBe(true);
  });

  it("offers exactly two entry paths: patient and clinic", () => {
    const welcome = read("screens/onboarding.tsx");
    expect(welcome.match(/aria-label="مسار [^"]+"/g)).toEqual(['aria-label="مسار المريض"', 'aria-label="مسار العيادة"']);
    expect(welcome).toContain('to="/clinic"');
    expect(welcome).toContain("لا يمنح صلاحيات");
  });

  it("collects no passwords anywhere, so no screen pretends to be a login", () => {
    const files = (folder: string): string[] =>
      readdirSync(folder).flatMap((name) => {
        const path = join(folder, name);
        return statSync(path).isDirectory() ? files(path) : /\.tsx$/.test(name) ? [path] : [];
      });
    for (const file of files(SRC)) expect(readFileSync(file, "utf-8"), file).not.toMatch(/type="password"|كلمة المرور/);
  });
});

describe("clinic API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads every clinic resource from its clinic-scoped path", async () => {
    const fetchMock = vi.fn(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.listClinics();
    await api.listDoctors(7);
    await api.listClinicPatients(7);
    await api.listAppointments(7);

    const calls = fetchMock.mock.calls as unknown as [string][];
    expect(calls.map(([path]) => path)).toEqual([
      "/api/clinics",
      "/api/clinics/7/doctors",
      "/api/clinics/7/patients",
      "/api/clinics/7/appointments",
    ]);
  });
});
