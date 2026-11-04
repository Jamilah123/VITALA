/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { errorFromResponse, parseFieldErrors } from "../api/errors";
import type { ScreeningAction, ScreeningTestSummary } from "../api/types";
import {
  citedSources,
  exclusionReason,
  fieldLabel,
  reviewFlag,
  reviewReason,
  reviewStatusLabel,
  RULE_STATUS,
  sortRules,
  testCount,
  testGroup,
} from "./screening";
import { validateScreeningRecord } from "./validation";

const DATA_DIR = join(__dirname, "..", "..", "..", "backend", "data");
const readRules = (name: string): { required_inputs: string[]; review_flags: string[] }[] =>
  JSON.parse(readFileSync(join(DATA_DIR, name), "utf-8"));
const RULES = [...readRules("disease_rules.json"), ...readRules("medication_monitoring.json")];
const BACKEND_ALIASES = new Set(["diabetes_diagnosed", "hypertension_diagnosed"]);

function rule(id: string, status: ScreeningAction["status"], sourceIds: string[] = []): ScreeningAction {
  return {
    rule_id: id,
    track: "diabetes",
    action_id: "x",
    action_name_ar: "x",
    eligibility_ar: "x",
    status,
    reasons: [],
    missing_inputs: [],
    matched_medication_ids: [],
    schedule_text_ar: "كل 6 أشهر",
    notes_ar: "",
    review_flags: [],
    conflict_ids: [],
    knowledge_ids: [],
    sources: sourceIds.map((source_id) => ({
      source_id,
      locator: `${id} locator`,
      title: `title ${source_id}`,
      issuer: "وزارة الصحة السعودية",
      url: "https://www.moh.gov.sa/",
      version: null,
      limitation_ar: "x",
    })),
    review_status: "draft_not_clinician_reviewed",
    auto_schedule_enabled: false,
  };
}

function test(candidates: string[], undecided: string[], rules: ScreeningAction[] = []): ScreeningTestSummary {
  return {
    test_id: "hba1c",
    name_ar: "السكر التراكمي",
    mapping_status: "draft_not_clinician_reviewed",
    recorded_tests: [],
    history_inputs: [],
    ambiguous_history_fields: [],
    candidate_rule_ids: candidates,
    needs_information_rule_ids: undecided,
    not_applicable_rule_ids: [],
    not_triggered_rule_ids: [],
    missing_inputs: [],
    review_reasons: [],
    conflict_ids: [],
    possible_overlap_test_ids: [],
    rules,
  };
}

describe("screening labels", () => {
  it("never present a rule status as due, overdue, or approved", () => {
    for (const status of Object.values(RULE_STATUS)) {
      expect(status.label).not.toMatch(/مستحق|متأخر|موعد|معتمد/);
      expect(status.detail).not.toMatch(/مستحق|متأخر|موعد/);
    }
    expect(RULE_STATUS.candidate.detail).toContain("ليست توصية طبية معتمدة");
    expect(RULE_STATUS.not_applicable.detail).toContain("لا يعني ذلك أن الفحص غير لازم");
  });

  it("translate every review reason and exclusion reason the backend sends", () => {
    const reviewReasons = [
      "draft_rules",
      "draft_test_grouping",
      "source_conflict",
      "mixed_rule_statuses",
      "possible_overlap",
      "history_not_used_by_rules",
      "history_mapping_pending_review",
      "ambiguous_history_mapping",
      "multiple_records_same_date",
    ];
    for (const code of reviewReasons) expect(reviewReason(code)).not.toBe(code);
    const exclusions = [
      "diabetes_not_diagnosed",
      "hypertension_not_diagnosed",
      "diabetes_diagnosed",
      "diabetes_type_not_covered",
      "diabetes_duration_below_minimum",
      "age_below_minimum",
      "no_matching_medication_recorded",
    ];
    for (const code of exclusions) expect(exclusionReason(code)).not.toBe(code);
  });

  it("translate every review flag and input field in the research rule files", () => {
    for (const flag of new Set(RULES.flatMap((item) => item.review_flags))) expect(reviewFlag(flag), flag).not.toBe(flag);
    const fields = new Set(RULES.flatMap((item) => item.required_inputs).filter((field) => !BACKEND_ALIASES.has(field)));
    for (const field of [...fields, "diabetes_status", "hypertension_status", "date_of_birth", "pregnancy_status"]) {
      expect(fieldLabel(field), field).not.toBe(field);
    }
  });

  it("show an unknown code as it is instead of hiding it", () => {
    expect(reviewReason("new_reason")).toBe("new_reason");
    expect(fieldLabel("new_field")).toBe("new_field");
    expect(reviewStatusLabel("clinician_approved")).toBe("clinician_approved");
    expect(reviewStatusLabel("draft_not_clinician_reviewed")).toBe("مسودة لم يراجعها طبيب");
  });

  it("count tests in correct Arabic", () => {
    expect([0, 1, 2, 3, 11].map(testCount)).toEqual(["لا فحوصات", "فحص واحد", "فحصان", "3 فحوصات", "11 فحصاً"]);
  });
});

describe("screening grouping", () => {
  it("puts a test with any candidate rule in the candidate group", () => {
    expect(testGroup(test(["DM05"], ["DM07"]))).toBe("candidate");
    expect(testGroup(test([], ["DM01"]))).toBe("needs_information");
    expect(testGroup(test([], []))).toBe("other");
  });

  it("orders rules by status without dropping any", () => {
    const rules = [rule("A", "not_triggered"), rule("B", "needs_information"), rule("C", "candidate"), rule("D", "not_applicable")];
    expect(sortRules(rules).map((item) => item.rule_id)).toEqual(["C", "B", "D", "A"]);
  });

  it("lists each cited source once with every rule that cites it", () => {
    const sources = citedSources([
      test([], [], [rule("DM04", "candidate", ["S01", "S02"]), rule("MED02", "candidate", ["S02"])]),
      test([], [], [rule("DM10", "candidate", ["S02"])]),
    ]);
    expect(sources.map((source) => [source.source_id, source.rule_ids])).toEqual([
      ["S01", ["DM04"]],
      ["S02", ["DM04", "MED02", "DM10"]],
    ]);
  });
});

describe("screening record validation", () => {
  const record = { test_name: "HbA1c", completed_on: "2026-01-10", result: "", unit: "", notes: "" };

  it("requires a name and a completion date", () => {
    const errors = validateScreeningRecord({ ...record, test_name: "  ", completed_on: "" }, null);
    expect(Object.keys(errors).sort()).toEqual(["completed_on", "test_name"]);
  });

  it("rejects a unit without a result and a date before birth", () => {
    expect(validateScreeningRecord({ ...record, unit: "%" }, null).unit).toBeDefined();
    expect(validateScreeningRecord(record, "2026-02-01").completed_on).toBeDefined();
  });

  it("never judges the result itself", () => {
    for (const result of ["7.1", "999", "مرتفع", "< 0.5"]) {
      expect(validateScreeningRecord({ ...record, result, unit: "%" }, null)).toEqual({});
    }
  });

  it("translates the backend's record errors", () => {
    const errors = parseFieldErrors([
      { loc: ["body", "unit"], msg: "Value error, A unit requires a result" },
      { loc: ["body", "test_id"], msg: "'x' is not a known screening test" },
    ]);
    expect(errors.unit).toBe("يلزم إدخال النتيجة قبل الوحدة.");
    expect(errors.test_id).toBe("هذا الفحص غير موجود في القائمة.");
  });
});

describe("screening API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads the summary from the proxied backend path", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ patient_id: 3, tests: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.getScreeningSummary(3)).resolves.toMatchObject({ patient_id: 3 });
    expect(fetchMock).toHaveBeenCalledWith("/api/patients/3/screening-summary", expect.anything());
  });

  it("sends a new record as JSON and reports a missing patient", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: "Patient 9 not found" }), { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);
    const input = { test_id: "hba1c", test_name: "HbA1c", completed_on: "2026-01-10", result: null, unit: null, source: "lab_report" as const, notes: null };

    await expect(api.addScreeningRecord(9, input)).rejects.toMatchObject({ kind: "not_found" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/patients/9/screening-records",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
    expect(errorFromResponse(404, undefined).kind).toBe("not_found");
  });
});

describe("screening UI safety", () => {
  const uiFiles = ["components", "screens"].flatMap((folder) =>
    readdirSync(join(__dirname, "..", folder)).map((file) => join(__dirname, "..", folder, file)),
  );
  const screeningFiles = uiFiles.filter((file) => /screening|home/.test(file));

  it("never renders the draft rules' schedule text", () => {
    for (const file of uiFiles) expect(readFileSync(file, "utf-8"), file).not.toContain("schedule_text_ar");
  });

  it("shows no due, overdue, or next-appointment wording on real screening screens", () => {
    for (const file of screeningFiles) expect(readFileSync(file, "utf-8"), file).not.toMatch(/مستحق|متأخر|الموعد القادم|خطوتك التالية/);
  });
});
