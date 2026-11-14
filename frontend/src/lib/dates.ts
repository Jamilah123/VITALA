// Dates travel as YYYY-MM-DD text and stay in local time. new Date("1995-05-15")
// and toISOString() are UTC, which shifts the day in many time zones.

// A bare "ar-SA" locale would format with the Islamic calendar and Arabic-Indic digits.
const LOCALE = "ar-u-ca-gregory-nu-latn";

export function toIso(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${String(date.getFullYear()).padStart(4, "0")}-${month}-${day}`;
}

export function todayIso(now = new Date()): string {
  return toIso(now);
}

function parseIso(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function isValidIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  return toIso(parseIso(value)) === value;
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long", year: "numeric" }).format(parseIso(iso));
}

export function formatMonthYear(iso: string): string {
  return new Intl.DateTimeFormat(LOCALE, { month: "long", year: "numeric" }).format(parseIso(iso));
}

export function formatMonth(iso: string): string {
  return new Intl.DateTimeFormat(LOCALE, { month: "long" }).format(parseIso(iso));
}

export function ageFrom(birthIso: string, now = new Date()): number {
  const birth = parseIso(birthIso);
  let age = now.getFullYear() - birth.getFullYear();
  const beforeBirthday =
    now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate());
  if (beforeBirthday) age -= 1;
  return age;
}
