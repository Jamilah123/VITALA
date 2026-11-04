import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ScreeningRecord, ScreeningTestSummary } from "../api/types";
import { SourceBadge, useToast } from "../components/feedback";
import { Pill, Screen, SectionHead } from "../components/layout";
import {
  ClinicalReviewNotice,
  DraftPill,
  MissingList,
  PatientGate,
  RecordForm,
  RecordList,
  RemoveRecordDialog,
  RuleCard,
  SourceList,
  TestStatusPill,
  TestTile,
} from "../components/screening";
import { Icon } from "../components/Icon";
import { conditionsSummary } from "../lib/profile";
import { citedSources, fieldLabel, sortRules, testCount, testGroup, type TestGroup } from "../lib/screening";
import { useSession } from "../lib/session";
import { useAsync } from "../lib/useAsync";

function useScreening(patientId: number | null) {
  return useAsync(async (signal) => {
    if (patientId === null) return null;
    const [patient, summary] = await Promise.all([api.getPatient(patientId, signal), api.getScreeningSummary(patientId, signal)]);
    return { patient, summary };
  }, [patientId]);
}

function TestCard({ test }: { test: ScreeningTestSummary }) {
  const group = testGroup(test);
  const parts = [
    test.candidate_rule_ids.length > 0 && `قواعد قد تنطبق: ${test.candidate_rule_ids.length}`,
    test.needs_information_rule_ids.length > 0 && `تحتاج معلومات: ${test.needs_information_rule_ids.length}`,
  ].filter(Boolean);
  return (
    <Link to={`/checks/${test.test_id}`} className="card row-card row-card--link">
      <TestTile testId={test.test_id} group={group} />
      <div className="row-card__body">
        <strong>{test.name_ar}</strong>
        <span className="muted small">{parts.length > 0 ? parts.join(" · ") : "لا تنطبق قواعدها على بياناتك حالياً."}</span>
        <div className="chips">
          <TestStatusPill group={group} />
          {test.recorded_tests.length > 0 && <Pill tone="green">في سجلك · {test.recorded_tests.length}</Pill>}
        </div>
      </div>
    </Link>
  );
}

const FILTERS = [
  { id: "candidate", label: "قد تنطبق", tone: "blue", matches: (test: ScreeningTestSummary) => testGroup(test) === "candidate" },
  { id: "needs_information", label: "تحتاج معلومات", tone: "amber", matches: (test: ScreeningTestSummary) => testGroup(test) === "needs_information" },
  { id: "recorded", label: "في سجلي", tone: "green", matches: (test: ScreeningTestSummary) => test.recorded_tests.length > 0 },
] as const;

const SECTIONS: { group: TestGroup; title: string; note?: string }[] = [
  { group: "candidate", title: "قد تنطبق عليك · للمراجعة مع الطبيب" },
  { group: "needs_information", title: "تحتاج معلومات لمعرفة إن كانت تنطبق" },
  {
    group: "other",
    title: "لا تنطبق قواعدها حالياً",
    note: "بحسب بياناتك المسجّلة فقط. لا يعني ذلك أن الفحص غير لازم.",
  },
];

export function Checks() {
  const { patientId } = useSession();
  const state = useScreening(patientId);
  const [filter, setFilter] = useState<string | null>(null);
  const [showOther, setShowOther] = useState(false);
  const active = FILTERS.find((item) => item.id === filter);

  return (
    <Screen title="الفحوصات" wide>
      <PatientGate state={state} label="جارٍ تحميل الفحوصات…" />
      {state.data && (
        <>
          <ClinicalReviewNotice notice={state.data.summary.notice_ar} />
          <div className="card card--soft spread">
            <span className="small">
              مبنية على ملفك: {conditionsSummary(state.data.patient)} ·{" "}
              <Link to="/account/health">تحديث الملف والأدوية</Link>
            </span>
            <SourceBadge kind="live" />
          </div>
          <div className="stat-row">
            {(["candidate", "needs_information"] as const).map((group) => (
              <div key={group} className="card stat">
                <span className="muted small">{group === "candidate" ? "قد تنطبق" : "تحتاج معلومات"}</span>
                <strong>{state.data!.summary.tests.filter((test) => testGroup(test) === group).length}</strong>
              </div>
            ))}
            <div className="card stat">
              <span className="muted small">سجلات مكتملة</span>
              <strong>{state.data.summary.tests.reduce((total, test) => total + test.recorded_tests.length, 0)}</strong>
            </div>
          </div>
          <div className="chips" role="group" aria-label="تصفية الفحوصات">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`chip chip--filter chip--${item.tone}${filter === item.id ? " chip--active" : ""}`}
                aria-pressed={filter === item.id}
                onClick={() => setFilter(filter === item.id ? null : item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {SECTIONS.map((section) => {
            const tests = state.data!.summary.tests.filter(
              (test) => testGroup(test) === section.group && (!active || active.matches(test)),
            );
            if (tests.length === 0) return null;
            const hidden = section.group === "other" && !showOther && !active;
            return (
              <section key={section.group} className="stack">
                <SectionHead title={section.title} aside={testCount(tests.length)} />
                {section.note && <p className="muted small">{section.note}</p>}
                {hidden ? (
                  <button type="button" className="btn btn--outline btn--block" onClick={() => setShowOther(true)}>
                    عرض هذه الفحوصات
                  </button>
                ) : (
                  <div className="grid-2">
                    {tests.map((test) => (
                      <TestCard key={test.test_id} test={test} />
                    ))}
                  </div>
                )}
              </section>
            );
          })}
          {active && !state.data.summary.tests.some(active.matches) && <p className="empty">لا توجد فحوصات في هذا التصنيف.</p>}
        </>
      )}
    </Screen>
  );
}

export function CheckDetail() {
  const { testId } = useParams();
  const { patientId } = useSession();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<ScreeningRecord | null>(null);
  const state = useAsync(async (signal) => {
    if (patientId === null) return null;
    const [patient, summary, catalogue] = await Promise.all([
      api.getPatient(patientId, signal),
      api.getScreeningSummary(patientId, signal),
      api.listCatalogue(signal),
    ]);
    return { patient, summary, names: Object.fromEntries(catalogue.map((item) => [item.id, item.name_ar])) };
  }, [patientId]);

  const test = state.data?.summary.tests.find((item) => item.test_id === testId);
  const names = Object.fromEntries((state.data?.summary.tests ?? []).map((item) => [item.test_id, item.name_ar]));

  return (
    <Screen title="تفاصيل الفحص" back="/checks" wide>
      <PatientGate state={state} label="جارٍ تحميل الفحص…" />
      {state.data && !test && <p className="empty">لم نجد هذا الفحص.</p>}
      {state.data && test && (
        <>
          <section className="card detail-hero">
            <TestTile testId={test.test_id} group={testGroup(test)} />
            <h2>{test.name_ar}</h2>
            <div className="chips">
              <TestStatusPill group={testGroup(test)} />
              <DraftPill />
            </div>
          </section>
          <ClinicalReviewNotice notice={state.data.summary.notice_ar} reasons={test.review_reasons} />

          <div className="grid-2">
            <div className="stack">
              <SectionHead title="سجلك لهذا الفحص" aside={<SourceBadge kind="live" />} />
              <p className="muted small">فحوصات أُجريت وسُجّلت في ملفك. هي سجل لما حدث، وليست اقتراحات.</p>
              {test.recorded_tests.length === 0 ? (
                <p className="empty">لا توجد سجلات. غياب السجل لا يعني أن الفحص لم يُجرَ.</p>
              ) : (
                <RecordList records={test.recorded_tests} onRemove={setRemoving} />
              )}
              {test.history_inputs.some((item) => item.record_count > 0 && !item.applied) && (
                <p className="note">لم يُستخدم سجلك في تقييم القواعد بعد: ربط السجلات بالقواعد بانتظار المراجعة الطبية.</p>
              )}
              <button type="button" className="add-row" onClick={() => setAdding(true)}>
                <Icon name="plus" size={18} /> تسجيل فحص مكتمل
              </button>

              <SectionHead title="معلومات ناقصة" />
              <MissingList items={test.missing_inputs} />
              <Link to="/account/health" className="btn btn--outline btn--block">
                تحديث ملفي الصحي والأدوية
              </Link>

              {(test.possible_overlap_test_ids.length > 0 || test.ambiguous_history_fields.length > 0) && (
                <>
                  <SectionHead title="ملاحظات للمراجعة" />
                  {test.possible_overlap_test_ids.length > 0 && (
                    <p className="small">
                      قد يتداخل مع فحوصات لم تُدمج معه:{" "}
                      {test.possible_overlap_test_ids.map((id, index) => (
                        <span key={id}>
                          {index > 0 && "، "}
                          <Link to={`/checks/${id}`}>{names[id] ?? id}</Link>
                        </span>
                      ))}
                    </p>
                  )}
                  {test.ambiguous_history_fields.length > 0 && (
                    <p className="small">
                      علاقة غير محسومة بين هذا السجل وبعض القواعد:{" "}
                      {test.ambiguous_history_fields.map((item) => fieldLabel(item.field)).join("، ")}
                    </p>
                  )}
                </>
              )}
            </div>

            <div className="stack">
              <SectionHead title="القواعد" aside={`${test.rules.length}`} />
              {sortRules(test.rules).map((rule) => (
                <RuleCard key={rule.rule_id} rule={rule} medicationNames={state.data!.names} />
              ))}
            </div>
          </div>

          {adding && (
            <RecordForm
              patientId={state.data.patient.id}
              testId={test.test_id}
              testName={test.name_ar}
              birthDate={state.data.patient.date_of_birth}
              onClose={() => setAdding(false)}
              onSaved={() => {
                setAdding(false);
                state.reload();
                toast("حُفظ السجل في الخادم.");
              }}
            />
          )}
          {removing && (
            <RemoveRecordDialog
              patientId={state.data.patient.id}
              record={removing}
              onClose={() => setRemoving(null)}
              onRemoved={() => {
                setRemoving(null);
                state.reload();
                toast("حُذف السجل من الخادم.");
              }}
            />
          )}
        </>
      )}
    </Screen>
  );
}

export function ResultsLog() {
  const { patientId } = useSession();
  const state = useAsync(async (signal) => {
    if (patientId === null) return null;
    const [records, tests] = await Promise.all([api.listScreeningRecords(patientId, signal), api.listScreeningTests(signal)]);
    return { records, tests };
  }, [patientId]);

  const groups = state.data
    ? [...new Set(state.data.records.map((record) => record.test_id))].map((testId) => ({
        testId,
        name: state.data!.tests.find((test) => test.id === testId)?.name_ar ?? testId,
        records: state.data!.records.filter((record) => record.test_id === testId),
      }))
    : [];

  return (
    <Screen title="سجل الفحوصات" wide>
      <PatientGate state={state} label="جارٍ تحميل السجل…" />
      {state.data && (
        <>
          <div className="spread">
            <p className="muted">الفحوصات المكتملة كما سُجّلت، الأحدث أولاً. السجل لا يحدد مواعيد قادمة.</p>
            <SourceBadge kind="live" />
          </div>
          {groups.length === 0 && (
            <div className="card stack-tight">
              <p className="empty">لا توجد فحوصات مسجّلة بعد.</p>
              <Link to="/checks" className="btn btn--outline btn--block">
                تسجيل فحص من صفحة الفحوصات
              </Link>
            </div>
          )}
          <div className="grid-2">
            {groups.map((group) => (
              <section key={group.testId} className="card stack-tight">
                <div className="spread">
                  <h2 className="group-title">{group.name}</h2>
                  <Link to={`/checks/${group.testId}`} className="small">
                    التفاصيل
                  </Link>
                </div>
                <RecordList records={group.records} />
              </section>
            ))}
          </div>
        </>
      )}
    </Screen>
  );
}

export function Sources() {
  const { patientId } = useSession();
  const state = useScreening(patientId);

  return (
    <Screen title="مصادر القواعد" back="/account">
      <PatientGate state={state} label="جارٍ تحميل المصادر…" />
      {state.data && (
        <div className="stack">
          <ClinicalReviewNotice notice="هذه المصادر التي تستند إليها قواعد الفحص المسودة. ذكر المصدر لا يعني أن طبيباً راجع القاعدة." />
          {citedSources(state.data.summary.tests).map((source) => (
            <div key={source.source_id} className="card stack-tight">
              <SourceList sources={[source]} />
              <p className="muted small">
                القواعد التي تستشهد به:{" "}
                <bdi dir="ltr" className="code">
                  {source.rule_ids.join(", ")}
                </bdi>
              </p>
            </div>
          ))}
        </div>
      )}
    </Screen>
  );
}
