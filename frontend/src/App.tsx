import { Component, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./components/feedback";
import { DemoProvider } from "./demo/store";
import { SessionProvider, useSession } from "./lib/session";
import { Account, HealthProfile, Sources } from "./screens/account";
import { Chat } from "./screens/Chat";
import {
  Activity,
  CheckDetail,
  Checks,
  DoctorView,
  Home,
  NotFound,
  ResultsLog,
  Tracking,
} from "./screens/demoScreens";
import { BasicInfo, HealthHistory, OnboardingDone, OpenProfile, WatchLink, Welcome } from "./screens/onboarding";

function Root() {
  const { patientId } = useSession();
  return <Navigate to={patientId === null ? "/welcome" : "/home"} replace />;
}

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="fatal" role="alert">
        <h1>حدث خطأ غير متوقع</h1>
        <button type="button" className="btn btn--primary" onClick={() => window.location.assign("/")}>
          إعادة تحميل التطبيق
        </button>
      </div>
    );
  }
}

export function App() {
  return (
    <ErrorBoundary>
      <SessionProvider>
        <DemoProvider>
          <ToastProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<Root />} />
                <Route path="/welcome" element={<Welcome />} />
                <Route path="/open-profile" element={<OpenProfile />} />
                <Route path="/onboarding/basic" element={<BasicInfo />} />
                <Route path="/onboarding/history" element={<HealthHistory />} />
                <Route path="/onboarding/watch" element={<WatchLink />} />
                <Route path="/onboarding/done" element={<OnboardingDone />} />
                <Route path="/home" element={<Home />} />
                <Route path="/checks" element={<Checks />} />
                <Route path="/checks/:checkId" element={<CheckDetail />} />
                <Route path="/tracking" element={<Tracking />} />
                <Route path="/activity" element={<Activity />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/log" element={<ResultsLog />} />
                <Route path="/doctor" element={<DoctorView />} />
                <Route path="/account" element={<Account />} />
                <Route path="/account/health" element={<HealthProfile />} />
                <Route path="/account/sources" element={<Sources />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </BrowserRouter>
          </ToastProvider>
        </DemoProvider>
      </SessionProvider>
    </ErrorBoundary>
  );
}
