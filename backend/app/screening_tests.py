"""Explicit grouping of draft rules into clinically equivalent tests.

Every grouping and overlap below is an unreviewed mapping. Rules are grouped
only when listed together here, never because their names look alike. Tests
that only partly overlap stay separate and are listed in POSSIBLE_OVERLAPS.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.rules import Rule


@dataclass(frozen=True)
class ScreeningTest:
    name_ar: str
    rule_ids: tuple[str, ...]


SCREENING_TESTS: dict[str, ScreeningTest] = {
    "hba1c": ScreeningTest("السكر التراكمي", ("DM01", "DM02")),
    "uacr": ScreeningTest("نسبة ألبومين البول إلى الكرياتينين UACR", ("DM03",)),
    "egfr": ScreeningTest("وظائف الكلى / eGFR", ("DM04", "HTN04", "MED02")),
    "eye_exam": ScreeningTest("فحص العين", ("DM05", "DM06", "DM07")),
    "blood_pressure": ScreeningTest("قياس ضغط الدم", ("DM08",)),
    "foot_exam": ScreeningTest("الفحص السريري للقدم", ("DM09",)),
    "neuropathy_exam": ScreeningTest("تقييم الاعتلال العصبي الطرفي", ("DM10",)),
    "bp_followup": ScreeningTest("متابعة الضغط", ("HTN01", "HTN02")),
    "annual_htn_review": ScreeningTest("التقييم الشامل للضغط", ("HTN03",)),
    "electrolytes": ScreeningTest("الصوديوم والبوتاسيوم", ("HTN05",)),
    "lipid_profile": ScreeningTest("ملف الدهون", ("HTN06", "MED07", "MED08")),
    "fasting_glucose": ScreeningTest("سكر الدم الصائم", ("HTN07",)),
    "urine_assessment": ScreeningTest("تحليل البول وتقييم الألبومين", ("HTN08",)),
    "ecg": ScreeningTest("تخطيط القلب ECG", ("HTN09",)),
    "vitamin_b12": ScreeningTest("فيتامين B12", ("MED01",)),
    "renal_potassium": ScreeningTest("الكرياتينين والبوتاسيوم", ("MED03", "MED04", "MED05")),
    "thiazide_labs": ScreeningTest("الأملاح وحمض اليوريك والكالسيوم والسكر الصائم", ("MED06",)),
    "liver_enzymes": ScreeningTest("ALT وAST", ("MED09",)),
    "ck": ScreeningTest("CK / CPK", ("MED10",)),
    "inr": ScreeningTest("INR", ("MED11", "MED12", "MED13")),
    "cbc_lft_renal": ScreeningTest("صورة الدم ووظائف الكبد والكلى", ("MED14",)),
}

RULE_TESTS: dict[str, str] = {rule_id: test_id for test_id, test in SCREENING_TESTS.items() for rule_id in test.rule_ids}

POSSIBLE_OVERLAPS: tuple[tuple[str, str], ...] = (
    ("egfr", "renal_potassium"),
    ("egfr", "cbc_lft_renal"),
    ("electrolytes", "renal_potassium"),
    ("electrolytes", "thiazide_labs"),
    ("fasting_glucose", "thiazide_labs"),
    ("liver_enzymes", "cbc_lft_renal"),
    ("uacr", "urine_assessment"),
    ("foot_exam", "neuropathy_exam"),
    ("blood_pressure", "bp_followup"),
    ("annual_htn_review", "egfr"),
    ("annual_htn_review", "electrolytes"),
    ("annual_htn_review", "lipid_profile"),
    ("annual_htn_review", "fasting_glucose"),
    ("annual_htn_review", "urine_assessment"),
    ("annual_htn_review", "ecg"),
)


def possible_overlaps(test_id: str) -> list[str]:
    return sorted({other for pair in POSSIBLE_OVERLAPS if test_id in pair for other in pair if other != test_id})


def check_test_mapping(rules: Iterable[Rule]) -> None:
    rule_ids = sorted(rule.id for rule in rules)
    grouped = sorted(rule_id for test in SCREENING_TESTS.values() for rule_id in test.rule_ids)
    if grouped != rule_ids:
        raise ValueError(f"Every rule must belong to exactly one screening test. Grouped: {grouped}. Rules: {rule_ids}")
    unknown = sorted({test_id for pair in POSSIBLE_OVERLAPS for test_id in pair} - SCREENING_TESTS.keys())
    if unknown:
        raise ValueError(f"POSSIBLE_OVERLAPS references unknown tests: {unknown}")
