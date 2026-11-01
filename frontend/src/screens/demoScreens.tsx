// Every screen in this file shows invented data from src/demo and says so.

import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useToast } from "../components/feedback";
import { CheckRow, clearErrorOnEdit, DateField, Field, Modal } from "../components/forms";
import { IconTile, Meter, Pill, Screen, SectionHead } from "../components/layout";
import {
  ACTIVITY,
  ATTENTION,
  CHECKS,
  DOCTOR_CHECKLIST,
  getCheck,
  HBA1C_TARGET,
  LOG_GROUPS,
  NEXT_STEP,
  PERSONA,
  type CheckStatus,
  type DemoCheck,
} from "../demo/data";
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

export function Home() {
  const demo = useDemo();
  const remind = useDemoReminder();
  const greeting = new Date().getHours() < 12 ? "صباح الخير" : "مساء الخير";

  return (
    <Screen title="الرئيسية" demo wide>
      <div className="home-greeting">
        <div>
          <p className="muted">{greeting}</p>
          <p className="home-greeting__name">{PERSONA.name}</p>
        </div>
        <Link to="/account" className="icon-btn icon-btn--large" aria-label="حسابي">
          <IconTile name="user" tone="plain" />
        </Link>
      </div>

      <div className="grid-2">
        <div className="stack">
          <section className="hero-card">
            <p className="hero-card__eyebrow">خطوتك التالية</p>
            <h2>{NEXT_STEP.title}</h2>
            <p>{NEXT_STEP.when}</p>
            <div className="hero-card__actions">
              <Link to={`/checks/${NEXT_STEP.checkId}`} className="btn btn--light btn--small">
                لماذا هذا الفحص؟
              </Link>
              <button type="button" className="btn btn--translucent btn--small" onClick={() => remind(NEXT_STEP.checkId)}>
                ذكّرني
              </button>
            </div>
          </section>

          <SectionHead title="يحتاج انتباهك" aside={<Link to="/checks">عرض الكل</Link>} />
          <Link to={`/checks/${ATTENTION.checkId}`} className="card row-card row-card--link">
            <IconTile name="eye" tone="rose" />
            <div className="row-card__body">
              <strong>{ATTENTION.title}</strong>
              <span className="muted small">{ATTENTION.detail}</span>
              <Pill tone="rose">{ATTENTION.badge}</Pill>
            </div>
          </Link>
        </div>

        <div className="stack">
          <SectionHead title="هدفك هذا الأسبوع" aside={<Link to="/activity">التفاصيل</Link>} />
          <Link to="/activity" className="card card--link stack-tight">
            <div className="spread">
              <strong>النشاط البدني</strong>
              <span className="muted small">
                {ACTIVITY.doneMinutes} من {demo.activityGoal} دقيقة
              </span>
            </div>
            <Meter value={ACTIVITY.doneMinutes} max={demo.activityGoal} label="النشاط البدني هذا الأسبوع" />
          </Link>

          <Link to="/chat" className="card card--soft row-card row-card--link">
            <IconTile name="chat" tone="green" />
            <div className="row-card__body">
              <strong>اسأل Vitala</strong>
              <span className="muted small">معاينة بردود جاهزة، وليست ذكاءً اصطناعياً.</span>
            </div>
          </Link>
        </div>
      </div>
    </Screen>
  );
}

const STATUS_COLOR: Record<CheckStatus, { color: string; label: string }> = {
  due: { color: "#b4c0da", label: "مستحق" },
  overdue: { color: "#c98a95", label: "متأخر" },
  upcoming: { color: "#e8bc58", label: "قادم" },
  done: { color: "#6a7f54", label: "مكتمل" },
};

function CheckDonut({ checks }: { checks: DemoCheck[] }) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const gap = 2;
  let offset = 0;
  const statuses = Object.keys(STATUS_COLOR) as CheckStatus[];
  const segments = statuses.map((status) => {
    const count = checks.filter((check) => check.status === status).length;
    const length = (count / checks.length) * circumference;
    const segment = { status, count, length, offset };
    offset += length;
    return segment;
  });
  const summary = segments.map((segment) => `${segment.count} ${STATUS_COLOR[segment.status].label}`).join(" · ");

  return (
    <div className="card map-card">
      <svg viewBox="0 0 100 100" width="104" height="104" role="img" aria-label={`${checks.length} فحوصات: ${summary}`}>
        <g transform="rotate(-90 50 50)">
          {segments.map((segment) => (
            <circle
              key={segment.status}
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              stroke={STATUS_COLOR[segment.status].color}
              strokeWidth="12"
              strokeDasharray={`${Math.max(0, segment.length - gap)} ${circumference}`}
              strokeDashoffset={-segment.offset}
            >
              <title>
                {STATUS_COLOR[segment.status].label}: {segment.count}
              </title>
            </circle>
          ))}
        </g>
        <text x="50" y="50" textAnchor="middle" dominantBaseline="central" className="donut-number">
          {checks.length}
        </text>
      </svg>
      <div className="map-card__text">
        <strong>خريطة الوقاية التجريبية</strong>
        <ul className="legend">
          {segments.map((segment) => (
            <li key={segment.status}>
              <span className="legend__swatch" style={{ background: STATUS_COLOR[segment.status].color }} />
              {segment.count} {STATUS_COLOR[segment.status].label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const FILTERS = [
  { id: "now", label: "مستحق الآن", tone: "rose", matches: (check: DemoCheck) => check.status === "due" || check.status === "overdue" },
  { id: "soon", label: "قريب", tone: "amber", matches: (check: DemoCheck) => check.status === "upcoming" },
  { id: "done", label: "مكتمل", tone: "green", matches: (check: DemoCheck) => check.status === "done" },
  { id: "info", label: "يحتاج معلومات", tone: "blue", matches: () => false },
] as const;

function CheckCard({ check }: { check: DemoCheck }) {
  return (
    <Link to={`/checks/${check.id}`} className="card row-card row-card--link">
      <IconTile name={check.icon} tone={check.iconTone} />
      <div className="row-card__body">
        <strong>{check.title}</strong>
        <span className="muted small">{check.cadence}</span>
        <Pill tone={check.statusTone}>{check.statusLabel}</Pill>
      </div>
    </Link>
  );
}

export function Checks() {
  const [filter, setFilter] = useState<string | null>(null);
  const active = FILTERS.find((item) => item.id === filter);
  const groups = [
    { title: "المستحقة الآن", unit: "فحوصات", items: CHECKS.filter((check) => check.section === "now") },
    { title: "قادمة", unit: "فحص", items: CHECKS.filter((check) => check.section === "later") },
  ].map((group) => ({ ...group, items: active ? group.items.filter(active.matches) : group.items }));
  const empty = groups.every((group) => group.items.length === 0);

  return (
    <Screen title="الفحوصات" demo wide>
      <p className="muted">في النسخة الفعلية ستُبنى الخريطة على العمر والجنس والحالة الصحية والتاريخ العائلي. هذه الخريطة ثابتة ولا تتغير بملفك.</p>
      <CheckDonut checks={CHECKS} />
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
      {empty && <p className="empty">لا توجد فحوصات في هذا التصنيف.</p>}
      <div className="grid-2">
        {groups
          .filter((group) => group.items.length > 0)
          .map((group) => (
            <section key={group.title} className="stack">
              <SectionHead title={group.title} aside={`${group.items.length} ${group.unit}`} />
              {group.items.map((check) => (
                <CheckCard key={check.id} check={check} />
              ))}
            </section>
          ))}
      </div>
    </Screen>
  );
}

function AddResultForm({ check }: { check: DemoCheck }) {
  const demo = useDemo();
  const toast = useToast();
  const [date, setDate] = useState(todayIso());
  const [value, setValue] = useState("");
  const [systolic, setSystolic] = useState("");
  const [diastolic, setDiastolic] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: FieldErrors = {};
    const dateError = validateResultDate(date);
    if (dateError) found.date = dateError;

    let display = "تم الفحص";
    if (check.result === "blood_pressure") {
      Object.assign(found, validateBloodPressure(systolic, diastolic));
      display = `${parseNumber(systolic)}/${parseNumber(diastolic)} mmHg`;
    } else if (check.result !== "date_only") {
      const { min, max, unit, label } = check.result;
      const error = rangeError(value, min, max, unit);
      if (error) found.value = error;
      const prefix = label === "النتيجة" ? "" : `${label} `;
      display = unit === "%" ? `${parseNumber(value)}%` : `${prefix}${parseNumber(value)} ${unit}`;
    }

    setErrors(found);
    if (Object.keys(found).length > 0) return;
    demo.addResult(check.id, { date, value: display });
    setValue("");
    setSystolic("");
    setDiastolic("");
    toast("أُضيفت نتيجة تجريبية في هذا المتصفح فقط، ولم تُرسل إلى الخادم.");
  };

  return (
    <form className="card stack" onSubmit={submit} onChange={clearErrorOnEdit(setErrors)} noValidate>
      <h2 className="group-title">أضيفي نتيجة (تجريبي)</h2>
      <div className="grid-fields">
        <DateField name="date" label="التاريخ" value={date} onChange={setDate} error={errors.date} />
        {check.result === "blood_pressure" && (
          <>
            <Field name="systolic" label="الانقباضي" value={systolic} onChange={setSystolic} error={errors.systolic} inputMode="numeric" />
            <Field name="diastolic" label="الانبساطي" value={diastolic} onChange={setDiastolic} error={errors.diastolic} inputMode="numeric" />
          </>
        )}
        {check.result !== "blood_pressure" && check.result !== "date_only" && (
          <Field
            name="value"
            label={check.result.label}
            suffix={check.result.unit}
            value={value}
            onChange={setValue}
            error={errors.value}
            inputMode="decimal"
          />
        )}
      </div>
      <div className="upload-placeholder" aria-disabled="true">
        إرفاق صورة أو مستند — غير متاح بعد
      </div>
      <button type="submit" className="btn btn--primary btn--block">
        حفظ النتيجة
      </button>
    </form>
  );
}

export function CheckDetail() {
  const { checkId } = useParams();
  const check = getCheck(checkId);
  const demo = useDemo();
  const remind = useDemoReminder();

  if (!check) {
    return (
      <Screen title="تفاصيل الفحص" back="/checks">
        <p className="empty">لم نجد هذا الفحص.</p>
      </Screen>
    );
  }
  const latest = demo.resultsFor(check.id)[0];

  return (
    <Screen title="تفاصيل الفحص" back="/checks" demo wide>
      <section className="card detail-hero">
        <IconTile name={check.icon} tone={check.iconTone} />
        <h2>{check.fullTitle}</h2>
        <p className="muted">{check.detailCadence}</p>
        <Pill tone={check.statusTone}>{check.statusLabel}</Pill>
      </section>
      <div className="grid-2">
        <div className="stack">
          <section className="card row-card">
            <IconTile name="doc" tone="blue" />
            <div className="row-card__body">
              <strong>لماذا يُنصح به؟</strong>
              <span className="muted small">{check.why}</span>
            </div>
          </section>
          <section className="card row-card">
            <IconTile name="user" tone="green" />
            <div className="row-card__body">
              <strong>لماذا ظهر في هذا المثال؟</strong>
              <span className="muted small">{check.whyPersona}</span>
            </div>
          </section>
          <section className="card stack-tight">
            <strong>آخر نتيجة والمصدر</strong>
            <span className="muted small">
              {latest ? (
                <>
                  {formatMonthYear(latest.date)} · <bdi dir="ltr">{latest.value}</bdi>
                </>
              ) : (
                "لا توجد نتيجة مسجّلة."
              )}
            </span>
            <span className="muted small">
              المصدر (مثال من التصميم): <bdi>{check.source}</bdi>
            </span>
            {check.rule && (
              <span className="muted small">
                القاعدة (مثال من التصميم): <bdi>{check.rule}</bdi>
              </span>
            )}
            <span className="muted small">لم يراجع طبيب هذا المحتوى بعد.</span>
          </section>
        </div>
        <div className="stack">
          <AddResultForm check={check} />
          <button type="button" className="btn btn--outline btn--block" onClick={() => remind(check.id)}>
            ضبط تذكير (تجريبي)
          </button>
        </div>
      </div>
    </Screen>
  );
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
          <Link to="/checks/eye" className="card row-card row-card--link">
            <IconTile name="eye" tone="rose" />
            <div className="row-card__body">
              <strong>قاع العين</strong>
              <span className="muted small">سنوياً.</span>
              <Pill tone="rose">متأخر</Pill>
            </div>
          </Link>
          <Link to="/checks/uacr" className="card row-card row-card--link">
            <IconTile name="flask" tone="blue" />
            <div className="row-card__body">
              <strong>وظائف الكلى (UACR)</strong>
              <span className="muted small">سنوياً.</span>
              <Pill tone="neutral">بعد شهرين</Pill>
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

export function ResultsLog() {
  const demo = useDemo();
  const navigate = useNavigate();
  const groups = LOG_GROUPS.map((group) => ({ ...group, entries: demo.resultsFor(group.checkId) })).filter(
    (group) => group.entries.length > 0,
  );

  return (
    <Screen title="سجل النتائج" demo wide>
      <p className="muted">النتائج والمواعيد في خط زمني واحد.</p>
      <div className="grid-2">
        {groups.map((group) => (
          <section key={group.checkId} className="card stack-tight">
            <div className="spread">
              <h2 className="group-title">{group.title}</h2>
              {/* A status written for the base data must not vouch for values typed in here. */}
              {demo.hasAddedResults(group.checkId) ? (
                <Pill tone="neutral">فيه إضافة تجريبية</Pill>
              ) : (
                group.status && <Pill tone="green">{group.status}</Pill>
              )}
            </div>
            {group.entries.map((entry, index) => (
              <p key={entry.date + index} className="muted small">
                {formatMonthYear(entry.date)} · <bdi dir="ltr">{entry.value}</bdi>
              </p>
            ))}
          </section>
        ))}
      </div>
      <button type="button" className="btn btn--outline btn--block" onClick={() => navigate("/doctor")}>
        معاينة ملخص الطبيب
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
