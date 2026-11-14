export type ApiErrorKind = "network" | "validation" | "not_found" | "conflict" | "server";

/** A failed API call, with its message already in Arabic for display. */
export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    message: string,
    readonly fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const MESSAGES = {
  network: "تعذّر الوصول إلى الخادم. يُرجى التأكد من تشغيله ثم إعادة المحاولة.",
  server: "حدث خطأ في الخادم. يُرجى إعادة المحاولة بعد قليل.",
  not_found: "لم يُعثر على هذا السجل في الخادم.",
  conflict: "هذا السجل موجود مسبقاً. يمكن تعديل السجل الحالي بدلاً من إضافته.",
  duplicateRecord: "هذه النتيجة مسجّلة مسبقاً بالقيم نفسها، فلم تُحفظ مرة ثانية.",
  validation: "يُرجى مراجعة الحقول المحددة ثم إعادة المحاولة.",
  unknownField: "قيمة غير صالحة.",
} as const;

// The backend's validation messages (backend/app/validation.py) are in English.
const FIELD_MESSAGES: [RegExp, string][] = [
  [/Date of birth cannot be in the future/, "لا يمكن أن يكون تاريخ الميلاد في المستقبل."],
  [/Date of birth is after the recorded/, "تاريخ الميلاد بعد تواريخ أدوية أو فحوصات مسجّلة. يُرجى تعديلها أولاً."],
  [/A unit requires a result/, "يلزم إدخال النتيجة قبل الوحدة."],
  [/is not a known screening test/, "هذا الفحص غير موجود في القائمة."],
  [/Patient is not registered with this clinic/, "المريض غير مسجّل في هذه العيادة."],
  [/Doctor does not belong to this clinic/, "الطبيب لا يتبع هذه العيادة."],
  [/Appointment time must be in the future/, "يجب أن يكون وقت الموعد في المستقبل."],
  [/more than 365 days ahead/, "لا يمكن حجز موعد بعد أكثر من سنة."],
  [/already has an appointment within 30 minutes/, "لدى الطبيب موعد آخر خلال 30 دقيقة من هذا الوقت."],
  [/Only scheduled appointments can be changed/, "لا يمكن تعديل موعد ملغى أو منتهٍ."],
  [/cannot be marked \w+ before its time/, "لا يمكن تسجيل نتيجة الموعد قبل وقته."],
  [/Cannot change a \w+ appointment/, "لا يمكن تغيير حالة هذا الموعد."],
  [/time zone offset|timezone info/, "صيغة وقت الموعد غير صحيحة."],
  [/Pregnancy cannot be yes/, "لا يمكن تسجيل الحمل لملف جنسه «ذكر»."],
  [/Sex cannot be male while pregnancy/, "لا يمكن اختيار «ذكر» مع تسجيل حمل. يُرجى تعديل حالة الحمل أولاً."],
  [/greater than or equal|less than or equal/, "القيمة خارج النطاق المسموح."],
  [/valid number|valid integer/, "يلزم إدخال رقم صالح."],
  [/diagnosis date requires/, "يتطلب تاريخ التشخيص أن تكون الحالة «مشخّصة»."],
  [/Diagnosis date cannot be in the future/, "لا يمكن أن يكون تاريخ التشخيص في المستقبل."],
  [/Diagnosis date cannot be before/, "لا يمكن أن يسبق تاريخ التشخيص تاريخ الميلاد."],
  [/diabetes type requires/, "يتطلب نوع السكري أن تكون الحالة «مشخّصة»."],
  [/Date cannot be in the future/, "لا يمكن أن يكون التاريخ في المستقبل."],
  [/Date cannot be before the patient/, "لا يمكن أن يسبق التاريخ تاريخ الميلاد."],
  [/Last dose change cannot be before/, "لا يمكن أن يسبق آخر تغيير للجرعة تاريخ البدء."],
  [/not in the medication catalogue/, "هذا الدواء غير موجود في القائمة."],
  [/YYYY-MM-DD|valid date/i, "صيغة التاريخ غير صحيحة."],
  [/at least 1 character|at most 200/, "يلزم إدخال نص من حرف واحد إلى 200 حرف."],
];

interface ValidationItem {
  loc?: unknown[];
  msg?: string;
}

export function translateFieldMessage(message: string | undefined): string {
  const match = FIELD_MESSAGES.find(([pattern]) => message && pattern.test(message));
  return match ? match[1] : MESSAGES.unknownField;
}

/** Turn a FastAPI 422 "detail" list into { field: Arabic message }. */
export function parseFieldErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const errors: Record<string, string> = {};
  for (const item of detail as ValidationItem[]) {
    const location = item.loc ?? [];
    const field = String(location[location.length - 1] ?? "form");
    errors[field] = translateFieldMessage(item.msg);
  }
  return errors;
}

/** Map an HTTP failure to an ApiError. `body` is undefined when it was not JSON. */
export function errorFromResponse(status: number, body: { detail?: unknown } | undefined): ApiError {
  if (status === 422) {
    return new ApiError("validation", MESSAGES.validation, parseFieldErrors(body?.detail));
  }
  if (status === 404) return new ApiError("not_found", MESSAGES.not_found);
  if (status === 409) {
    const duplicateRecord = typeof body?.detail === "string" && /identical record already exists/.test(body.detail);
    return new ApiError("conflict", duplicateRecord ? MESSAGES.duplicateRecord : MESSAGES.conflict);
  }
  // The dev proxy answers with a bodyless 5xx when the backend is down.
  if (status >= 500 && body === undefined) return new ApiError("network", MESSAGES.network);
  return new ApiError("server", MESSAGES.server);
}

export function networkError(): ApiError {
  return new ApiError("network", MESSAGES.network);
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : MESSAGES.server;
}
