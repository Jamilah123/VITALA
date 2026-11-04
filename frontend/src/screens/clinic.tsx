import type { DependencyList, ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ApiError } from "../api/errors";
import type { Appointment, AppointmentDetail, Clinic, ClinicPatient, Doctor, PreAppointmentSummary, ScreeningTestSummary } from "../api/types";
import { ErrorState, Loading, SourceBadge } from "../components/feedback";
import { IconTile, Pill, Screen, SectionHead } from "../components/layout";
import {
  ClinicalReviewNotice,
  MissingList,
  RecordList,
  RuleCard,
  TestStatusPill,
  TestTile,
} from "../components/screening";
import {
  APPOINTMENT_STATUS,
  BOOKING_SOURCE,
  CLINIC_TABS,
  formatClinicDay,
  formatClinicTime,
  groupByClinicDay,
  UPCOMING_MODULES,
  upcomingAppointments,
} from "../lib/clinic";
import {
  ageFact,
  allRecords,
  conditionFact,
  dateFact,
  diabetesTypeFact,
  measureFact,
  screeningGroups,
  sexFact,
  smokingFact,
  yesNoFact,
  type Fact,
} from "../lib/clinicSummary";
import { ageFrom, formatDate } from "../lib/dates";
import { conditionsSummary, drugClassLabel, SEX_LABELS } from "../lib/profile";
import { FAMILY_CONDITIONS } from "../lib/riskProfile";
import { reviewReason, sortRules, testCount } from "../lib/screening";
import { useAsync, type AsyncState } from "../lib/useAsync";

const DEMO_TEXT =
  "عيادة تجريبية: الأطباء والمرضى والمواعيد بيانات اصطناعية، ومصدر الحجز محاكاة. لا يوجد تسجيل دخول، واختيار مسار العيادة لا يمنح صلاحيات ولا يحمي البيانات.";

type Loaded<T> = { clinic: Clinic; data: T } | null;

function useClinic<T>(load: (clinic: Clinic, signal: AbortSignal) => Promise<T>, deps: DependencyList = []) {
  return useAsync<Loaded<T>>(async (signal) => {
    const clinic = (await api.listClinics(signal)).find((item) => item.is_demo);
    if (!clinic) return null;
    return { clinic, data: await load(clinic, signal) };
  }, deps);
}

function ClinicScreen<T>({
  title,
  back,
  state,
  children,
}: {
  title: string;
  back?: string;
  state: AsyncState<Loaded<T>>;
  children: (clinic: Clinic, data: T) => ReactNode;
}) {
  return (
    <Screen title={title} back={back} tabs={CLINIC_TABS} demo demoText={DEMO_TEXT} wide>
      {state.loading && !state.data && <Loading label="جارٍ تحميل بيانات العيادة…" />}
      {state.error ? (
        <ErrorState
          error={state.error}
          onRetry={state.reload}
          action={
            state.error instanceof ApiError && state.error.kind === "not_found" ? (
              <Link to="/clinic/appointments" className="btn btn--outline btn--small">
                العودة إلى المواعيد
              </Link>
            ) : undefined
          }
        />
      ) : null}
      {!state.loading && !state.error && state.data === null && (
        <div className="card stack-tight">
          <strong>لم تُهيّأ العيادة التجريبية بعد.</strong>
          <p className="muted small">
            يلزم تشغيل أمر الإعداد من مجلد backend مرة واحدة، ثم إعادة تحميل الصفحة. لا يغيّر الأمر أي ملف موجود.
          </p>
          <bdi dir="ltr" className="code">
            .\.venv\Scripts\python.exe -m app.seed
          </bdi>
        </div>
      )}
      {state.data && children(state.data.clinic, state.data.data)}
    </Screen>
  );
}

interface ClinicLists {
  doctors: Doctor[];
  patients: ClinicPatient[];
  appointments: Appointment[];
}

function useClinicLists() {
  return useClinic<ClinicLists>(async (clinic, signal) => {
    const [doctors, patients, appointments] = await Promise.all([
      api.listDoctors(clinic.id, signal),
      api.listClinicPatients(clinic.id, signal),
      api.listAppointments(clinic.id, signal),
    ]);
    return { doctors, patients, appointments };
  });
}

function AppointmentRow({ appointment, clinic, lists }: { appointment: Appointment; clinic: Clinic; lists: ClinicLists }) {
  const status = APPOINTMENT_STATUS[appointment.status];
  const person = lists.patients.find((item) => item.id === appointment.clinic_patient_id);
  const doctor = lists.doctors.find((item) => item.id === appointment.doctor_id);
  return (
    <li>
      <Link to={`/clinic/appointments/${appointment.id}`} className="med med--link">
        <div className="med__body">
          <strong>
            <bdi dir="ltr">{formatClinicTime(appointment.scheduled_at, clinic.time_zone)}</bdi> ·{" "}
            {person?.display_name_ar ?? `ملف ${appointment.clinic_patient_id}`}
          </strong>
          <span className="muted small">
            {doctor?.name_ar ?? "طبيب غير معروف"}
            {appointment.visit_reason_ar && ` · ${appointment.visit_reason_ar}`}
          </span>
        </div>
        <div className="chips">
          <Pill tone={status.tone}>{status.label}</Pill>
          <Pill tone="neutral">{BOOKING_SOURCE[appointment.booking_source]}</Pill>
        </div>
      </Link>
    </li>
  );
}

export function ClinicHome() {
  const state = useClinicLists();
  return (
    <ClinicScreen title="مساحة العيادة" state={state}>
      {(clinic, lists) => {
        const upcoming = upcomingAppointments(lists.appointments, new Date());
        return (
          <div className="grid-2">
            <div className="stack">
              <section className="card row-card">
                <IconTile name="shield" tone="blue" />
                <div className="row-card__body">
                  <strong>{clinic.name_ar}</strong>
                  <span className="muted small">{clinic.city_ar ?? "المدينة غير محددة"}</span>
                  <Pill tone="amber">بيانات تجريبية</Pill>
                </div>
              </section>
              <SectionHead title="المواعيد القادمة" aside={<Link to="/clinic/appointments">عرض الكل</Link>} />
              {upcoming.length === 0 ? (
                <p className="empty">لا توجد مواعيد قادمة.</p>
              ) : (
                <ul className="med-list">
                  {upcoming.map((appointment) => (
                    <AppointmentRow key={appointment.id} appointment={appointment} clinic={clinic} lists={lists} />
                  ))}
                </ul>
              )}
              <Link to="/welcome" className="btn btn--ghost btn--block">
                العودة إلى صفحة البداية
              </Link>
            </div>
            <div className="stack">
              <SectionHead title="وحدات قادمة" />
              {UPCOMING_MODULES.map((module) => (
                <div key={module.title} className="card row-card" aria-disabled="true">
                  <IconTile name="doc" tone="plain" />
                  <div className="row-card__body">
                    <strong>{module.title}</strong>
                    <span className="muted small">{module.detail}</span>
                    <Pill tone="neutral">قريباً</Pill>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      }}
    </ClinicScreen>
  );
}

export function ClinicAppointments() {
  const state = useClinicLists();
  return (
    <ClinicScreen title="المواعيد" state={state}>
      {(clinic, lists) => {
        const days = groupByClinicDay(lists.appointments, clinic.time_zone);
        return (
          <>
            <p className="muted">مواعيد إدارية مسجّلة في العيادة، بتوقيت {clinic.city_ar ?? "العيادة"}. لا تُحسب أي مواعيد من قواعد الفحص.</p>
            {days.length === 0 && <p className="empty">لا توجد مواعيد مسجّلة.</p>}
            <div className="stack">
              {days.map((day) => (
                <section key={day.key} className="stack-tight">
                  <SectionHead title={day.label} aside={`${day.appointments.length}`} />
                  <ul className="med-list">
                    {day.appointments.map((appointment) => (
                      <AppointmentRow key={appointment.id} appointment={appointment} clinic={clinic} lists={lists} />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </>
        );
      }}
    </ClinicScreen>
  );
}

export function ClinicPatients() {
  const state = useClinicLists();
  return (
    <ClinicScreen title="المرضى" state={state}>
      {(_clinic, lists) => (
        <>
          <p className="muted">تعرض القائمة المرضى المرتبطين بهذه العيادة فقط.</p>
          {lists.patients.length === 0 && <p className="empty">لا يوجد مرضى مرتبطون بالعيادة.</p>}
          <div className="grid-2">
            {lists.patients.map((item) => (
              <div key={item.id} className="card row-card">
                <IconTile name="user" tone="plain" />
                <div className="row-card__body">
                  <strong>{item.display_name_ar}</strong>
                  <span className="muted small">
                    {item.file_number && (
                      <>
                        <bdi dir="ltr">{item.file_number}</bdi> ·{" "}
                      </>
                    )}
                    {SEX_LABELS[item.patient.sex]}
                    {item.patient.date_of_birth ? ` · ${ageFrom(item.patient.date_of_birth)} سنة` : " · العمر غير معروف"}
                  </span>
                  <span className="muted small">{conditionsSummary(item.patient)}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </ClinicScreen>
  );
}

export function ClinicDoctors() {
  const state = useClinicLists();
  return (
    <ClinicScreen title="الأطباء" state={state}>
      {(_clinic, lists) => (
        <>
          {lists.doctors.length === 0 && <p className="empty">لا يوجد أطباء مسجّلون في العيادة.</p>}
          <div className="grid-2">
            {lists.doctors.map((doctor) => (
              <div key={doctor.id} className="card row-card">
                <IconTile name="shield" tone="blue" />
                <div className="row-card__body">
                  <strong>{doctor.name_ar}</strong>
                  <span className="muted small">{doctor.specialty_ar ?? "التخصص غير محدد"}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </ClinicScreen>
  );
}

function useAppointmentId(): number | null {
  const id = Number(useParams().appointmentId);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function NotFoundCard() {
  return (
    <div className="card stack-tight">
      <p className="empty">لم يُعثر على هذا الموعد في العيادة.</p>
      <Link to="/clinic/appointments" className="btn btn--outline btn--block">
        العودة إلى المواعيد
      </Link>
    </div>
  );
}

function VisitCard({ clinic, visit }: { clinic: Clinic; visit: AppointmentDetail }) {
  const { appointment, doctor, patient } = visit;
  const status = APPOINTMENT_STATUS[appointment.status];
  return (
    <section className="card stack-tight" aria-label="تفاصيل الموعد">
      <div className="spread">
        <strong>{patient.display_name_ar}</strong>
        {patient.file_number && (
          <bdi dir="ltr" className="code">
            {patient.file_number}
          </bdi>
        )}
      </div>
      <span className="small">
        {formatClinicDay(appointment.scheduled_at, clinic.time_zone)} ·{" "}
        <bdi dir="ltr">{formatClinicTime(appointment.scheduled_at, clinic.time_zone)}</bdi>
      </span>
      <span className="muted small">
        {doctor.name_ar}
        {doctor.specialty_ar && ` · ${doctor.specialty_ar}`}
        {appointment.visit_reason_ar && ` · ${appointment.visit_reason_ar}`}
      </span>
      <div className="chips">
        <Pill tone={status.tone}>{status.label}</Pill>
        <Pill tone="neutral">{BOOKING_SOURCE[appointment.booking_source]}</Pill>
      </div>
    </section>
  );
}

export function ClinicAppointmentDetail() {
  const appointmentId = useAppointmentId();
  const state = useClinic<AppointmentDetail | null>(
    (clinic, signal) => (appointmentId === null ? Promise.resolve(null) : api.getAppointment(clinic.id, appointmentId, signal)),
    [appointmentId],
  );
  return (
    <ClinicScreen title="تفاصيل الموعد" back="/clinic/appointments" state={state}>
      {(clinic, visit) =>
        visit === null ? (
          <NotFoundCard />
        ) : (
          <div className="stack">
            <VisitCard clinic={clinic} visit={visit} />
            <Link to={`/clinic/appointments/${visit.appointment.id}/summary`} className="btn btn--primary btn--block">
              عرض الملخص الطبي
            </Link>
          </div>
        )
      }
    </ClinicScreen>
  );
}

function FactList({ facts }: { facts: [string, Fact][] }) {
  return (
    <dl className="fact-list">
      {facts.map(([label, fact]) => (
        <div key={label} className={`fact fact--${fact.state}`}>
          <dt>{label}</dt>
          <dd>{fact.text}</dd>
        </div>
      ))}
    </dl>
  );
}

const FACT_LEGEND = "«غير معروف» يعني أن القيمة لم تُسجّل، ولا يعني «لا» أو «غير مشخّص».";

function SummarySection({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="card stack" aria-label={title}>
      <SectionHead title={title} aside={aside} />
      {children}
    </section>
  );
}

function ScreeningTestBlock({ test, medicationNames }: { test: ScreeningTestSummary; medicationNames: Record<string, string> }) {
  const shown = sortRules(test.rules.filter((rule) => rule.status === "candidate" || rule.status === "needs_information"));
  return (
    <article className="card card--soft stack-tight">
      <div className="spread">
        <span className="spread">
          <TestTile testId={test.test_id} group={test.candidate_rule_ids.length ? "candidate" : "needs_information"} />
          <strong>{test.name_ar}</strong>
        </span>
        <TestStatusPill group={test.candidate_rule_ids.length ? "candidate" : "needs_information"} />
      </div>
      <ul className="facts small">
        {shown.map((rule) => (
          <li key={rule.rule_id}>
            <bdi dir="ltr" className="code">
              {rule.rule_id}
            </bdi>{" "}
            {rule.eligibility_ar}
            <span className="muted"> · المصادر: {rule.sources.map((source) => `${source.source_id} (${source.locator})`).join("، ")}</span>
          </li>
        ))}
      </ul>
      {test.missing_inputs.some((item) => item.affects_eligibility) && (
        <div className="small">
          <strong>معلومات تحدد إن كانت القواعد تنطبق:</strong>
          <MissingList items={test.missing_inputs.filter((item) => item.affects_eligibility)} />
        </div>
      )}
      {test.review_reasons.length > 0 && <p className="muted small">للمراجعة: {test.review_reasons.map(reviewReason).join(" ")}</p>}
      <details className="details">
        <summary>كل القواعد والمراجع ({test.rules.length})</summary>
        <div className="stack-tight">
          {sortRules(test.rules).map((rule) => (
            <RuleCard key={rule.rule_id} rule={rule} medicationNames={medicationNames} />
          ))}
        </div>
      </details>
    </article>
  );
}

function SummaryBody({ clinic, summary }: { clinic: Clinic; summary: PreAppointmentSummary }) {
  const patient = summary.visit.patient.patient;
  const risk = summary.risk_profile;
  const records = allRecords(summary);
  const { candidates, undecided, otherCount } = screeningGroups(summary);
  const medicationNames = Object.fromEntries(summary.medications.map((item) => [item.medication_id, item.name_ar ?? item.medication_id]));
  const conditions: [string, Fact][] = [["السكري", conditionFact(patient.diabetes_status)]];
  if (patient.diabetes_status === "diagnosed") {
    conditions.push(["نوع السكري", diabetesTypeFact(patient.diabetes_type)], ["تاريخ تشخيص السكري", dateFact(patient.diabetes_diagnosis_date)]);
  }
  conditions.push(["ضغط الدم", conditionFact(patient.hypertension_status)]);
  if (patient.hypertension_status === "diagnosed") conditions.push(["تاريخ تشخيص الضغط", dateFact(patient.hypertension_diagnosis_date)]);
  conditions.push(["ارتفاع الدهون", yesNoFact(risk.raised_lipids)]);
  const riskFacts: [string, Fact][] = [
    ["التدخين", smokingFact(risk.smoking_status)],
    ["النشاط البدني", measureFact(risk.activity_minutes_per_week, "دقيقة أسبوعياً")],
    ["الطول", measureFact(risk.height_cm, "سم")],
    ["الوزن", measureFact(risk.weight_kg, "كجم")],
    ["مؤشر كتلة الجسم", measureFact(risk.bmi, "")],
  ];
  if (patient.sex !== "male") riskFacts.push(["الحمل حالياً", yesNoFact(risk.pregnancy_status)]);

  return (
    <div className="stack">
      <ClinicalReviewNotice notice="ملخص تجريبي ببيانات اصطناعية. قواعد الفحص مسودة لم يُتحقق منها سريرياً، ولا تحدد مواعيد ولا توصيات مؤكدة." />

      <div className="grid-2">
        <SummarySection title="نظرة عامة على المريض" aside={<SourceBadge kind="live" />}>
          <VisitCard clinic={clinic} visit={summary.visit} />
          <FactList facts={[["الجنس", sexFact(patient.sex)], ["العمر وتاريخ الميلاد", ageFact(patient.date_of_birth)]]} />
        </SummarySection>

        <SummarySection title="التاريخ الطبي وعوامل الخطر" aside={<SourceBadge kind="live" />}>
          <p className="muted small">{FACT_LEGEND}</p>
          <h3 className="group-title">الحالات</h3>
          <FactList facts={conditions} />
          <h3 className="group-title">عوامل الخطر والقياسات</h3>
          {!risk.stored && <p className="note">لم تُسجّل عوامل الخطر لهذا المريض بعد.</p>}
          <FactList facts={riskFacts} />
          <h3 className="group-title">تاريخ العائلة</h3>
          <FactList facts={FAMILY_CONDITIONS.map((condition) => [condition.label, yesNoFact(risk[condition.field])] as [string, Fact])} />
        </SummarySection>
      </div>

      <div className="grid-2">
        <SummarySection title="الأدوية الحالية" aside={<SourceBadge kind="live" />}>
          {summary.medications.length === 0 ? (
            <p className="empty">لا توجد أدوية مسجّلة. قد تكون القائمة ناقصة.</p>
          ) : (
            <ul className="med-list">
              {summary.medications.map((medication) => (
                <li key={medication.id} className="med">
                  <div className="med__body">
                    <strong>
                      {medication.name_ar ?? <bdi dir="ltr">{medication.medication_id}</bdi>} <bdi>{medication.dose_text}</bdi>
                    </strong>
                    <span className="muted small">
                      {medication.generic_name && <bdi dir="ltr">{medication.generic_name}</bdi>}
                      {medication.drug_class && ` · ${drugClassLabel(medication.drug_class)}`}
                      {!medication.name_ar && " · غير موجود في قائمة الأدوية"}
                    </span>
                    <span className="muted small">
                      البدء: {medication.start_date ? formatDate(medication.start_date) : "غير معروف"} · آخر تغيير للجرعة:{" "}
                      {medication.last_dose_change_date ? formatDate(medication.last_dose_change_date) : "غير معروف"}
                    </span>
                    <span className="muted small">مصدر الإدخال: غير مسجّل</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SummarySection>

        <SummarySection title="بيانات الساعة الذكية">
          <p className="empty">لا توجد بيانات متاحة</p>
          <p className="muted small">ربط الساعة الذكية غير متاح بعد في هذه النسخة، ولا تُعرض أي قياسات تقديرية.</p>
        </SummarySection>
      </div>

      <SummarySection title="الفحوصات التي قد تنطبق" aside={<Pill tone="neutral">مسودة · غير معتمدة</Pill>}>
        <ClinicalReviewNotice notice={summary.screening.notice_ar} />
        {candidates.length === 0 && undecided.length === 0 && <p className="empty">لا توجد قواعد مسودة تنطبق أو تحتاج معلومات لهذا المريض.</p>}
        {candidates.length > 0 && (
          <>
            <h3 className="group-title">قد تنطبق · للتقييم السريري ({testCount(candidates.length)})</h3>
            <div className="grid-2">
              {candidates.map((test) => (
                <ScreeningTestBlock key={test.test_id} test={test} medicationNames={medicationNames} />
              ))}
            </div>
          </>
        )}
        {undecided.length > 0 && (
          <details className="details">
            <summary>تحتاج معلومات لمعرفة إن كانت تنطبق ({testCount(undecided.length)})</summary>
            <div className="grid-2">
              {undecided.map((test) => (
                <ScreeningTestBlock key={test.test_id} test={test} medicationNames={medicationNames} />
              ))}
            </div>
          </details>
        )}
        {otherCount > 0 && <p className="muted small">{testCount(otherCount)} لا تنطبق قواعدها حالياً بحسب البيانات المسجّلة، ولا يعني ذلك أنها غير لازمة.</p>}
      </SummarySection>

      <SummarySection title="سجل الفحوصات والنتائج" aside={<SourceBadge kind="live" />}>
        <p className="muted small">نتائج مسجّلة كما أُدخلت، دون تفسير. غياب السجل لا يعني أن الفحص لم يُجرَ.</p>
        {records.length === 0 ? (
          <p className="empty">لا توجد فحوصات مسجّلة.</p>
        ) : (
          <RecordList records={records.map((record) => ({ ...record, test_name: `${record.test_name_ar} · ${record.test_name}` }))} />
        )}
      </SummarySection>
    </div>
  );
}

export function ClinicPatientSummary() {
  const appointmentId = useAppointmentId();
  const state = useClinic<PreAppointmentSummary | null>(
    (clinic, signal) => (appointmentId === null ? Promise.resolve(null) : api.getPreAppointmentSummary(clinic.id, appointmentId, signal)),
    [appointmentId],
  );
  return (
    <ClinicScreen title="الملخص الطبي قبل الموعد" back={appointmentId ? `/clinic/appointments/${appointmentId}` : "/clinic/appointments"} state={state}>
      {(clinic, summary) => (summary === null ? <NotFoundCard /> : <SummaryBody clinic={clinic} summary={summary} />)}
    </ClinicScreen>
  );
}
