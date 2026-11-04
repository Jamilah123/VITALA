import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ApiError, errorMessage } from "../api/errors";
import type { ConditionStatus, Patient, RiskProfile, Sex } from "../api/types";
import { DemoNotice, ErrorState, FormError, Loading, SourceBadge, SyntheticDataNotice } from "../components/feedback";
import { CheckRow, Chip, clearErrorOnEdit, DateField, Field } from "../components/forms";
import { Logo } from "../components/Icon";
import { IconTile, Progress, Screen } from "../components/layout";
import { MedicationManager } from "../components/MedicationManager";
import { MeasurementFields, RiskFactorFields } from "../components/riskProfile";
import { WATCH_OPTIONS } from "../demo/data";
import { useDemo } from "../demo/store";
import { ageFrom } from "../lib/dates";
import { conditionFields } from "../lib/profile";
import {
  draftFromRisk,
  numberOrNull,
  riskInputFromDraft,
  saveRiskProfile,
  UNKNOWN_DRAFT,
  validateRiskDraft,
  type RiskDraft,
} from "../lib/riskProfile";
import { useSession } from "../lib/session";
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
          رحلتك الصحية الوقائية
          <br />
          تبدأ هنا
        </h2>
        <p className="muted">تعرض Vitala الفحوصات التي قد تنطبق ومصادرها، لمراجعتها مع الطبيب.</p>
        <SyntheticDataNotice />
        <Link to="/onboarding/basic" className="btn btn--primary btn--block">
          البدء الآن
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
      setError("يلزم إدخال رقم ملف صحيح.");
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

function useOnboardingData() {
  const { patientId } = useSession();
  return useAsync(async (signal) => {
    if (patientId === null) return null;
    const [patient, risk] = await Promise.all([api.getPatient(patientId, signal), api.getRiskProfile(patientId, signal)]);
    return { patient, risk };
  }, [patientId]);
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
  const state = useOnboardingData();
  return (
    <Screen title="المعلومات الأساسية" back="/welcome" nav={false}>
      <Progress step={1} />
      <p className="step-count">الخطوة 1 من 4</p>
      {state.loading && !state.data && <Loading />}
      {state.error ? <StaleProfileError error={state.error} onRetry={state.reload} /> : null}
      {!state.loading && !state.error && <BasicInfoForm patient={state.data?.patient ?? null} risk={state.data?.risk ?? null} />}
    </Screen>
  );
}

function BasicInfoForm({ patient, risk }: { patient: Patient | null; risk: RiskProfile | null }) {
  const { setPatientId } = useSession();
  const navigate = useNavigate();
  // Remembered after the first save, so a retry never creates a second patient.
  const [savedId, setSavedId] = useState(patient?.id ?? null);
  const [riskStored, setRiskStored] = useState(risk?.stored ?? false);
  const [dateOfBirth, setDateOfBirth] = useState(patient?.date_of_birth ?? "");
  const [sex, setSex] = useState<Sex>(patient?.sex ?? "unknown");
  const [draft, setDraft] = useState<RiskDraft>(risk ? draftFromRisk(risk) : UNKNOWN_DRAFT);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof RiskDraft>(field: K, value: RiskDraft[K]) => setDraft((previous) => ({ ...previous, [field]: value }));
  const dateErrors = validateBasics({ dateOfBirth, height: "", weight: "" });
  const age = dateOfBirth && !dateErrors.date_of_birth ? ageFrom(dateOfBirth) : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = { ...dateErrors, ...validateRiskDraft({ ...draft, activity: "" }) };
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;

    const fields = { date_of_birth: dateOfBirth || null, sex };
    const measurements = { height_cm: numberOrNull(draft.height), weight_kg: numberOrNull(draft.weight) };
    setSaving(true);
    try {
      const saved = savedId ? await api.updatePatient(savedId, fields) : await api.createPatient(fields);
      setSavedId(saved.id);
      setPatientId(saved.id);
      if (riskStored || measurements.height_cm !== null || measurements.weight_kg !== null) {
        await saveRiskProfile(saved.id, riskStored, measurements);
        setRiskStored(true);
      }
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
        <p className="muted">تُستخدم لتحديد الفحوصات التي قد تنطبق حسب العمر والجنس.</p>
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
      <MeasurementFields draft={draft} set={set} errors={errors} age={age} />
      <p className="field__hint">تُحفظ هذه البيانات في الخادم. الطول والوزن اختياريان.</p>
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

type ConditionChip = "diabetes" | "hypertension" | "none";

export function HealthHistory() {
  const { patientId } = useSession();
  const state = useOnboardingData();
  if (patientId === null) return <Navigate to="/onboarding/basic" replace />;

  return (
    <Screen title="التاريخ الصحي" back="/onboarding/basic" nav={false}>
      <Progress step={2} />
      <p className="step-count">الخطوة 2 من 4</p>
      {state.loading && !state.data && <Loading />}
      {state.error ? <StaleProfileError error={state.error} onRetry={state.reload} /> : null}
      {state.data && <HealthHistoryForm patient={state.data.patient} risk={state.data.risk} />}
    </Screen>
  );
}

function initialConditions(patient: Patient): Set<ConditionChip> {
  const chips = new Set<ConditionChip>();
  if (patient.diabetes_status === "diagnosed") chips.add("diabetes");
  if (patient.hypertension_status === "diagnosed") chips.add("hypertension");
  if (patient.diabetes_status === "not_diagnosed" && patient.hypertension_status === "not_diagnosed") chips.add("none");
  return chips;
}

function HealthHistoryForm({ patient, risk }: { patient: Patient; risk: RiskProfile }) {
  const navigate = useNavigate();
  const [conditions, setConditions] = useState(() => initialConditions(patient));
  const [draft, setDraft] = useState<RiskDraft>(() => draftFromRisk(risk));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof RiskDraft>(field: K, value: RiskDraft[K]) => setDraft((previous) => ({ ...previous, [field]: value }));

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
    const found = validateRiskDraft(draft);
    setErrors(found);
    setError(null);
    if (Object.keys(found).length > 0) return;
    setSaving(true);
    try {
      await api.updatePatient(patient.id, conditionFields(statusOf("diabetes"), statusOf("hypertension")));
      await saveRiskProfile(patient.id, risk.stored, riskInputFromDraft(draft));
      navigate("/onboarding/watch");
    } catch (failure) {
      if (failure instanceof ApiError) setErrors(failure.fieldErrors);
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  const labels: [ConditionChip, string][] = [
    ["diabetes", "السكري"],
    ["hypertension", "ضغط الدم"],
    ["none", "لا شيء مما سبق"],
  ];

  return (
    <div className="stack">
      <div>
        <h2 className="screen-heading">التاريخ الصحي</h2>
        <p className="muted">يُرجى اختيار ما ينطبق. يمكن التعديل لاحقاً.</p>
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
        <p className="field__hint">
          ما لا يُختار يُسجَّل «غير معروف» ولا يعني عدم الإصابة. «لا شيء مما سبق» يعني عدم وجود تشخيص بالسكري أو الضغط.
        </p>
      </section>

      <section className="stack-tight">
        <div className="section-head section-head--flush">
          <h3 className="group-title">عوامل الخطر</h3>
          <SourceBadge kind="live" />
        </div>
        <RiskFactorFields draft={draft} set={set} errors={errors} sex={patient.sex} />
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
        <h2 className="screen-heading">حُفظ الملف</h2>
        <p className="muted">البيانات الأساسية والأدوية وعوامل الخطر محفوظة في الخادم.</p>
        <p className="note">تعرض صفحة «الفحوصات» ما قد ينطبق وفق قواعد مسودة لم يراجعها طبيب، دون مواعيد أو توصيات معتمدة.</p>
        <Link to="/home" className="btn btn--primary btn--block">
          الانتقال إلى الرئيسية
        </Link>
      </div>
    </Screen>
  );
}
