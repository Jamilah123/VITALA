/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { PreAppointmentSummary, ScreeningRecord, ScreeningTestSummary } from "../api/types";
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
} from "./clinicSummary";

const SRC = join(__dirname, "..");
const read = (path: string) => readFileSync(join(SRC, path), "utf-8");
const sourceFiles = (folder: string): string[] =>
  readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(name) && !name.endsWith(".test.ts") ? [path] : [];
  });

function record(id: number, test_id: string, completed_on: string): ScreeningRecord {
  return { id, patient_id: 1, test_id, test_name: test_id, completed_on, result: null, unit: null, source: "lab_report", notes: null };
}

function test(test_id: string, name_ar: string, records: ScreeningRecord[], candidates: string[] = [], undecided: string[] = []): ScreeningTestSummary {
  return {
    test_id,
    name_ar,
    mapping_status: "draft_not_clinician_reviewed",
    recorded_tests: records,
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
    rules: [],
  };
}

function summary(tests: ScreeningTestSummary[], unmapped: ScreeningRecord[] = []): PreAppointmentSummary {
  return { screening: { tests, unmapped_records: unmapped } } as unknown as PreAppointmentSummary;
}

describe("summary facts", () => {
  it("never shows a missing value as absent", () => {
    for (const fact of [conditionFact("unknown"), yesNoFact("unknown"), smokingFact("unknown"), sexFact("unknown"), ageFact(null), measureFact(null, "سم"), dateFact(null), diabetesTypeFact("unknown")]) {
      expect(fact).toEqual({ text: "غير معروف", state: "unknown" });
    }
  });

  it("shows only explicit negatives as absent", () => {
    expect(conditionFact("not_diagnosed")).toEqual({ text: "غير مشخّص", state: "absent" });
    expect(yesNoFact("no")).toEqual({ text: "لا", state: "absent" });
    expect(smokingFact("never").state).toBe("absent");
  });

  it("shows recorded values as documented, including zero", () => {
    expect(conditionFact("diagnosed").state).toBe("documented");
    expect(yesNoFact("yes").state).toBe("documented");
    expect(smokingFact("former")).toEqual({ text: "مدخّن سابقاً", state: "documented" });
    expect(measureFact(0, "دقيقة أسبوعياً")).toEqual({ text: "0 دقيقة أسبوعياً", state: "documented" });
    expect(diabetesTypeFact("type_2")).toEqual({ text: "النوع الثاني", state: "documented" });
    expect(ageFact("1985-03-15").text).toContain("15 مارس 1985");
  });
});

describe("summary screening sections", () => {
  it("lists every record newest first, including unmapped ones, with the test name", () => {
    const records = allRecords(
      summary(
        [test("hba1c", "السكر التراكمي", [record(1, "hba1c", "2025-01-10"), record(3, "hba1c", "2026-03-02")]), test("egfr", "وظائف الكلى", [record(2, "egfr", "2025-06-01")])],
        [record(4, "retired_test", "2026-01-01")],
      ),
    );

    expect(records.map((item) => item.id)).toEqual([3, 4, 2, 1]);
    expect(records.map((item) => item.test_name_ar)).toEqual(["السكر التراكمي", "retired_test", "وظائف الكلى", "السكر التراكمي"]);
  });

  it("splits tests into candidates, undecided, and the rest", () => {
    const groups = screeningGroups(summary([test("a", "أ", [], ["R1"]), test("b", "ب", [], [], ["R2"]), test("c", "ج", []), test("d", "د", [], ["R3"], ["R4"])]));

    expect(groups.candidates.map((item) => item.test_id)).toEqual(["a", "d"]);
    expect(groups.undecided.map((item) => item.test_id)).toEqual(["b"]);
    expect(groups.otherCount).toBe(1);
  });
});

describe("doctor access lives only in the clinic workspace", () => {
  const routes = read("App.tsx");

  it("removed the standalone doctor page and every link to it", () => {
    expect(routes).not.toMatch(/path="\/doctor/);
    for (const file of sourceFiles(SRC)) {
      const text = readFileSync(file, "utf-8");
      expect(text, file).not.toMatch(/["'`]\/doctor["'`/]|DoctorView|DOCTOR_CHECKLIST|doctorConfirmed/);
    }
  });

  it("opens appointments and summaries only under /clinic", () => {
    const paths = [...routes.matchAll(/path="([^"]+)"/g)].map((match) => match[1]);
    expect(paths).toContain("/clinic/appointments/:appointmentId");
    expect(paths).toContain("/clinic/appointments/:appointmentId/summary");
    for (const path of paths.filter((item) => /appointment|summary/.test(item))) expect(path.startsWith("/clinic/")).toBe(true);
  });

  it("clinic screens use no demo data, so no wearable values are invented", () => {
    const clinicScreen = read("screens/clinic.tsx");
    expect(clinicScreen).not.toMatch(/from "\.\.\/demo/);
    expect(clinicScreen).toContain("لا توجد بيانات متاحة");
    expect(clinicScreen).not.toMatch(/مستحق|متأخر/);
  });
});

describe("summary API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads the appointment and its summary from clinic-scoped paths", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.getAppointment(1, 5);
    await api.getPreAppointmentSummary(1, 5);

    const calls = fetchMock.mock.calls as unknown as [string][];
    expect(calls.map(([path]) => path)).toEqual(["/api/clinics/1/appointments/5", "/api/clinics/1/appointments/5/summary"]);
  });

  it("reports another clinic's appointment as not found", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Appointment 9 not found in clinic 1" }), { status: 404 })));

    await expect(api.getPreAppointmentSummary(1, 9)).rejects.toMatchObject({ kind: "not_found" });
  });
});

describe("record labels", () => {
  it("shows the report's own name only when it differs from the catalogue name", async () => {
    const { recordLabel } = await import("./clinicSummary");
    expect(recordLabel("السكر التراكمي", "السكر التراكمي")).toBe("السكر التراكمي");
    expect(recordLabel("السكر التراكمي", "HbA1c")).toBe("السكر التراكمي · HbA1c");
  });
});
