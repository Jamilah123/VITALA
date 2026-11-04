import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { parseFieldErrors } from "../api/errors";
import type { RiskProfile } from "../api/types";
import {
  draftFromRisk,
  hasBrowserData,
  planBrowserImport,
  riskInputFromDraft,
  saveRiskProfile,
  UNKNOWN_DRAFT,
  validateRiskDraft,
} from "./riskProfile";
import type { BrowserProfile } from "./session";

const UNKNOWN_SERVER: RiskProfile = {
  patient_id: 4,
  stored: false,
  smoking_status: "unknown",
  height_cm: null,
  weight_kg: null,
  bmi: null,
  activity_minutes_per_week: null,
  raised_lipids: "unknown",
  pregnancy_status: "unknown",
  family_diabetes: "unknown",
  family_heart_disease: "unknown",
  family_breast_cancer: "unknown",
  family_colorectal_cancer: "unknown",
};

const EMPTY_BROWSER: BrowserProfile = { height: "", weight: "", dyslipidemia: false, familyHistory: [] };

describe("risk profile drafts", () => {
  it("keeps unknown values unknown and empty measurements null", () => {
    const input = riskInputFromDraft(UNKNOWN_DRAFT);

    expect(input.height_cm).toBeNull();
    expect(input.activity_minutes_per_week).toBeNull();
    expect(Object.values(input)).not.toContain("no");
    expect(draftFromRisk(UNKNOWN_SERVER)).toEqual(UNKNOWN_DRAFT);
  });

  it("round-trips stored values, including zero minutes", () => {
    const stored: RiskProfile = { ...UNKNOWN_SERVER, smoking_status: "former", height_cm: 172.5, activity_minutes_per_week: 0 };

    expect(riskInputFromDraft(draftFromRisk(stored))).toMatchObject({ smoking_status: "former", height_cm: 172.5, activity_minutes_per_week: 0 });
  });

  it("validates ranges with the API's field names and accepts Arabic digits", () => {
    expect(Object.keys(validateRiskDraft({ height: "49", weight: "351", activity: "-5" })).sort()).toEqual([
      "activity_minutes_per_week",
      "height_cm",
      "weight_kg",
    ]);
    expect(validateRiskDraft({ height: "١٧٠", weight: "", activity: "١٥٠" })).toEqual({});
    for (const activity of ["150.5", "10081", "abc"]) expect(validateRiskDraft({ height: "", weight: "", activity }).activity_minutes_per_week).toBeDefined();
  });
});

describe("browser import", () => {
  it("offers nothing when the browser holds nothing", () => {
    expect(hasBrowserData(EMPTY_BROWSER)).toBe(false);
    expect(planBrowserImport(EMPTY_BROWSER, UNKNOWN_SERVER)).toEqual({ input: {}, imported: [], skipped: [] });
  });

  it("copies typed values into fields the server does not have", () => {
    const browser = { height: "165", weight: "٦٠", dyslipidemia: true, familyHistory: ["سكري", "القولون"] };
    const plan = planBrowserImport(browser, UNKNOWN_SERVER);

    expect(hasBrowserData(browser)).toBe(true);
    expect(plan.input).toEqual({
      height_cm: 165,
      weight_kg: 60,
      raised_lipids: "yes",
      family_diabetes: "yes",
      family_colorectal_cancer: "yes",
    });
    expect(plan.skipped).toEqual([]);
  });

  it("never turns an unselected option into no", () => {
    const plan = planBrowserImport({ ...EMPTY_BROWSER, height: "170" }, UNKNOWN_SERVER);

    expect(plan.input).toEqual({ height_cm: 170 });
    expect(Object.values(plan.input)).not.toContain("no");
  });

  it("never overwrites a value the server already holds", () => {
    const server: RiskProfile = { ...UNKNOWN_SERVER, stored: true, height_cm: 180, raised_lipids: "no", family_diabetes: "no" };
    const plan = planBrowserImport({ height: "165", weight: "70", dyslipidemia: true, familyHistory: ["سكري"] }, server);

    expect(plan.input).toEqual({ weight_kg: 70 });
    expect(plan.skipped).toHaveLength(3);
  });

  it("skips browser values that are not valid measurements", () => {
    const plan = planBrowserImport({ ...EMPTY_BROWSER, height: "1700", weight: "abc" }, UNKNOWN_SERVER);

    expect(plan.input).toEqual({});
    expect(plan.skipped).toHaveLength(2);
  });
});

describe("risk profile API", () => {
  afterEach(() => vi.unstubAllGlobals());

  const respond = (body: unknown, status = 200) => vi.fn(async () => new Response(JSON.stringify(body), { status }));

  it("reads, creates, and updates on the patient's risk-profile path", async () => {
    const fetchMock = respond(UNKNOWN_SERVER);
    vi.stubGlobal("fetch", fetchMock);

    await api.getRiskProfile(4);
    await saveRiskProfile(4, false, { smoking_status: "never" });
    await saveRiskProfile(4, true, { smoking_status: "former" });

    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([path, init]) => [path, init.method ?? "GET"])).toEqual([
      ["/api/patients/4/risk-profile", "GET"],
      ["/api/patients/4/risk-profile", "POST"],
      ["/api/patients/4/risk-profile", "PATCH"],
    ]);
    expect(calls[2][1].body).toBe(JSON.stringify({ smoking_status: "former" }));
  });

  it("translates the backend's risk-factor errors", () => {
    const errors = parseFieldErrors([
      { loc: ["body", "pregnancy_status"], msg: "Value error, Pregnancy cannot be yes for a patient recorded as male" },
      { loc: ["body", "sex"], msg: "Value error, Sex cannot be male while pregnancy is recorded as yes" },
      { loc: ["body", "height_cm"], msg: "Input should be greater than or equal to 50" },
      { loc: ["body", "activity_minutes_per_week"], msg: "Input should be a valid integer" },
    ]);

    expect(errors.pregnancy_status).toContain("الحمل");
    expect(errors.sex).toContain("الحمل");
    expect(errors.height_cm).toBe("القيمة خارج النطاق المسموح.");
    expect(errors.activity_minutes_per_week).toBe("يلزم إدخال رقم صالح.");
  });
});
