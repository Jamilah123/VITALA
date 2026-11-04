import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ApiError, errorMessage } from "../api/errors";
import type { ConditionStatus, DiabetesType, MedicationUse, Patient, RiskProfile, Sex } from "../api/types";
import { ErrorState, FormError, Loading, SourceBadge, SyntheticDataNotice, useToast } from "../components/feedback";
import { CheckRow, clearErrorOnEdit, DateField, Modal, SegmentedField, SelectField } from "../components/forms";
import { IconTile, Pill, Screen, SectionHead } from "../components/layout";
import { MedicationManager } from "../components/MedicationManager";
import { BrowserImportCard, MeasurementFields, RiskFactorFields } from "../components/riskProfile";
import { PatientGate } from "../components/screening";
import { useDemo, type PrivacySetting } from "../demo/store";
import { ageFrom } from "../lib/dates";
import {
  conditionsSummary,
  DIABETES_TYPE_LABELS,
  draftFromPatient,
  draftToUpdate,
  SEX_LABELS,
  STATUS_LABELS,
  type ProfileDraft,
} from "../lib/profile";
import {
  draftFromRisk,
  hasBrowserData,
  riskInputFromDraft,
  saveRiskProfile,
  validateRiskDraft,
  type RiskDraft,
} from "../lib/riskProfile";
import { readBrowserProfile, useSession } from "../lib/session";
import { useAsync } from "../lib/useAsync";
import { validateProfileDates, type FieldErrors } from "../lib/validation";

const PRIVACY_ROWS: { id: PrivacySetting; label: string }[] = [
  { id: "watch", label: "بيانات الساعة الذكية" },
  { id: "reminders", label: "تذكيرات الفحوصات" },
  { id: "sharing", label: "مشاركة الملخص مع الطبيب" },
];

interface AccountData {
  patient: Patient;
  uses: MedicationUse[];
  risk: RiskProfile;
  names: Record<string, string>;
}

function useAccountData(patientId: number | null) {
  return useAsync<AccountData | null>(async (signal) => {
    if (patientId === null) return null;
    const [patient, uses, catalogue, risk] = await Promise.all([
      api.getPatient(patientId, signal),
      api.listMedications(patientId, signal),
      api.listCatalogue(signal),
      api.getRiskProfile(patientId, signal),
    ]);
    return { patient, uses, risk, names: Object.fromEntries(catalogue.map((item) => [item.id, item.name_ar])) };
  }, [patientId]);
}

function profileLine(patient: Patient, risk: RiskProfile): string {
  const parts = [SEX_LABELS[patient.sex]];
  if (patient.date_of_birth) parts.push(`${ageFrom(patient.date_of_birth)} سنة`);
  if (risk.bmi !== null) parts.push(`BMI ${risk.bmi}`);
  return parts.join(" · ");
}

function BackendStatus() {
  const state = useAsync((signal) => api.health(signal), []);
  if (state.loading) return <span className="muted small">جارٍ فحص الاتصال بالخادم…</span>;
  const online = !state.error && state.data?.status === "ok";
  return (
    <span className={`status-dot ${online ? "status-dot--ok" : "status-dot--bad"}`}>
      {online ? "الخادم متصل" : "الخادم غير متصل"}
    </span>
  );
}

export function Account() {
  const { patientId, forgetPatient } = useSession();
  const demo = useDemo();
  const toast = useToast();
  const navigate = useNavigate();
  const state = useAccountData(patientId);
  const [confirmForget, setConfirmForget] = useState(false);
  const notFound = state.error instanceof ApiError && state.error.kind === "not_found";

  return (
    <Screen title="حسابي" wide>
      <div className="grid-2">
        <div className="stack">
          <SectionHead title="ملفي" aside={<BackendStatus />} />
          {patientId === null && (
            <div className="card stack-tight">
              <p>لا يوجد ملف مفتوح في هذا المتصفح.</p>
              <Link to="/onboarding/basic" className="btn btn--primary btn--block">
                إنشاء ملف
              </Link>
              <Link to="/open-profile" className="btn btn--ghost btn--block">
                فتح ملف موجود برقمه
              </Link>
            </div>
          )}
          {state.loading && !state.data && patientId !== null && <Loading label="جارٍ تحميل ملفك…" />}
          {state.error ? (
            <ErrorState
              error={state.error}
              onRetry={state.reload}
              action={
                notFound ? (
                  <button type="button" className="btn btn--outline btn--small" onClick={forgetPatient}>
                    البدء بملف جديد
                  </button>
                ) : undefined
              }
            />
          ) : null}
          {state.data && (
            <>
              <div className="card row-card">
                <IconTile name="user" tone="blue" />
                <div className="row-card__body">
                  <strong>
                    ملف رقم <bdi>{state.data.patient.id}</bdi>
                  </strong>
                  <span className="muted small">{profileLine(state.data.patient, state.data.risk)}</span>
                </div>
                <SourceBadge kind="live" />
              </div>
              <Link to="/account/health" className="card row-card row-card--link">
                <IconTile name="shield" tone="green" />
                <div className="row-card__body">
                  <strong>التاريخ الصحي والأدوية</strong>
                  <span className="muted small">{conditionsSummary(state.data.patient)}</span>
                  <span className="muted small">
                    {state.data.uses.length === 0
                      ? "لا توجد أدوية مسجّلة"
                      : state.data.uses.map((use) => state.data!.names[use.medication_id] ?? use.medication_id).join(" · ")}
                  </span>
                  <Pill tone="blue">تعديل</Pill>
                </div>
              </Link>
            </>
          )}
          {patientId !== null && !notFound && (
            <>
              <button type="button" className="btn btn--ghost btn--block" onClick={() => setConfirmForget(true)}>
                الخروج من هذا الملف في هذا المتصفح
              </button>
            </>
          )}
        </div>

        <div className="stack">
          <SectionHead title="الخصوصية والأذونات" aside={<SourceBadge kind="demo" />} />
          <div className="card">
            {PRIVACY_ROWS.map((row) => (
              <CheckRow
                key={row.id}
                checked={demo.privacy[row.id]}
                onChange={(checked) => demo.update({ privacy: { ...demo.privacy, [row.id]: checked } })}
              >
                <span>{row.label}</span>
              </CheckRow>
            ))}
          </div>
          <p className="note">هذه الإعدادات تجريبية: لا توجد ساعة مربوطة أو تذكيرات أو مشاركة فعلية بعد. نجمع الحد الأدنى من المعلومات اللازمة.</p>
          <Link to="/account/sources" className="card row-card row-card--link">
            <IconTile name="doc" tone="blue" />
            <div className="row-card__body">
              <strong>مصادر القواعد</strong>
              <span className="muted small">مصادر وزارة الصحة التي تستند إليها القواعد المسودة</span>
              <Pill tone="blue">عرض</Pill>
            </div>
            <SourceBadge kind="live" />
          </Link>
          <button
            type="button"
            className="btn btn--ghost btn--block"
            onClick={() => {
              demo.reset();
              toast("أُعيد ضبط البيانات التجريبية. لم يتأثر ملفك في الخادم.");
            }}
          >
            إعادة ضبط البيانات التجريبية
          </button>
        </div>
      </div>

      {confirmForget && (
        <Modal title="الخروج من الملف" onClose={() => setConfirmForget(false)}>
          <p className="stack-text">
            سينسى هذا المتصفح رقم الملف ({patientId}) فقط. يبقى الملف في الخادم لأن الحذف غير متاح بعد، ويمكنك فتحه لاحقاً برقمه.
          </p>
          <div className="btn-row">
            <button type="button" className="btn btn--outline" onClick={() => setConfirmForget(false)}>
              إلغاء
            </button>
            <button
              type="button"
              className="btn btn--primary btn--grow"
              onClick={() => {
                forgetPatient();
                navigate("/welcome");
              }}
            >
              خروج
            </button>
          </div>
        </Modal>
      )}
    </Screen>
  );
}

const STATUS_OPTIONS = (["diagnosed", "not_diagnosed", "unknown"] as ConditionStatus[]).map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

export function HealthProfile() {
  const { patientId } = useSession();
  const state = useAsync(async (signal) => {
    if (patientId === null) return null;
    const [patient, risk] = await Promise.all([api.getPatient(patientId, signal), api.getRiskProfile(patientId, signal)]);
    return { patient, risk };
  }, [patientId]);
  const browser = state.data ? readBrowserProfile(state.data.patient.id) : null;
  const offerImport = browser !== null && hasBrowserData(browser) && !browser.serverImport;

  return (
    <Screen title="التاريخ الصحي والأدوية" back="/account" wide>
      <PatientGate state={state} label="جارٍ تحميل الملف…" />
      {state.data && (
        <>
          {offerImport && <BrowserImportCard server={state.data.risk} onDone={state.reload} />}
          <div className="grid-2">
            {/* Remounted on save, so the form always shows what the server stored. */}
            <ProfileForm key={JSON.stringify(state.data)} patient={state.data.patient} risk={state.data.risk} onSaved={state.reload} />
            <div className="stack">
              <SectionHead title="الأدوية الحالية" aside={<SourceBadge kind="live" />} />
              <MedicationManager patientId={state.data.patient.id} birthDate={state.data.patient.date_of_birth} />
            </div>
          </div>
        </>
      )}
    </Screen>
  );
}

function ProfileForm({ patient, risk, onSaved }: { patient: Patient; risk: RiskProfile; onSaved: () => void }) {
  const toast = useToast();
  const [draft, setDraft] = useState<ProfileDraft>(() => draftFromPatient(patient));
  const [riskDraft, setRiskDraft] = useState<RiskDraft>(() => draftFromRisk(risk));
  const [riskStored, setRiskStored] = useState(risk.stored);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof ProfileDraft>(field: K, value: ProfileDraft[K]) =>
    setDraft((previous) => ({ ...previous, [field]: value }));
  const setRisk = <K extends keyof RiskDraft>(field: K, value: RiskDraft[K]) =>
    setRiskDraft((previous) => ({ ...previous, [field]: value }));

  const setSex = (sex: Sex) => {
    set("sex", sex);
    // Mirrors the backend check: a male record cannot also record pregnancy.
    if (sex === "male" && riskDraft.pregnancy_status === "yes") setRisk("pregnancy_status", "unknown");
  };

  const setStatus = (condition: "diabetes" | "hypertension", status: ConditionStatus) =>
    setDraft((previous) => {
      if (status === "diagnosed") return { ...previous, [`${condition}_status`]: status };
      // Mirrors what will be sent: only a diagnosed condition can have these.
      return {
        ...previous,
        [`${condition}_status`]: status,
        [`${condition}_diagnosis_date`]: "",
        ...(condition === "diabetes" && { diabetes_type: "unknown" as const }),
      };
    });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = { ...validateProfileDates(draft), ...validateRiskDraft(riskDraft) };
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;

    const savePatient = () => api.updatePatient(patient.id, draftToUpdate(draft));
    const saveRisk = async () => {
      await saveRiskProfile(patient.id, riskStored, riskInputFromDraft(riskDraft));
      setRiskStored(true);
    };
    setSaving(true);
    try {
      // Clearing pregnancy must reach the server before a change of sex to male.
      if (draft.sex === "male") {
        await saveRisk();
        await savePatient();
      } else {
        await savePatient();
        await saveRisk();
      }
      toast("حُفظ الملف في الخادم.");
      onSaved();
    } catch (error) {
      if (error instanceof ApiError) setErrors(error.fieldErrors);
      setFormError(errorMessage(error));
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} onChange={clearErrorOnEdit(setErrors)} noValidate className="stack">
      <SectionHead title="ملفي الصحي" aside={<SourceBadge kind="live" />} />
      <SyntheticDataNotice />
      <DateField name="date_of_birth" label="تاريخ الميلاد" value={draft.date_of_birth} onChange={(value) => set("date_of_birth", value)} error={errors.date_of_birth} />
      <SegmentedField<Sex>
        legend="الجنس"
        value={draft.sex}
        onChange={setSex}
        error={errors.sex}
        options={(["female", "male", "unknown"] as Sex[]).map((value) => ({ value, label: SEX_LABELS[value] }))}
      />

      <SegmentedField
        legend="السكري"
        value={draft.diabetes_status}
        onChange={(value) => setStatus("diabetes", value)}
        error={errors.diabetes_status}
        options={STATUS_OPTIONS}
      />
      {draft.diabetes_status === "diagnosed" && (
        <>
          <SelectField
            name="diabetes_type"
            label="نوع السكري"
            value={draft.diabetes_type}
            onChange={(value) => set("diabetes_type", value as DiabetesType)}
            error={errors.diabetes_type}
          >
            {(Object.keys(DIABETES_TYPE_LABELS) as DiabetesType[]).map((value) => (
              <option key={value} value={value}>
                {DIABETES_TYPE_LABELS[value]}
              </option>
            ))}
          </SelectField>
          <DateField
            name="diabetes_diagnosis_date"
            label="تاريخ تشخيص السكري"
            value={draft.diabetes_diagnosis_date}
            onChange={(value) => set("diabetes_diagnosis_date", value)}
            error={errors.diabetes_diagnosis_date}
          />
        </>
      )}

      <SegmentedField
        legend="ضغط الدم"
        value={draft.hypertension_status}
        onChange={(value) => setStatus("hypertension", value)}
        error={errors.hypertension_status}
        options={STATUS_OPTIONS}
      />
      {draft.hypertension_status === "diagnosed" && (
        <DateField
          name="hypertension_diagnosis_date"
          label="تاريخ تشخيص الضغط"
          value={draft.hypertension_diagnosis_date}
          onChange={(value) => set("hypertension_diagnosis_date", value)}
          error={errors.hypertension_diagnosis_date}
        />
      )}
      <p className="field__hint">«غير معروف» لا يعني عدم الإصابة. وحده «غير مشخّص» يعني أنه لا يوجد تشخيص.</p>

      <div className="section-head section-head--flush">
        <h3 className="group-title">القياسات وعوامل الخطر</h3>
        <SourceBadge kind="live" />
      </div>
      <MeasurementFields
        draft={riskDraft}
        set={setRisk}
        errors={errors}
        age={draft.date_of_birth ? ageFrom(draft.date_of_birth) : null}
      />
      <RiskFactorFields draft={riskDraft} set={setRisk} errors={errors} sex={draft.sex} />

      <FormError message={formError} />
      <button type="submit" className="btn btn--primary btn--block" disabled={saving}>
        {saving ? "جارٍ الحفظ…" : "حفظ الملف"}
      </button>
    </form>
  );
}
