// The synthetic demo clinic. Appointment times are administrative bookings, never
// dates derived from screening rules.

import type { Appointment, AppointmentStatus, BookingSource } from "../api/types";
import type { IconName } from "../components/Icon";

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
