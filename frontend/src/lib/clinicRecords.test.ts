/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { errorFromResponse } from "../api/errors";
import { RECORD_SOURCES } from "./screening";

const SRC = join(__dirname, "..");
const read = (path: string) => readFileSync(join(SRC, path), "utf-8");

describe("clinic screening results API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads and writes through the clinic-patient link, never a patient id", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const result = { test_id: "hba1c", test_name: "HbA1c", completed_on: "2026-03-02", result: "7.3", unit: "%", notes: null };

    await api.getClinicPatient(1, 4);
    await api.listClinicPatientRecords(1, 4);
    await api.addClinicPatientRecord(1, 4, result);

    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([path, init]) => [path, init.method ?? "GET"])).toEqual([
      ["/api/clinics/1/patients/4", "GET"],
      ["/api/clinics/1/patients/4/screening-records", "GET"],
      ["/api/clinics/1/patients/4/screening-records", "POST"],
    ]);
    const sent = JSON.parse(String(calls[2][1].body));
    expect(sent).toEqual(result);
    expect(sent).not.toHaveProperty("source");
    expect(sent).not.toHaveProperty("patient_id");
  });

  it("explains a refused duplicate without suggesting an edit", () => {
    const duplicate = errorFromResponse(409, { detail: "An identical record already exists for this patient (record 7)" });
    expect(duplicate.kind).toBe("conflict");
    expect(duplicate.message).toBe("هذه النتيجة مسجّلة مسبقاً بالقيم نفسها، فلم تُحفظ مرة ثانية.");
    expect(errorFromResponse(409, { detail: "Patient 2 already has 'metformin'." }).message).toContain("يمكن تعديل السجل الحالي");
  });

  it("names the clinician-entered source in Arabic", () => {
    expect(RECORD_SOURCES.clinician_entered).toBe("أدخله الطبيب");
  });
});

describe("clinic results screens", () => {
  it("open the patient page only inside the clinic workspace", () => {
    expect(read("App.tsx")).toContain('path="/clinic/patients/:linkId"');
  });

  it("let the clinic form fix the source instead of offering a choice", () => {
    const form = read("components/screening.tsx");
    expect(form).toContain('target.kind === "clinic" ? (');
    expect(form).toContain("يحدده الخادم ولا يمكن تغييره");
    expect(form).toMatch(/api\.addClinicPatientRecord\(target\.clinicId, target\.linkId, fields\)/);
  });

  it("never call results or tests approved or validated", () => {
    for (const file of ["screens/clinic.tsx", "components/screening.tsx"]) {
      expect(read(file), file).not.toMatch(/المعتمدة في التطبيق|نتيجة معتمدة|تم التحقق منها سريرياً|مُعتمدة سريرياً/);
    }
  });
});
