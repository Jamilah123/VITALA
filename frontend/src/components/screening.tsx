import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ApiError, errorMessage } from "../api/errors";
import type {
  RecordSource,
  RuleStatus,
  ScreeningAction,
  ScreeningRecord,
  SourceReference,
  SummaryMissingInput,
} from "../api/types";
import { formatDate, todayIso } from "../lib/dates";
import {
  exclusionReason,
  fieldLabel,
  MISSING_REASONS,
  RECORD_SOURCES,
  reviewFlag,
  reviewReason,
  reviewStatusLabel,
  RULE_STATUS,
  trackLabel,
  type TestGroup,
} from "../lib/screening";
import { useSession } from "../lib/session";
import type { AsyncState } from "../lib/useAsync";
import { validateScreeningRecord, type FieldErrors, type ScreeningRecordInput } from "../lib/validation";
import { ErrorState, FormError, Loading, SyntheticDataNotice } from "./feedback";
import { clearErrorOnEdit, DateField, Field, Modal, SelectField } from "./forms";
import type { IconName } from "./Icon";
import { IconTile, Pill } from "./layout";

const TEST_ICONS: Record<string, IconName> = {
  hba1c: "drop",
  fasting_glucose: "drop",
  eye_exam: "eye",
  blood_pressure: "pulse",
  bp_followup: "pulse",
  annual_htn_review: "pulse",
  ecg: "heart",
  foot_exam: "walk",
  neuropathy_exam: "walk",
};

const GROUP_TONES: Record<TestGroup, string> = { candidate: "blue", needs_information: "amber", other: "plain" };

export function TestTile({ testId, group }: { testId: string; group: TestGroup }) {
  return <IconTile name={TEST_ICONS[testId] ?? "flask"} tone={GROUP_TONES[group]} />;
}

export function RuleStatusPill({ status }: { status: RuleStatus }) {
  return <Pill tone={RULE_STATUS[status].tone}>{RULE_STATUS[status].label}</Pill>;
}

export function TestStatusPill({ group }: { group: TestGroup }) {
  return group === "other" ? null : <RuleStatusPill status={group} />;
}

export function DraftPill() {
  return <Pill tone="neutral">مسودة لم يراجعها طبيب</Pill>;
}

export function NoPatient() {
  return (
    <div className="card stack-tight">
      <p>لا يوجد ملف مفتوح في هذا المتصفح.</p>
      <Link to="/onboarding/basic" className="btn btn--primary btn--block">
        إنشاء ملف
      </Link>
      <Link to="/open-profile" className="btn btn--ghost btn--block">
        فتح ملف موجود برقمه
      </Link>
    </div>
  );
}

/** Loading, error, and missing-profile states for a screen that reads one patient. */
export function PatientGate({ state, label }: { state: Omit<AsyncState<unknown>, "setData">; label: string }) {
  const { patientId, forgetPatient } = useSession();
  if (patientId === null) return <NoPatient />;
  if (state.loading && !state.data) return <Loading label={label} />;
  if (!state.error) return null;
  const notFound = state.error instanceof ApiError && state.error.kind === "not_found";
  return (
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
  );
}

/** The backend's own warning, followed by every review reason in Arabic. */
export function ClinicalReviewNotice({ notice, reasons = [] }: { notice: string; reasons?: string[] }) {
  return (
    <aside className="note note--warn stack-tight" aria-label="تنبيه المراجعة الطبية">
      <strong>{notice}</strong>
      {reasons.length > 0 && (
        <ul className="facts">
          {reasons.map((code) => (
            <li key={code}>{reviewReason(code)}</li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function Code({ children }: { children: string }) {
  return (
    <bdi dir="ltr" className="code">
      {children}
    </bdi>
  );
}

type SourceItem = Omit<SourceReference, "locator"> & { locator?: string };

export function SourceList({ sources }: { sources: SourceItem[] }) {
  return (
    <ul className="facts">
      {sources.map((source) => (
        <li key={source.source_id + (source.locator ?? "")} className="stack-tight">
          <span>
            <Code>{source.source_id}</Code>{" "}
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.title}
            </a>
          </span>
          <span className="muted small">
            {source.issuer}
            {source.version && ` · ${source.version}`}
            {source.locator && (
              <>
                {" "}
                · الموضع: <bdi>{source.locator}</bdi>
              </>
            )}
          </span>
          <span className="muted small">حدود المصدر: {source.limitation_ar}</span>
        </li>
      ))}
    </ul>
  );
}

export function MissingList({ items }: { items: SummaryMissingInput[] }) {
  if (items.length === 0) return <p className="muted small">لا توجد معلومات ناقصة تطلبها هذه القواعد.</p>;
  return (
    <ul className="facts">
      {items.map((item) => (
        <li key={item.field}>
          <strong>{fieldLabel(item.field)}</strong>
          <span className="muted small">
            {" "}
            · {MISSING_REASONS[item.reason]}
            {item.affects_eligibility && " · يحدد إن كانت القاعدة تنطبق"} · القواعد:{" "}
            {item.rule_ids.map((id) => (
              <Code key={id}>{id}</Code>
            ))}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function RuleCard({ rule, medicationNames }: { rule: ScreeningAction; medicationNames: Record<string, string> }) {
  return (
    <article className="card stack-tight" aria-label={`القاعدة ${rule.rule_id}`}>
      <div className="spread">
        <strong>
          <Code>{rule.rule_id}</Code> · {rule.action_name_ar}
        </strong>
        <RuleStatusPill status={rule.status} />
      </div>
      <p className="muted small">{RULE_STATUS[rule.status].detail}</p>
      <p className="small">
        <strong>لمن تنطبق القاعدة: </strong>
        {rule.eligibility_ar} <span className="muted">({trackLabel(rule.track)})</span>
      </p>
      {rule.reasons.length > 0 && (
        <ul className="facts small">
          {rule.reasons.map((code) => (
            <li key={code}>{exclusionReason(code)}</li>
          ))}
        </ul>
      )}
      {rule.matched_medication_ids.length > 0 && (
        <p className="small">
          <strong>الأدوية المسجّلة المرتبطة: </strong>
          {rule.matched_medication_ids.map((id) => medicationNames[id] ?? id).join("، ")}
        </p>
      )}
      {rule.missing_inputs.length > 0 && (
        <div className="small">
          <strong>معلومات ناقصة:</strong>
          <ul className="facts">
            {rule.missing_inputs.map((item) => (
              <li key={item.field}>
                {fieldLabel(item.field)}{" "}
                <span className="muted">
                  · {MISSING_REASONS[item.reason]}
                  {item.affects_eligibility && " · يحدد إن كانت القاعدة تنطبق"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {rule.notes_ar && (
        <p className="small">
          <strong>ملاحظة المصدر: </strong>
          {rule.notes_ar}
        </p>
      )}
      {rule.review_flags.length > 0 && (
        <div className="small">
          <strong>تنبيهات للمراجعة:</strong>
          <ul className="facts">
            {rule.review_flags.map((code) => (
              <li key={code}>{reviewFlag(code)}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="small">
        <strong>المصادر:</strong>
        <SourceList sources={rule.sources} />
      </div>
      <p className="muted small">
        حالة المراجعة: {reviewStatusLabel(rule.review_status)} · الجدولة التلقائية معطّلة
        {rule.conflict_ids.length > 0 && (
          <>
            {" "}
            · اختلافات المصادر: {rule.conflict_ids.map((id) => <Code key={id}>{id}</Code>)}
          </>
        )}
        {rule.knowledge_ids.length > 0 && (
          <>
            {" "}
            · مراجع الشرح: {rule.knowledge_ids.map((id) => <Code key={id}>{id}</Code>)}
          </>
        )}
      </p>
    </article>
  );
}

export function RecordList({ records, onRemove }: { records: ScreeningRecord[]; onRemove?: (record: ScreeningRecord) => void }) {
  return (
    <ul className="med-list">
      {records.map((record) => (
        <li key={record.id} className="med">
          <div className="med__body">
            <strong>
              {formatDate(record.completed_on)}
              {record.result && (
                <>
                  {" · "}
                  <bdi dir="ltr">
                    {record.result}
                    {record.unit && ` ${record.unit}`}
                  </bdi>
                </>
              )}
            </strong>
            <span className="muted small">
              <bdi>{record.test_name}</bdi> · {RECORD_SOURCES[record.source] ?? record.source}
            </span>
            {record.notes && <span className="muted small">{record.notes}</span>}
          </div>
          {onRemove && (
            <div className="med__actions">
              <button type="button" className="link-btn link-btn--danger" onClick={() => onRemove(record)}>
                حذف
              </button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

const SOURCE_OPTIONS = Object.keys(RECORD_SOURCES) as RecordSource[];

export function RecordForm({
  patientId,
  testId,
  testName,
  birthDate,
  onSaved,
  onClose,
}: {
  patientId: number;
  testId: string;
  testName: string;
  birthDate: string | null;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [input, setInput] = useState<ScreeningRecordInput>({
    test_name: testName,
    completed_on: todayIso(),
    result: "",
    unit: "",
    notes: "",
  });
  const [source, setSource] = useState<RecordSource>("patient_reported");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = (field: keyof ScreeningRecordInput) => (value: string) => setInput((previous) => ({ ...previous, [field]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateScreeningRecord(input, birthDate);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    try {
      await api.addScreeningRecord(patientId, {
        test_id: testId,
        test_name: input.test_name.trim(),
        completed_on: input.completed_on,
        result: input.result.trim() || null,
        unit: input.unit.trim() || null,
        source,
        notes: input.notes.trim() || null,
      });
      onSaved();
    } catch (error) {
      if (error instanceof ApiError) setErrors(error.fieldErrors);
      setFormError(errorMessage(error));
      setSaving(false);
    }
  };

  return (
    <Modal title="تسجيل فحص مكتمل" onClose={onClose}>
      <form onSubmit={submit} onChange={clearErrorOnEdit(setErrors)} noValidate className="stack">
        <SyntheticDataNotice />
        <Field name="test_name" label="اسم الفحص" value={input.test_name} onChange={set("test_name")} error={errors.test_name} maxLength={200} hint="كما يظهر في التقرير." />
        <DateField name="completed_on" label="تاريخ الإجراء" value={input.completed_on} onChange={set("completed_on")} error={errors.completed_on} />
        <Field name="result" label="النتيجة" value={input.result} onChange={set("result")} error={errors.result} maxLength={100} hint="اختياري. تُحفظ كما كُتبت ولا يفسّرها التطبيق." />
        <Field name="unit" label="الوحدة" value={input.unit} onChange={set("unit")} error={errors.unit} maxLength={50} dir="ltr" />
        <SelectField name="source" label="المصدر" value={source} onChange={(value) => setSource(value as RecordSource)} error={errors.source}>
          {SOURCE_OPTIONS.map((value) => (
            <option key={value} value={value}>
              {RECORD_SOURCES[value]}
            </option>
          ))}
        </SelectField>
        <Field name="notes" label="ملاحظات" value={input.notes} onChange={set("notes")} error={errors.notes} maxLength={1000} />
        <FormError message={formError} />
        <div className="btn-row">
          <button type="button" className="btn btn--outline" onClick={onClose} disabled={saving}>
            إلغاء
          </button>
          <button type="submit" className="btn btn--primary btn--grow" disabled={saving}>
            {saving ? "جارٍ الحفظ…" : "حفظ في الخادم"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function RemoveRecordDialog({
  patientId,
  record,
  onRemoved,
  onClose,
}: {
  patientId: number;
  record: ScreeningRecord;
  onRemoved: () => void;
  onClose: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const remove = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.removeScreeningRecord(patientId, record.id);
      onRemoved();
    } catch (failure) {
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  return (
    <Modal title="حذف السجل" onClose={onClose}>
      <p className="stack-text">
        هل تريد حذف سجل «<bdi>{record.test_name}</bdi>» بتاريخ {formatDate(record.completed_on)}؟ لا يمكن التراجع عن الحذف.
      </p>
      <FormError message={error} />
      <div className="btn-row">
        <button type="button" className="btn btn--outline" onClick={onClose} disabled={saving}>
          إلغاء
        </button>
        <button type="button" className="btn btn--danger btn--grow" onClick={remove} disabled={saving}>
          {saving ? "جارٍ الحذف…" : "حذف"}
        </button>
      </div>
    </Modal>
  );
}
