import { Link } from "react-router-dom";
import { api } from "../api/client";
import { SourceBadge } from "../components/feedback";
import { IconTile, Meter, Screen, SectionHead } from "../components/layout";
import { PatientGate, TestStatusPill, TestTile } from "../components/screening";
import { ACTIVITY } from "../demo/data";
import { useDemo } from "../demo/store";
import { testCount, testGroup } from "../lib/screening";
import { useSession } from "../lib/session";
import { useAsync } from "../lib/useAsync";

export function Home() {
  const demo = useDemo();
  const { patientId } = useSession();
  const state = useAsync(
    (signal) => (patientId === null ? Promise.resolve(null) : api.getScreeningSummary(patientId, signal)),
    [patientId],
  );
  const greeting = new Date().getHours() < 12 ? "صباح الخير" : "مساء الخير";
  const candidates = state.data?.tests.filter((test) => testGroup(test) === "candidate") ?? [];
  const undecided = state.data?.tests.filter((test) => testGroup(test) === "needs_information") ?? [];

  return (
    <Screen title="الرئيسية" wide>
      <div className="home-greeting">
        <div>
          <p className="muted">{greeting}</p>
          {patientId !== null && (
            <p className="home-greeting__name">
              ملف رقم <bdi>{patientId}</bdi>
            </p>
          )}
        </div>
        <Link to="/account" className="icon-btn icon-btn--large" aria-label="حسابي">
          <IconTile name="user" tone="plain" />
        </Link>
      </div>

      <div className="grid-2">
        <div className="stack">
          <PatientGate state={state} label="جارٍ تحميل ملخص الفحوصات…" />
          {state.data && (
            <>
              <section className="hero-card">
                <p className="hero-card__eyebrow">ملخص الفحوصات · من الخادم</p>
                <h2>{candidates.length > 0 ? `${testCount(candidates.length)} قد تنطبق عليك` : "لا فحوصات تنطبق قواعدها حالياً"}</h2>
                <p>
                  {undecided.length > 0 && `و${testCount(undecided.length)} تحتاج معلومات. `}
                  من قواعد مسودة لم يراجعها طبيب، وليست مواعيد أو توصيات معتمدة.
                </p>
                <div className="hero-card__actions">
                  <Link to="/checks" className="btn btn--light btn--small">
                    عرض الفحوصات
                  </Link>
                  <Link to="/log" className="btn btn--translucent btn--small">
                    سجل الفحوصات
                  </Link>
                </div>
              </section>

              {candidates.length > 0 && (
                <>
                  <SectionHead title="قد تنطبق عليك · للمراجعة" aside={<Link to="/checks">عرض الكل</Link>} />
                  {candidates.slice(0, 3).map((test) => (
                    <Link key={test.test_id} to={`/checks/${test.test_id}`} className="card row-card row-card--link">
                      <TestTile testId={test.test_id} group="candidate" />
                      <div className="row-card__body">
                        <strong>{test.name_ar}</strong>
                        <TestStatusPill group="candidate" />
                      </div>
                    </Link>
                  ))}
                </>
              )}
            </>
          )}
        </div>

        <div className="stack">
          <SectionHead
            title="هدفك هذا الأسبوع"
            aside={
              <>
                <SourceBadge kind="demo" /> <Link to="/activity">التفاصيل</Link>
              </>
            }
          />
          <Link to="/activity" className="card card--link stack-tight">
            <div className="spread">
              <strong>النشاط البدني</strong>
              <span className="muted small">
                {ACTIVITY.doneMinutes} من {demo.activityGoal} دقيقة
              </span>
            </div>
            <Meter value={ACTIVITY.doneMinutes} max={demo.activityGoal} label="النشاط البدني هذا الأسبوع" />
            <span className="muted small">أرقام تجريبية مكتوبة مسبقاً، لا توجد ساعة مربوطة.</span>
          </Link>

          <Link to="/chat" className="card card--soft row-card row-card--link">
            <IconTile name="chat" tone="green" />
            <div className="row-card__body">
              <strong>اسأل Vitala</strong>
              <span className="muted small">معاينة بردود جاهزة، وليست ذكاءً اصطناعياً.</span>
              <SourceBadge kind="demo" />
            </div>
          </Link>
        </div>
      </div>
    </Screen>
  );
}
