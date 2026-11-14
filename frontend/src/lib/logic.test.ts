import { describe, expect, it } from "vitest";
import { errorFromResponse, parseFieldErrors } from "../api/errors";
import { ageFrom, formatDate, isValidIsoDate, todayIso } from "./dates";
import { computeBmi, conditionFields, draftToUpdate, type ProfileDraft } from "./profile";
import { parseNumber, validateBasics, validateBloodPressure, validateMedication } from "./validation";

describe("dates", () => {
  it("uses the local day, not the UTC day", () => {
    expect(todayIso(new Date(2026, 10, 1, 0, 30))).toBe("2026-11-01");
  });

  it("formats in the Gregorian calendar with Western digits", () => {
    expect(formatDate("1995-05-15")).toBe("15 مايو 1995");
  });

  it("rejects impossible dates", () => {
    expect(isValidIsoDate("2026-02-30")).toBe(false);
    expect(isValidIsoDate("2026-02-28")).toBe(true);
  });

  it("counts age only after the birthday", () => {
    expect(ageFrom("1995-05-15", new Date(2026, 4, 14))).toBe(30);
    expect(ageFrom("1995-05-15", new Date(2026, 4, 15))).toBe(31);
  });
});

describe("parseNumber", () => {
  it("reads Arabic digits and the Arabic decimal mark", () => {
    expect(parseNumber("١٧٥")).toBe(175);
    expect(parseNumber("٧٫٤")).toBe(7.4);
    expect(parseNumber("۱۲")).toBe(12);
  });

  it("rejects anything that is not a plain positive number", () => {
    for (const text of ["", "abc", "-5", "1e3", "12 3"]) expect(parseNumber(text)).toBeNull();
  });
});

describe("conditions", () => {
  it("clears the type and dates when leaving diagnosed", () => {
    expect(conditionFields("unknown", "not_diagnosed")).toEqual({
      diabetes_status: "unknown",
      hypertension_status: "not_diagnosed",
      diabetes_type: "unknown",
      diabetes_diagnosis_date: null,
      hypertension_diagnosis_date: null,
    });
  });

  it("leaves stored details alone while still diagnosed", () => {
    expect(conditionFields("diagnosed", "diagnosed")).toEqual({
      diabetes_status: "diagnosed",
      hypertension_status: "diagnosed",
    });
  });

  it("sends empty dates as null and lets clearing win over a stale draft", () => {
    const draft: ProfileDraft = {
      date_of_birth: "",
      sex: "female",
      diabetes_status: "unknown",
      diabetes_type: "type_2",
      diabetes_diagnosis_date: "2020-01-01",
      hypertension_status: "diagnosed",
      hypertension_diagnosis_date: "",
    };
    expect(draftToUpdate(draft)).toMatchObject({
      date_of_birth: null,
      diabetes_type: "unknown",
      diabetes_diagnosis_date: null,
      hypertension_diagnosis_date: null,
    });
  });
});

describe("BMI", () => {
  it("matches the PDF example", () => {
    expect(computeBmi(175, 72, 31)).toEqual({ value: 23.5, category: "ضمن النطاق الطبيعي" });
  });

  it("gives no adult category for children or an unknown age", () => {
    expect(computeBmi(175, 72, 12).category).toBeNull();
    expect(computeBmi(175, 72, null).category).toBeNull();
  });
});

describe("form validation", () => {
  it("leaves optional basics optional", () => {
    expect(validateBasics({ dateOfBirth: "", height: "", weight: "" })).toEqual({});
  });

  it("rejects a future birth date and out-of-range measurements", () => {
    const errors = validateBasics({ dateOfBirth: "2999-01-01", height: "20", weight: "900" });
    expect(Object.keys(errors).sort()).toEqual(["date_of_birth", "height", "weight"]);
  });

  const medication = { medication_id: "metformin", dose_text: "500", start_date: "", last_dose_change_date: "" };

  it("requires a medication and a dose", () => {
    const errors = validateMedication({ ...medication, medication_id: "", dose_text: "   " }, null);
    expect(Object.keys(errors).sort()).toEqual(["dose_text", "medication_id"]);
  });

  it("catches a duplicate medication", () => {
    expect(validateMedication(medication, null, ["metformin"]).medication_id).toBeDefined();
  });

  it("applies the backend's date ordering rules", () => {
    expect(
      validateMedication({ ...medication, start_date: "2020-01-01", last_dose_change_date: "2019-01-01" }, null)
        .last_dose_change_date,
    ).toBeDefined();
    expect(validateMedication({ ...medication, start_date: "1990-01-01" }, "1995-01-01").start_date).toBeDefined();
  });

  it("requires diastolic below systolic", () => {
    expect(validateBloodPressure("120", "130").diastolic).toBeDefined();
    expect(validateBloodPressure("120", "80")).toEqual({});
  });
});

describe("API errors", () => {
  it("translates backend field errors", () => {
    const errors = parseFieldErrors([
      { loc: ["body", "date_of_birth"], msg: "Date of birth cannot be in the future" },
      { loc: ["body", "last_dose_change_date"], msg: "Last dose change cannot be before the start date" },
      { loc: ["body", "sex"], msg: "Input should be 'male', 'female' or 'unknown'" },
    ]);
    expect(errors.date_of_birth).toContain("المستقبل");
    expect(errors.last_dose_change_date).toContain("تاريخ البدء");
    expect(errors.sex).toBe("قيمة غير صالحة.");
  });

  it("treats a bodyless 5xx from the proxy as the backend being down", () => {
    expect(errorFromResponse(500, undefined).kind).toBe("network");
    expect(errorFromResponse(500, { detail: "boom" }).kind).toBe("server");
  });

  it("classifies 404 and 409", () => {
    expect(errorFromResponse(404, { detail: "x" }).kind).toBe("not_found");
    expect(errorFromResponse(409, { detail: "x" }).kind).toBe("conflict");
  });
});
