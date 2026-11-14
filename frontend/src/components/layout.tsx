import { useEffect, useRef, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { DemoNotice } from "./feedback";
import { Icon, Logo, type IconName } from "./Icon";

export const PATIENT_TABS: { to: string; label: string; icon: IconName }[] = [
  { to: "/home", label: "الرئيسية", icon: "home" },
  { to: "/checks", label: "فحوصاتي", icon: "list" },
  { to: "/tracking", label: "المتابعة", icon: "bars" },
  { to: "/log", label: "السجل", icon: "doc" },
  { to: "/account", label: "حسابي", icon: "user" },
];

function Nav({ tabs }: { tabs: { to: string; label: string; icon: IconName }[] }) {
  return (
    <nav className="nav" aria-label="التنقل الرئيسي">
      <div className="nav__brand">
        <Logo size={40} />
        <span>vitala</span>
      </div>
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          // Exact match only when another tab lives under this path, as /clinic does.
          end={tabs.some((other) => other.to.startsWith(`${tab.to}/`))}
          className="nav__item"
        >
          <Icon name={tab.icon} />
          <span>{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function Screen({
  title,
  back,
  nav = true,
  demo = false,
  demoText,
  wide = false,
  tabs = PATIENT_TABS,
  children,
}: {
  title: string;
  /** Show a back button, to this path or to the previous page when `true`. */
  back?: string | boolean;
  nav?: boolean;
  demo?: boolean;
  demoText?: ReactNode;
  wide?: boolean;
  tabs?: { to: string; label: string; icon: IconName }[];
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = `${title} · Vitala`;
    // Tell keyboard and screen-reader users that the page changed.
    heading.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [title]);

  const goBack = () => {
    if (typeof back === "string") navigate(back);
    else navigate(-1);
  };

  return (
    <div className={`shell${nav ? " shell--nav" : ""}`}>
      {nav && <Nav tabs={tabs} />}
      <div className="shell__page">
        <header className="topbar">
          <div className="topbar__side">
            {back && (
              <button type="button" className="icon-btn" onClick={goBack} aria-label="رجوع">
                <Icon name="chevron" size={20} />
              </button>
            )}
          </div>
          <h1 ref={heading} tabIndex={-1} className="topbar__title">
            {title}
          </h1>
          <div className="topbar__side topbar__side--end">
            <Logo />
          </div>
        </header>
        <main className={`page${wide ? " page--wide" : ""}`}>
          {demo && <DemoNotice>{demoText}</DemoNotice>}
          {children}
        </main>
      </div>
    </div>
  );
}

export function Progress({ step }: { step: 1 | 2 | 3 | 4 }) {
  return (
    <div className="steps" role="img" aria-label={`الخطوة ${step} من 4`}>
      {[1, 2, 3, 4].map((index) => (
        <span key={index} className={index <= step ? "steps__bar steps__bar--on" : "steps__bar"} />
      ))}
    </div>
  );
}

export function SectionHead({ title, aside }: { title: string; aside?: ReactNode }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {aside && <div className="section-head__aside">{aside}</div>}
    </div>
  );
}

export function IconTile({ name, tone }: { name: IconName; tone: string }) {
  return (
    <span className={`tile tile--${tone}`}>
      <Icon name={name} />
    </span>
  );
}

export function Pill({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`pill pill--${tone}`}>{children}</span>;
}

/** A bar that fills from the reading start. Text beside it carries the actual value. */
export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  return (
    <div
      className="meter"
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.min(value, max)}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <span style={{ width: `${Math.min(100, (value / max) * 100)}%` }} />
    </div>
  );
}
