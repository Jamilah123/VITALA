// The synthetic demo clinic. Appointment times are administrative bookings, never
// dates derived from screening rules.

import type { Appointment, AppointmentOutcome, AppointmentStatus, BookingSource } from "../api/types";
import type { IconName } from "../components/Icon";
import { isValidIsoDate } from "./dates";
import type { FieldErrors } from "./validation";

export interface NavTab {
  to: string;
  label: string;
  icon: IconName;
}

export const CLINIC_TABS: NavTab[] = [
  { to: "/clinic", label: "نظرة عامة", icon: "home" },
  { to: "/clinic/appointments", label: "المواعيد", icon: "list" },
  { to: "/clinic/patients", label: "المرضى", icon: "user" },
  { to: "/clinic/doctors", label: "الأطباء", icon: "shield" },
];

export const APPOINTMENT_STATUS: Record<AppointmentStatus, { label: string; tone: string }> = {
  scheduled: { label: "مجدول", tone: "blue" },
  completed: { label: "مكتمل", tone: "green" },
  cancelled: { label: "ملغى", tone: "neutral" },
  no_show: { label: "لم يحضر", tone: "amber" },
};

export const BOOKING_SOURCE: Record<BookingSource, string> = {
  vitala: "عبر Vitala · محاكاة",
  clinic: "عبر العيادة · محاكاة",
  unknown: "مصدر الحجز غير معروف",
};

export const UPCOMING_MODULES = [
  { title: "ملخص ما قبل الموعد", detail: "التاريخ الصحي والأدوية والفحوصات المسجّلة والقواعد المسودة مع مراجعها." },
  { title: "رفع نتائج الفحوصات", detail: "إضافة نتائج المريض إلى سجله من العيادة." },
  { title: "المواعيد المنسوبة إلى Vitala", detail: "متابعة الحجوزات القادمة عبر Vitala، ببيانات محاكاة واضحة." },
  { title: "الفوترة والاشتراك", detail: "إدارة اشتراك العيادة، دون أي دفع فعلي في النسخة التجريبية." },
  { title: "مؤشرات المتابعة الوقائية", detail: "متابعة اكتمال الفحوصات دون مواعيد محسوبة من قواعد غير معتمدة." },
];

const LOCALE = "ar-u-ca-gregory-nu-latn";

export function clinicDayKey(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso));
}

export function formatClinicDay(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, { timeZone, weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));
}

export function formatClinicTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}

export interface AppointmentDay {
  key: string;
  label: string;
  appointments: Appointment[];
}

/** Groups by the clinic's calendar day, keeping the API's time order. */
export function groupByClinicDay(appointments: Appointment[], timeZone: string): AppointmentDay[] {
  const days = new Map<string, AppointmentDay>();
  for (const appointment of [...appointments].sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))) {
    const key = clinicDayKey(appointment.scheduled_at, timeZone);
    const day = days.get(key) ?? { key, label: formatClinicDay(appointment.scheduled_at, timeZone), appointments: [] };
    day.appointments.push(appointment);
    days.set(key, day);
  }
  return [...days.values()];
}

export function upcomingAppointments(appointments: Appointment[], now: Date, limit = 3): Appointment[] {
  return appointments
    .filter((appointment) => appointment.status === "scheduled" && new Date(appointment.scheduled_at) >= now)
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
    .slice(0, limit);
}

// Converting a wall-clock time chosen in the clinic's zone to UTC. Browsers have
// no direct API for this, so the zone's offset at that instant is read from Intl.
function zoneOffsetMs(instant: number, timeZone: string): number {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
      .formatToParts(new Date(instant))
      .map((part) => [part.type, part.value]),
  );
  return Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute, +parts.second) - instant;
}

/** "2026-11-09" + "09:00" in the clinic's zone → "2026-11-09T06:00:00Z". */
export function zonedTimeToUtc(date: string, time: string, timeZone: string): string {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const wall = Date.UTC(year, month - 1, day, hour, minute);
  // A second pass settles times next to a daylight-saving change.
  const instant = wall - zoneOffsetMs(wall - zoneOffsetMs(wall, timeZone), timeZone);
  return new Date(instant).toISOString().replace(".000Z", "Z");
}

export function clinicTimeValue(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}

export const OUTCOME_ACTIONS: Record<AppointmentOutcome, { label: string; confirm: string; tone: "danger" | "primary" }> = {
  cancelled: { label: "إلغاء الموعد", confirm: "سيُلغى الموعد ويبقى في السجل بحالة «ملغى». لا يمكن التراجع عن ذلك.", tone: "danger" },
  completed: { label: "تسجيل الموعد مكتملاً", confirm: "سيُسجَّل الموعد مكتملاً. لا يمكن التراجع عن ذلك.", tone: "primary" },
  no_show: { label: "تسجيل عدم الحضور", confirm: "سيُسجَّل أن المريض لم يحضر. لا يمكن التراجع عن ذلك.", tone: "primary" },
};

export const canEditAppointment = (appointment: Appointment) => appointment.status === "scheduled";

/** Completed and no-show are only possible once the appointment time has passed. */
export function availableOutcomes(appointment: Appointment, now: Date): AppointmentOutcome[] {
  if (appointment.status !== "scheduled") return [];
  return new Date(appointment.scheduled_at) <= now ? ["completed", "no_show", "cancelled"] : ["cancelled"];
}

export interface AppointmentFormInput {
  clinic_patient_id: string;
  doctor_id: string;
  date: string;
  time: string;
  visit_reason_ar: string;
}

const BOOKING_HORIZON_MS = 365 * 24 * 60 * 60 * 1000;

/** Data-entry checks that mirror the server, which stays the final authority. */
export function validateAppointmentForm(input: AppointmentFormInput, timeZone: string, now: Date, checkTime = true): FieldErrors {
  const errors: FieldErrors = {};
  if (!input.clinic_patient_id) errors.clinic_patient_id = "يلزم اختيار المريض.";
  if (!input.doctor_id) errors.doctor_id = "يلزم اختيار الطبيب.";
  if (input.visit_reason_ar.trim().length > 200) errors.visit_reason_ar = "يجب ألا يتجاوز سبب الزيارة 200 حرف.";
  if (!isValidIsoDate(input.date)) errors.scheduled_at = "يلزم إدخال تاريخ صحيح.";
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(input.time)) errors.time = "يلزم إدخال وقت صحيح.";
  if (checkTime && !errors.scheduled_at && !errors.time) {
    const instant = new Date(zonedTimeToUtc(input.date, input.time, timeZone)).getTime();
    if (instant <= now.getTime()) errors.scheduled_at = "يجب أن يكون وقت الموعد في المستقبل.";
    else if (instant > now.getTime() + BOOKING_HORIZON_MS) errors.scheduled_at = "لا يمكن حجز موعد بعد أكثر من سنة.";
  }
  return errors;
}
