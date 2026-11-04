import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Appointment, Clinic, ClinicPatient, Doctor } from "../api/types";
import { ErrorState, Loading } from "../components/feedback";
import { IconTile, Pill, Screen, SectionHead } from "../components/layout";
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
import { ageFrom } from "../lib/dates";
import { conditionsSummary, SEX_LABELS } from "../lib/profile";
import { useAsync, type AsyncState } from "../lib/useAsync";

const DEMO_TEXT =
  "عيادة تجريبية: الأطباء والمرضى والمواعيد بيانات اصطناعية، ومصدر الحجز محاكاة. لا يوجد تسجيل دخول، واختيار مسار العيادة لا يمنح صلاحيات ولا يحمي البيانات.";

interface ClinicData {
  clinic: Clinic;
  doctors: Doctor[];
  patients: ClinicPatient[];
  appointments: Appointment[];
}

function useDemoClinic() {
  return useAsync<ClinicData | null>(async (signal) => {
    const clinic = (await api.listClinics(signal)).find((item) => item.is_demo);
    if (!clinic) return null;
    const [doctors, patients, appointments] = await Promise.all([
      api.listDoctors(clinic.id, signal),
      api.listClinicPatients(clinic.id, signal),
      api.listAppointments(clinic.id, signal),
    ]);
    return { clinic, doctors, patients, appointments };
  }, []);
}

function ClinicScreen({
  title,
  state,
  children,
}: {
  title: string;
  state: AsyncState<ClinicData | null>;
  children: (data: ClinicData) => ReactNode;
}) {
  return (
    <Screen title={title} tabs={CLINIC_TABS} demo demoText={DEMO_TEXT} wide>
      {state.loading && !state.data && <Loading label="جارٍ تحميل بيانات العيادة…" />}
      {state.error ? <ErrorState error={state.error} onRetry={state.reload} /> : null}
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
      {state.data && children(state.data)}
    </Screen>
  );
}

const lookup = (data: ClinicData) => ({
  doctor: (id: number) => data.doctors.find((doctor) => doctor.id === id),
  patient: (id: number) => data.patients.find((item) => item.id === id),
});

function AppointmentRow({ appointment, data }: { appointment: Appointment; data: ClinicData }) {
  const { doctor, patient } = lookup(data);
  const status = APPOINTMENT_STATUS[appointment.status];
  const person = patient(appointment.clinic_patient_id);
  return (
    <li className="med">
      <div className="med__body">
        <strong>
          <bdi dir="ltr">{formatClinicTime(appointment.scheduled_at, data.clinic.time_zone)}</bdi> ·{" "}
          {person?.display_name_ar ?? `ملف ${appointment.clinic_patient_id}`}
        </strong>
        <span className="muted small">
          {doctor(appointment.doctor_id)?.name_ar ?? "طبيب غير معروف"}
          {appointment.visit_reason_ar && ` · ${appointment.visit_reason_ar}`}
        </span>
      </div>
      <div className="chips">
        <Pill tone={status.tone}>{status.label}</Pill>
        <Pill tone="neutral">{BOOKING_SOURCE[appointment.booking_source]}</Pill>
      </div>
    </li>
  );
}

export function ClinicHome() {
  const state = useDemoClinic();
  return (
    <ClinicScreen title="مساحة العيادة" state={state}>
      {(data) => {
        const upcoming = upcomingAppointments(data.appointments, new Date());
        return (
          <div className="grid-2">
            <div className="stack">
              <section className="card row-card">
                <IconTile name="shield" tone="blue" />
                <div className="row-card__body">
                  <strong>{data.clinic.name_ar}</strong>
                  <span className="muted small">{data.clinic.city_ar ?? "المدينة غير محددة"}</span>
                  <Pill tone="amber">بيانات تجريبية</Pill>
                </div>
              </section>
              <SectionHead title="المواعيد القادمة" aside={<Link to="/clinic/appointments">عرض الكل</Link>} />
              {upcoming.length === 0 ? (
                <p className="empty">لا توجد مواعيد قادمة.</p>
              ) : (
                <ul className="med-list">
                  {upcoming.map((appointment) => (
                    <li key={appointment.id} className="med">
                      <div className="med__body">
                        <strong>{lookup(data).patient(appointment.clinic_patient_id)?.display_name_ar}</strong>
                        <span className="muted small">
                          {formatClinicDay(appointment.scheduled_at, data.clinic.time_zone)} ·{" "}
                          <bdi dir="ltr">{formatClinicTime(appointment.scheduled_at, data.clinic.time_zone)}</bdi>
                        </span>
                      </div>
                    </li>
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
  const state = useDemoClinic();
  return (
    <ClinicScreen title="المواعيد" state={state}>
      {(data) => {
        const days = groupByClinicDay(data.appointments, data.clinic.time_zone);
        return (
          <>
            <p className="muted">مواعيد إدارية مسجّلة في العيادة، بتوقيت {data.clinic.city_ar ?? "العيادة"}. لا تُحسب أي مواعيد من قواعد الفحص.</p>
            {days.length === 0 && <p className="empty">لا توجد مواعيد مسجّلة.</p>}
            <div className="stack">
              {days.map((day) => (
                <section key={day.key} className="stack-tight">
                  <SectionHead title={day.label} aside={`${day.appointments.length}`} />
                  <ul className="med-list">
                    {day.appointments.map((appointment) => (
                      <AppointmentRow key={appointment.id} appointment={appointment} data={data} />
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
  const state = useDemoClinic();
  return (
    <ClinicScreen title="المرضى" state={state}>
      {(data) => (
        <>
          <p className="muted">تعرض القائمة المرضى المرتبطين بهذه العيادة فقط.</p>
          {data.patients.length === 0 && <p className="empty">لا يوجد مرضى مرتبطون بالعيادة.</p>}
          <div className="grid-2">
            {data.patients.map((item) => (
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
  const state = useDemoClinic();
  return (
    <ClinicScreen title="الأطباء" state={state}>
      {(data) => (
        <>
          {data.doctors.length === 0 && <p className="empty">لا يوجد أطباء مسجّلون في العيادة.</p>}
          <div className="grid-2">
            {data.doctors.map((doctor) => (
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
