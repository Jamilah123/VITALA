import { useState } from "react";
import type { RiskProfile, Sex, SmokingStatus, YesNoUnknown } from "../api/types";
import { errorMessage } from "../api/errors";
import { computeBmi } from "../lib/profile";
import { FAMILY_CONDITIONS, planBrowserImport, saveRiskProfile, SMOKING_LABELS, YES_NO_LABELS, type RiskDraft } from "../lib/riskProfile";
import { readBrowserProfile, saveBrowserProfile } from "../lib/session";
import { parseNumber, type FieldErrors } from "../lib/validation";
import { FormError, SourceBadge } from "./feedback";
import { Field, SegmentedField } from "./forms";

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

const SMOKING_OPTIONS = (Object.keys(SMOKING_LABELS) as SmokingStatus[]).map((value) => ({ value, label: SMOKING_LABELS[value] }));
const YES_NO_OPTIONS = (["yes", "no", "unknown"] as YesNoUnknown[]).map((value) => ({ value, label: YES_NO_LABELS[value] }));

type SetDraft = <K extends keyof RiskDraft>(field: K, value: RiskDraft[K]) => void;

export function MeasurementFields({
  draft,
  set,
  errors,
  age,
}: {
  draft: RiskDraft;
  set: SetDraft;
  errors: FieldErrors;
  age: number | null;
}) {
  const height = parseNumber(draft.height);
  const weight = parseNumber(draft.weight);
  const bmi =
    height && weight && height >= 50 && height <= 250 && weight >= 2 && weight <= 350 ? computeBmi(height, weight, age) : null;
  return (
    <>
      <Field name="height_cm" label="الطول" suffix="سم" value={draft.height} onChange={(value) => set("height", value)} error={errors.height_cm} inputMode="decimal" />
      <Field name="weight_kg" label="الوزن" suffix="كجم" value={draft.weight} onChange={(value) => set("weight", value)} error={errors.weight_kg} inputMode="decimal" />
      {bmi && <BmiCard value={bmi.value} category={bmi.category} />}
    </>
  );
}

export function RiskFactorFields({
  draft,
  set,
  errors,
  sex,
}: {
  draft: RiskDraft;
  set: SetDraft;
  errors: FieldErrors;
  sex: Sex;
}) {
  return (
    <div className="stack">
      <SegmentedField
        legend="التدخين"
        value={draft.smoking_status}
        onChange={(value) => set("smoking_status", value)}
        error={errors.smoking_status}
        options={SMOKING_OPTIONS}
      />
      <Field
        name="activity_minutes_per_week"
        label="النشاط البدني"
        suffix="دقيقة أسبوعياً"
        value={draft.activity}
        onChange={(value) => set("activity", value)}
        error={errors.activity_minutes_per_week}
        inputMode="numeric"
        hint="تقدير ذاتي اختياري. يُترك فارغاً إن لم يكن معروفاً."
      />
      <SegmentedField
        legend="ارتفاع الدهون"
        value={draft.raised_lipids}
        onChange={(value) => set("raised_lipids", value)}
        error={errors.raised_lipids}
        options={YES_NO_OPTIONS}
      />
      {sex !== "male" && (
        <SegmentedField
          legend="الحمل حالياً"
          value={draft.pregnancy_status}
          onChange={(value) => set("pregnancy_status", value)}
          error={errors.pregnancy_status}
          options={YES_NO_OPTIONS}
        />
      )}
      <h3 className="group-title">تاريخ العائلة</h3>
      {FAMILY_CONDITIONS.map((condition) => (
        <SegmentedField
          key={condition.field}
          legend={condition.label}
          value={draft[condition.field]}
          onChange={(value) => set(condition.field, value)}
          error={errors[condition.field]}
          options={YES_NO_OPTIONS}
        />
      ))}
      <p className="field__hint">
        «غير معروف» لا يعني «لا». تُعرض هذه العوامل للطبيب، ولا تغيّر تقييم قواعد الفحص في هذه المرحلة.
      </p>
    </div>
  );
}

/** Offers, once, to copy details typed before the server stored them. Nothing is overwritten. */
export function BrowserImportCard({ server, onDone }: { server: RiskProfile; onDone: () => void }) {
  const browser = readBrowserProfile(server.patient_id);
  const plan = planBrowserImport(browser, server);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const finish = (outcome: "imported" | "dismissed") => {
    saveBrowserProfile(server.patient_id, { serverImport: outcome });
    onDone();
  };

  const importNow = async () => {
    setSaving(true);
    setError(null);
    try {
      if (plan.imported.length > 0) await saveRiskProfile(server.patient_id, server.stored, plan.input);
      finish("imported");
    } catch (failure) {
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  return (
    <section className="card stack-tight" aria-label="نقل بيانات المتصفح">
      <div className="spread">
        <strong>بيانات محفوظة في هذا المتصفح فقط</strong>
        <SourceBadge kind="browser" />
      </div>
      <p className="muted small">أُدخلت هذه البيانات قبل أن يدعمها الخادم. يمكن نقلها إلى الملف مرة واحدة، ولا تُستبدل أي قيمة محفوظة في الخادم.</p>
      {plan.imported.length > 0 && <p className="small">سيُنقل: {plan.imported.join("، ")}</p>}
      {plan.skipped.length > 0 && <p className="small">لن يُنقل: {plan.skipped.join("، ")}</p>}
      <FormError message={error} />
      <div className="btn-row">
        <button type="button" className="btn btn--outline" onClick={() => finish("dismissed")} disabled={saving}>
          عدم النقل
        </button>
        <button type="button" className="btn btn--primary btn--grow" onClick={importNow} disabled={saving || plan.imported.length === 0}>
          {saving ? "جارٍ النقل…" : "نقل إلى الخادم"}
        </button>
      </div>
    </section>
  );
}
