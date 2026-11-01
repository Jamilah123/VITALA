import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ApiError, errorMessage } from "../api/errors";
import type { ConditionStatus, Patient, Sex } from "../api/types";
import { DemoNotice, ErrorState, FormError, Loading, SourceBadge, SyntheticDataNotice } from "../components/feedback";
import { CheckRow, Chip, clearErrorOnEdit, DateField, Field } from "../components/forms";
import { Logo } from "../components/Icon";
import { IconTile, Progress, Screen } from "../components/layout";
import { MedicationManager } from "../components/MedicationManager";
import { WATCH_OPTIONS } from "../demo/data";
import { useDemo } from "../demo/store";
import { ageFrom } from "../lib/dates";
import { computeBmi, conditionFields } from "../lib/profile";
import { readBrowserProfile, saveBrowserProfile, useSession } from "../lib/session";
import { useAsync } from "../lib/useAsync";
import { parseNumber, validateBasics, type FieldErrors } from "../lib/validation";

export function Welcome() {
  return (
    <Screen title="البداية" nav={false}>
      <div className="welcome">
        <img src="/logo.svg" className="welcome__logo" alt="" />
        <p className="welcome__word" dir="ltr">
          vitala
        </p>
        <hr />
        <h2>
          ابدئي رحلتك
          <br />
          الصحية الوقائية
        </h2>
        <p className="muted">Vitala تعرّفك على الفحوصات المناسبة لك، ومتى موعدها، ومن أين جاءت التوصية.</p>
        <SyntheticDataNotice />
        <Link to="/onboarding/basic" className="btn btn--primary btn--block">
          ابدئي الآن
        </Link>
        <Link to="/open-profile" className="btn btn--ghost btn--block">
          تسجيل الدخول
        </Link>
      </div>
    </Screen>
  );
}

/** There are no accounts yet, so this opens a synthetic profile by its number. */
export function OpenProfile() {
  const { setPatientId } = useSession();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const id = parseNumber(value);
    if (id === null || !Number.isInteger(id) || id < 1) {
      setError("أدخلي رقم ملف صحيحاً.");
      return;
    }
    setError(null);
    setOpening(true);
    try {
      await api.getPatient(id);
      setPatientId(id);
      navigate("/home");
    } catch (failure) {
      setError(failure instanceof ApiError && failure.kind === "not_found" ? "لا يوجد ملف بهذا الرقم." : errorMessage(failure));
      setOpening(false);
    }
  };

  return (
    <Screen title="تسجيل الدخول" back="/welcome" nav={false}>
      <p className="note">
        تسجيل الدخول غير متاح بعد: لا توجد حسابات أو كلمات مرور في هذه المرحلة. يمكنك فتح ملف اصطناعي موجود برقمه.
      </p>
      <form onSubmit={submit} noValidate className="stack">
        <Field
          label="رقم الملف"
          value={value}
          onChange={(next) => {
            setValue(next);
            setError(null);
          }}
          error={error ?? undefined}
          inputMode="numeric"
          autoFocus
        />
        <button type="submit" className="btn btn--primary btn--block" disabled={opening}>
          {opening ? "جارٍ الفتح…" : "فتح الملف"}
        </button>
      </form>
      <Link to="/onboarding/basic" className="btn btn--ghost btn--block">
        إنشاء ملف جديد
      </Link>
    </Screen>
  );
}

function usePatient() {
  const { patientId } = useSession();
  return useAsync<Patient | null>(
    (signal) => (patientId === null ? Promise.resolve(null) : api.getPatient(patientId, signal)),
    [patientId],
  );
}

function StaleProfileError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { forgetPatient } = useSession();
  return (
    <ErrorState
      error={error}
      onRetry={onRetry}
      action={
        error instanceof ApiError && error.kind === "not_found" ? (
          <button type="button" className="btn btn--outline btn--small" onClick={forgetPatient}>
            البدء بملف جديد
          </button>
        ) : undefined
      }
    />
  );
}

export function BasicInfo() {
  const state = usePatient();
  return (
    <Screen title="المعلومات الأساسية" back="/welcome" nav={false}>
      <Progress step={1} />
      <p className="step-count">الخطوة 1 من 4</p>
      {state.loading && !state.data && <Loading />}
      {state.error ? <StaleProfileError error={state.error} onRetry={state.reload} /> : null}
      {!state.loading && !state.error && <BasicInfoForm patient={state.data ?? null} />}
    </Screen>
  );
}

function BasicInfoForm({ patient }: { patient: Patient | null }) {
  const { setPatientId } = useSession();
  const navigate = useNavigate();
  const stored = readBrowserProfile(patient?.id ?? null);
  const [dateOfBirth, setDateOfBirth] = useState(patient?.date_of_birth ?? "");
  const [sex, setSex] = useState<Sex>(patient?.sex ?? "unknown");
  const [height, setHeight] = useState(stored.height);
  const [weight, setWeight] = useState(stored.weight);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const heightValue = parseNumber(height);
  const weightValue = parseNumber(weight);
  const liveErrors = validateBasics({ dateOfBirth, height, weight });
  const bmi =
    heightValue && weightValue && !liveErrors.height && !liveErrors.weight
      ? computeBmi(heightValue, weightValue, dateOfBirth && !liveErrors.date_of_birth ? ageFrom(dateOfBirth) : null)
      : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setErrors(liveErrors);
    setFormError(null);
    if (Object.keys(liveErrors).length > 0) return;

    const fields = { date_of_birth: dateOfBirth || null, sex };
    setSaving(true);
    try {
      const saved = patient ? await api.updatePatient(patient.id, fields) : await api.createPatient(fields);
      setPatientId(saved.id);
      saveBrowserProfile(saved.id, { height: height.trim(), weight: weight.trim() });
      navigate("/onboarding/history");
    } catch (error) {
      if (error instanceof ApiError) setErrors(error.fieldErrors);
      setFormError(errorMessage(error));
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} onChange={clearErrorOnEdit(setErrors)} noValidate className="stack">
      <div>
        <h2 className="screen-heading">المعلومات الأساسية</h2>
        <p className="muted">نستخدمها لتحديد الفحوصات المناسبة لعمرك وجنسك.</p>
      </div>
      <SyntheticDataNotice />
      <DateField name="date_of_birth" label="تاريخ الميلاد" value={dateOfBirth} onChange={setDateOfBirth} error={errors.date_of_birth} />
      <div className="chips" role="group" aria-label="الجنس">
        {(["male", "female"] as const).map((option) => (
          <Chip key={option} selected={sex === option} onClick={() => setSex(sex === option ? "unknown" : option)}>
            {option === "female" ? "أنثى" : "ذكر"}
          </Chip>
        ))}
      </div>
      <Field name="height" label="الطول" suffix="سم" value={height} onChange={setHeight} error={errors.height} inputMode="decimal" />
      <Field name="weight" label="الوزن" suffix="كجم" value={weight} onChange={setWeight} error={errors.weight} inputMode="decimal" />
      <p className="field__hint">
        التاريخ والجنس يُحفظان في الخادم. الطول والوزن يبقيان في هذا المتصفح فقط، لأن الخادم لا يدعمهما بعد.
      </p>
      {bmi && <BmiCard value={bmi.value} category={bmi.category} />}
      <FormError message={formError} />
      <div className="btn-row">
        <Link to="/welcome" className="btn btn--outline">
          رجوع
        </Link>
        <button type="submit" className="btn btn--primary btn--grow" disabled={saving}>
          {saving ? "جارٍ الحفظ…" : "التالي"}
        </button>
      </div>
    </form>
  );
}

const BMI_SCALE_MIN = 15;
const BMI_SCALE_MAX = 40;

export function BmiCard({ value, category }: { value: number; category: string | null }) {
  const position = ((Math.min(BMI_SCALE_MAX, Math.max(BMI_SCALE_MIN, value)) - BMI_SCALE_MIN) / (BMI_SCALE_MAX - BMI_SCALE_MIN)) * 100;
  return (
    <section className="card card--soft bmi" aria-label="مؤشر كتلة الجسم">
      <div className="bmi__head">
        <strong>مؤشر كتلة الجسم</strong>
        <span className="bmi__value">{value}</span>
      </div>
      <div className="bmi__track" dir="ltr">
        <span className="bmi__marker" style={{ left: `${position}%` }} />
      </div>
      <p className="muted small">
        {category ?? "تصنيف البالغين لا ينطبق هنا."} {category && "· تصنيف عام للبالغين، وليس تشخيصاً."}
      </p>
    </section>
  );
}

type ConditionChip = "diabetes" | "hypertension" | "dyslipidemia" | "none";

const FAMILY_OPTIONS = ["سكري", "سرطان الثدي", "القولون", "أمراض القلب"];

export function HealthHistory() {
  const { patientId } = useSession();
  const state = usePatient();
  if (patientId === null) return <Navigate to="/onboarding/basic" replace />;

  return (
    <Screen title="التاريخ الصحي" back="/onboarding/basic" nav={false}>
      <Progress step={2} />
      <p className="step-count">الخطوة 2 من 4</p>
      {state.loading && !state.data && <Loading />}
      {state.error ? <StaleProfileError error={state.error} onRetry={state.reload} /> : null}
      {state.data && <HealthHistoryForm patient={state.data} />}
    </Screen>
  );
}

function initialConditions(patient: Patient, dyslipidemia: boolean): Set<ConditionChip> {
  const chips = new Set<ConditionChip>();
  if (patient.diabetes_status === "diagnosed") chips.add("diabetes");
  if (patient.hypertension_status === "diagnosed") chips.add("hypertension");
  if (dyslipidemia) chips.add("dyslipidemia");
  if (patient.diabetes_status === "not_diagnosed" && patient.hypertension_status === "not_diagnosed") chips.add("none");
  return chips;
}

function HealthHistoryForm({ patient }: { patient: Patient }) {
  const navigate = useNavigate();
  const stored = readBrowserProfile(patient.id);
  const [conditions, setConditions] = useState(() => initialConditions(patient, stored.dyslipidemia));
  const [family, setFamily] = useState<string[]>(stored.familyHistory);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const toggleCondition = (chip: ConditionChip) => {
    setConditions((previous) => {
      const next = new Set(previous);
      if (next.has(chip)) {
        next.delete(chip);
      } else if (chip === "none") {
        return new Set<ConditionChip>(["none"]);
      } else {
        next.add(chip);
        next.delete("none");
      }
      return next;
    });
  };

  const statusOf = (chip: "diabetes" | "hypertension"): ConditionStatus => {
    if (conditions.has(chip)) return "diagnosed";
    // Only an explicit "none" says a condition is absent. Otherwise it is unknown.
    return conditions.has("none") ? "not_diagnosed" : "unknown";
  };

  const next = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updatePatient(patient.id, conditionFields(statusOf("diabetes"), statusOf("hypertension")));
      saveBrowserProfile(patient.id, { dyslipidemia: conditions.has("dyslipidemia"), familyHistory: family });
      navigate("/onboarding/watch");
    } catch (failure) {
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  const labels: [ConditionChip, string][] = [
    ["diabetes", "السكري"],
    ["hypertension", "ضغط الدم"],
    ["dyslipidemia", "ارتفاع الدهون"],
    ["none", "لا شيء"],
  ];

  return (
    <div className="stack">
      <div>
        <h2 className="screen-heading">التاريخ الصحي</h2>
        <p className="muted">اختاري ما ينطبق عليك. يمكنك التعديل لاحقاً.</p>
      </div>

      <section className="stack-tight">
        <h3 className="group-title">حالات مشخّصة</h3>
        <div className="chips" role="group" aria-label="حالات مشخّصة">
          {labels.map(([chip, label]) => (
            <Chip key={chip} selected={conditions.has(chip)} onClick={() => toggleCondition(chip)}>
              {label}
            </Chip>
          ))}
        </div>
        <p className="field__hint">ما لا تختارينه يُسجَّل «غير معروف» ولا يعني عدم الإصابة. «لا شيء» يعني أنه لا يوجد تشخيص.</p>
      </section>

      <section className="stack-tight">
        <h3 className="group-title">تاريخ العائلة</h3>
        <div className="chips" role="group" aria-label="تاريخ العائلة">
          {FAMILY_OPTIONS.map((option) => (
            <Chip
              key={option}
              selected={family.includes(option)}
              onClick={() =>
                setFamily((previous) =>
                  previous.includes(option) ? previous.filter((item) => item !== option) : [...previous, option],
                )
              }
            >
              {option}
            </Chip>
          ))}
        </div>
        <p className="field__hint">ارتفاع الدهون وتاريخ العائلة يبقيان في هذا المتصفح فقط، لأن الخادم لا يدعمهما بعد.</p>
      </section>

      <section className="stack-tight">
        <div className="section-head section-head--flush">
          <h3 className="group-title">الأدوية الحالية</h3>
          <SourceBadge kind="live" />
        </div>
        <MedicationManager patientId={patient.id} birthDate={patient.date_of_birth} />
      </section>

      <FormError message={error} />
      <div className="btn-row">
        <Link to="/onboarding/basic" className="btn btn--outline">
          رجوع
        </Link>
        <button type="button" className="btn btn--primary btn--grow" onClick={next} disabled={saving}>
          {saving ? "جارٍ الحفظ…" : "التالي"}
        </button>
      </div>
    </div>
  );
}

export function WatchLink() {
  const demo = useDemo();
  const navigate = useNavigate();
  const { patientId } = useSession();
  if (patientId === null) return <Navigate to="/onboarding/basic" replace />;

  return (
    <Screen title="ربط الساعة" back="/onboarding/history" nav={false}>
      <Progress step={3} />
      <p className="step-count">الخطوة 3 من 4</p>
      <div className="stack">
        <div>
          <h2 className="screen-heading">ربط الساعة الذكية</h2>
          <p className="muted">اختياري. بإذنك فقط، نقرأ بيانات النشاط لتتبّع هدفك.</p>
        </div>
        <DemoNotice>ربط الساعة غير متاح بعد: لن يتصل التطبيق بأي جهاز، وتُحفظ اختياراتك في هذا المتصفح فقط.</DemoNotice>
        <div className="card">
          {WATCH_OPTIONS.map((option) => (
            <CheckRow
              key={option.id}
              checked={demo.watch[option.id]}
              onChange={(checked) => demo.update({ watch: { ...demo.watch, [option.id]: checked } })}
              icon={<IconTile name={option.icon} tone={option.tone} />}
            >
              <strong>{option.title}</strong>
              <span className="muted small">{option.detail}</span>
            </CheckRow>
          ))}
        </div>
        <p className="note">القيم المعروضة من الساعة تقديرية. يمكنك إيقاف المشاركة أو حذف البيانات في أي وقت من «حسابي».</p>
        <button type="button" className="btn btn--primary btn--block" onClick={() => navigate("/onboarding/done")}>
          حفظ الاختيار بدون ربط فعلي
        </button>
        <Link to="/onboarding/done" className="btn btn--ghost btn--block">
          تخطي الآن
        </Link>
      </div>
    </Screen>
  );
}

export function OnboardingDone() {
  return (
    <Screen title="اكتمل" nav={false}>
      <Progress step={4} />
      <div className="done">
        <Logo size={96} />
        <h2 className="screen-heading">حفظنا ملفك</h2>
        <p className="muted">
          بياناتك الأساسية وأدويتك محفوظة في الخادم. محرّك التوصيات غير متاح بعد، فلم نحسب فحوصات من بياناتك.
        </p>
        <p className="note">يمكنك استعراض خريطة وقائية تجريبية لشخصية افتراضية لترَي كيف ستبدو.</p>
        <Link to="/home" className="btn btn--primary btn--block">
          عرض الخريطة التجريبية
        </Link>
      </div>
    </Screen>
  );
}
