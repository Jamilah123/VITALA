// Every screen in this file shows invented data from src/demo and says so.

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { SourceBadge, useToast } from "../components/feedback";
import { CheckRow, clearErrorOnEdit, DateField, Field, Modal } from "../components/forms";
import { IconTile, Meter, Pill, Screen, SectionHead } from "../components/layout";
import { ACTIVITY, DOCTOR_CHECKLIST, HBA1C_TARGET, PERSONA } from "../demo/data";
import { useDemo } from "../demo/store";
import { formatMonth, formatMonthYear, todayIso } from "../lib/dates";
import {
  parseNumber,
  rangeError,
  validateBloodPressure,
  validateResultDate,
  type FieldErrors,
} from "../lib/validation";

function useDemoReminder() {
  const demo = useDemo();
  const toast = useToast();
  return (id: string) => {
    if (!demo.reminders.includes(id)) demo.update({ reminders: [...demo.reminders, id] });
    toast("حُفظ تذكير تجريبي. لن يصلك إشعار فعلي، فالتذكيرات غير متاحة بعد.");
  };
}

function shortMonth(iso: string): string {
  return formatMonth(iso).slice(0, 3);
}

function BloodPressureDialog({ onClose }: { onClose: () => void }) {
  const demo = useDemo();
  const toast = useToast();
  const [date, setDate] = useState(todayIso());
  const [systolic, setSystolic] = useState("");
  const [diastolic, setDiastolic] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found = validateBloodPressure(systolic, diastolic);
    const dateError = validateResultDate(date);
    if (dateError) found.date = dateError;
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    demo.addResult("bp", { date, value: `${parseNumber(systolic)}/${parseNumber(diastolic)} mmHg` });
    toast("أُضيف قياس تجريبي في هذا المتصفح فقط، ولم يُرسل إلى الخادم.");
    onClose();
  };

  return (
    <Modal title="إضافة قياس ضغط (تجريبي)" onClose={onClose}>
      <form className="stack" onSubmit={submit} onChange={clearErrorOnEdit(setErrors)} noValidate>
        <DateField name="date" label="التاريخ" value={date} onChange={setDate} error={errors.date} />
        <Field name="systolic" label="الانقباضي" suffix="mmHg" value={systolic} onChange={setSystolic} error={errors.systolic} inputMode="numeric" />
        <Field name="diastolic" label="الانبساطي" suffix="mmHg" value={diastolic} onChange={setDiastolic} error={errors.diastolic} inputMode="numeric" />
        <div className="btn-row">
          <button type="button" className="btn btn--outline" onClick={onClose}>
            إلغاء
          </button>
          <button type="submit" className="btn btn--primary btn--grow">
            حفظ
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function Tracking() {
  const demo = useDemo();
  const [addingPressure, setAddingPressure] = useState(false);
  const hba1c = demo.resultsFor("hba1c");
  const [latest, previous] = hba1c;
  const latestValue = parseFloat(latest.value);
  const previousValue = previous ? parseFloat(previous.value) : null;
  const change = previousValue === null ? null : Math.round((latestValue - previousValue) * 10) / 10;
  const bars = hba1c.slice(0, 2).reverse();
  const scaleMax = Math.max(...bars.map((bar) => parseFloat(bar.value)));
  const pressure = demo.resultsFor("bp")[0];

  return (
    <Screen title="متابعة السكري والضغط" demo wide>
      <p className="muted">مسار المتابعة: ما المطلوب قياسه، وما الذي يُفحص للكشف المبكر عن المضاعفات.</p>
      <div className="grid-2">
        <section className="card stack">
          <div className="spread">
            <h2 className="group-title">السكري</h2>
            <Pill tone="blue">
              <bdi dir="ltr">HbA1c {latest.value}</bdi>
            </Pill>
          </div>
          <div className="spread spread--top">
            <div>
              <p className="muted small">الهدف في هذا المثال</p>
              <strong>
                <bdi dir="ltr">{HBA1C_TARGET}</bdi>
              </strong>
            </div>
            {change !== null && previous && (
              <div>
                <p className="muted small">التغيّر منذ {formatMonth(previous.date)}</p>
                <strong className={change < 0 ? "text-green" : undefined}>
                  {change < 0 ? "↓" : change > 0 ? "↑" : ""} {Math.abs(change)}
                </strong>
              </div>
            )}
          </div>
          <div className="bars bars--two" role="img" aria-label={bars.map((bar) => `${formatMonthYear(bar.date)}: ${bar.value}`).join("، ")}>
            {/* Older result on the reading start, per the PDF. */}
            {bars.map((bar, index) => (
              <div key={bar.date + index} className="bars__col" title={`${formatMonthYear(bar.date)}: ${bar.value}`}>
                <span className="bars__value">
                  <bdi dir="ltr">{bar.value}</bdi>
                </span>
                <div className="bars__plot">
                  <span
                    className={index === bars.length - 1 ? "bars__bar bars__bar--strong" : "bars__bar"}
                    style={{ height: `${(parseFloat(bar.value) / scaleMax) * 100}%` }}
                  />
                </div>
                <span className="bars__label">{shortMonth(bar.date)}</span>
              </div>
            ))}
          </div>
        </section>

        <div className="stack">
          <section className="card stack-tight">
            <div className="spread">
              <h2 className="group-title">ضغط الدم</h2>
              <Pill tone="amber">
                <bdi dir="ltr">{pressure.value.replace(" mmHg", "")}</bdi>
              </Pill>
            </div>
            <p className="muted small">آخر قياس {formatMonthYear(pressure.date)}. قياس المنزل يساعد طبيبك على ضبط العلاج.</p>
            <div className="end">
              <button type="button" className="btn btn--outline btn--small" onClick={() => setAddingPressure(true)}>
                إضافة قياس
              </button>
            </div>
          </section>
          <SectionHead title="فحوصات المضاعفات" />
          <Link to="/checks/eye_exam" className="card row-card row-card--link">
            <IconTile name="eye" tone="plain" />
            <div className="row-card__body">
              <strong>فحص العين</strong>
              <span className="muted small">القواعد وسجلك من الخادم.</span>
              <SourceBadge kind="live" />
            </div>
          </Link>
          <Link to="/checks/uacr" className="card row-card row-card--link">
            <IconTile name="flask" tone="plain" />
            <div className="row-card__body">
              <strong>وظائف الكلى (UACR)</strong>
              <span className="muted small">القواعد وسجلك من الخادم.</span>
              <SourceBadge kind="live" />
            </div>
          </Link>
          <p className="note">Vitala لا تشخّص ولا تغيّر العلاج. القرارات الدوائية مع طبيبك.</p>
        </div>
      </div>
      {addingPressure && <BloodPressureDialog onClose={() => setAddingPressure(false)} />}
    </Screen>
  );
}

export function Activity() {
  const demo = useDemo();
  const remind = useDemoReminder();
  const goal = demo.activityGoal;
  const remaining = Math.max(0, goal - ACTIVITY.doneMinutes);
  const peak = Math.max(...ACTIVITY.days.map((day) => day.minutes));

  return (
    <Screen title="هدف النشاط" back="/home" demo wide>
      <div className="grid-2">
        <section className="card activity-hero">
          <p className="muted">الهدف الأسبوعي في هذا المثال</p>
          <p className="activity-hero__figure">
            <span className="activity-hero__number">{ACTIVITY.doneMinutes}</span> / {goal} دقيقة
          </p>
          <Meter value={ACTIVITY.doneMinutes} max={goal} label="الدقائق النشطة هذا الأسبوع" />
          <p className="muted small">{remaining > 0 ? `باقي ${remaining} دقيقة نشطة حتى السبت.` : "اكتمل الهدف الأسبوعي."}</p>
        </section>
        <section className="card stack-tight">
          <h2 className="group-title">هذا الأسبوع</h2>
          <div
            className="bars"
            role="img"
            aria-label={ACTIVITY.days.map((day) => `${day.name}: ${day.minutes} دقيقة`).join("، ")}
          >
            {ACTIVITY.days.map((day) => (
              <div key={day.label} className="bars__col" title={`${day.name}: ${day.minutes} دقيقة`}>
                <div className="bars__plot">
                  <span
                    className={day.label === ACTIVITY.highlightDay ? "bars__bar bars__bar--strong" : "bars__bar"}
                    style={{ height: `${(day.minutes / peak) * 100}%` }}
                  />
                </div>
                <span className="bars__label">{day.label}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className="stat-row">
        <div className="card stat">
          <span className="muted small">الخطوات اليوم</span>
          <strong>{ACTIVITY.stepsToday}</strong>
        </div>
        <div className="card stat">
          <span className="muted small">متوسط النبض</span>
          <strong>{ACTIVITY.averagePulse}</strong>
        </div>
        <div className="card stat">
          <span className="muted small">النوم</span>
          <strong>{ACTIVITY.sleep}</strong>
        </div>
      </div>
      <p className="note">لا توجد ساعة مربوطة: هذه الأرقام مكتوبة مسبقاً. الهدف 150 دقيقة أسبوعياً مناسب لمعظم البالغين، وقد يعدّله طبيبك.</p>
      <button type="button" className="btn btn--primary btn--block" onClick={() => remind("activity")}>
        ضبط تذكير يومي (تجريبي)
      </button>
    </Screen>
  );
}

export function DoctorView() {
  const demo = useDemo();
  const toast = useToast();
  const [editingGoal, setEditingGoal] = useState(false);
  const [goalText, setGoalText] = useState(String(demo.activityGoal));
  const [goalError, setGoalError] = useState<string | null>(null);
  const confirmed = DOCTOR_CHECKLIST.filter((item) => demo.doctorConfirmed.includes(item.id)).length;
  const total = DOCTOR_CHECKLIST.length + 1;

  const toggle = (id: string, checked: boolean) =>
    demo.update({
      doctorConfirmed: checked ? [...demo.doctorConfirmed, id] : demo.doctorConfirmed.filter((item) => item !== id),
    });

  const saveGoal = (event: FormEvent) => {
    event.preventDefault();
    const error = rangeError(goalText, 10, 1000, "دقيقة");
    setGoalError(error);
    if (error) return;
    demo.update({ activityGoal: Math.round(parseNumber(goalText)!) });
    setEditingGoal(false);
  };

  return (
    <Screen
      title="عرض الطبيب"
      back
      nav={false}
      demo
      demoText="معاينة لما قد يراه الطبيب. لم يُرسل شيء إلى أي طبيب، ولا تُحفظ المراجعة إلا في هذا المتصفح."
    >
      <section className="card card--soft spread">
        <div>
          <strong>
            {PERSONA.name} · {PERSONA.age} سنة · {PERSONA.sex}
          </strong>
          <p className="muted small">
            {PERSONA.conditions} · BMI {PERSONA.bmi}
          </p>
        </div>
        <Pill tone="blue">ملف تجريبي</Pill>
      </section>

      <SectionHead title="قائمة المراجعة" aside={`${confirmed} من ${total} مؤكدة`} />
      <div className="stack">
        {DOCTOR_CHECKLIST.map((item) => (
          <div key={item.id} className="card doctor-row">
            <CheckRow checked={demo.doctorConfirmed.includes(item.id)} onChange={(checked) => toggle(item.id, checked)}>
              <strong>{item.title}</strong>
              <span className="muted small">{item.detail}</span>
            </CheckRow>
            <Pill tone={item.tone}>{item.badge}</Pill>
          </div>
        ))}
        <div className="card doctor-row">
          <div className="row-card__body doctor-row__goal">
            <strong>هدف النشاط</strong>
            <span className="muted small">
              {demo.activityGoal} دقيقة أسبوعياً · أنجز {ACTIVITY.doneMinutes}
            </span>
          </div>
          <button
            type="button"
            className="btn btn--outline btn--small"
            onClick={() => {
              setGoalText(String(demo.activityGoal));
              setGoalError(null);
              setEditingGoal(true);
            }}
          >
            تعديل
          </button>
        </div>
      </div>

      {demo.doctorReviewedOn && <p className="note">سُجّلت مراجعة تجريبية في {demo.doctorReviewedOn}. لم يراجع طبيب هذه البيانات فعلياً.</p>}
      <button
        type="button"
        className="btn btn--primary btn--block"
        onClick={() => {
          demo.update({ doctorReviewedOn: todayIso() });
          toast("سُجّلت مراجعة تجريبية في هذا المتصفح فقط.");
        }}
      >
        تأكيد المراجعة (تجريبي)
      </button>
      <p className="note">أداة دعم تخطيط وقائي. لا تغني عن التقدير السريري.</p>

      {editingGoal && (
        <Modal title="تعديل هدف النشاط (تجريبي)" onClose={() => setEditingGoal(false)}>
          <form className="stack" onSubmit={saveGoal} noValidate>
            <Field label="الهدف الأسبوعي" suffix="دقيقة" value={goalText} onChange={(next) => {
                setGoalText(next);
                setGoalError(null);
              }} error={goalError ?? undefined} inputMode="numeric" />
            <div className="btn-row">
              <button type="button" className="btn btn--outline" onClick={() => setEditingGoal(false)}>
                إلغاء
              </button>
              <button type="submit" className="btn btn--primary btn--grow">
                حفظ
              </button>
            </div>
          </form>
        </Modal>
      )}
    </Screen>
  );
}

export function NotFound() {
  return (
    <Screen title="الصفحة غير موجودة">
      <p className="empty">لم نجد هذه الصفحة.</p>
      <Link to="/" className="btn btn--primary btn--block">
        العودة إلى البداية
      </Link>
    </Screen>
  );
}
