// Arabic wording for the screening API's codes. Every rule is an unreviewed draft:
// no label may present one as an approved recommendation, a due date, or a delay.
// An unknown code is shown as it is, never hidden.

import type { MissingReason, RecordSource, RuleStatus, ScreeningTestSummary, SourceReference } from "../api/types";

export type Tone = "blue" | "amber" | "green" | "neutral";

export const RULE_STATUS: Record<RuleStatus, { label: string; tone: Tone; detail: string }> = {
  candidate: {
    label: "قد تنطبق · للمراجعة",
    tone: "blue",
    detail: "تنطبق شروط هذه القاعدة المسودة على بياناتك المسجّلة. ليست توصية طبية معتمدة، ويُنصح بمناقشتها مع الطبيب.",
  },
  needs_information: {
    label: "تحتاج معلومات",
    tone: "amber",
    detail: "لا يمكن معرفة إن كانت القاعدة تنطبق قبل استكمال المعلومات الناقصة.",
  },
  not_applicable: {
    label: "لا تنطبق حالياً",
    tone: "neutral",
    detail: "بحسب بياناتك المسجّلة. لا يعني ذلك أن الفحص غير لازم.",
  },
  not_triggered: {
    label: "لا دواء مرتبط مسجّل",
    tone: "neutral",
    detail: "تخص القاعدة أدوية غير مسجّلة في ملفك. قد تكون قائمة الأدوية ناقصة.",
  },
};

const EXCLUSION_REASONS: Record<string, string> = {
  diabetes_not_diagnosed: "السكري غير مشخّص في ملفك.",
  hypertension_not_diagnosed: "ضغط الدم غير مشخّص في ملفك.",
  diabetes_diagnosed: "القاعدة لمن ليس لديهم سكري، والسكري مشخّص في ملفك.",
  diabetes_type_not_covered: "القاعدة لا تشمل نوع السكري المسجّل.",
  diabetes_duration_below_minimum: "لم تمضِ على تشخيص السكري المدة التي تذكرها القاعدة.",
  age_below_minimum: "العمر المسجّل أقل مما تذكره القاعدة.",
  no_matching_medication_recorded: "لا يوجد في ملفك دواء تخصه هذه القاعدة.",
};

const REVIEW_REASONS: Record<string, string> = {
  draft_rules: "القواعد مسودة لم يراجعها طبيب.",
  draft_test_grouping: "جمع هذه القواعد في فحص واحد لم يُراجَع بعد.",
  source_conflict: "توجد اختلافات بين المصادر.",
  mixed_rule_statuses: "بعض القواعد قد تنطبق وبعضها يحتاج معلومات.",
  possible_overlap: "قد يتداخل مع فحوصات أخرى، ولم يُدمج معها.",
  history_not_used_by_rules: "سجلك لهذا الفحص لم يُستخدم في تقييم القواعد.",
  history_mapping_pending_review: "ربط سجلك بالقواعد بانتظار المراجعة الطبية.",
  ambiguous_history_mapping: "علاقة السجل ببعض القواعد غير محسومة.",
  multiple_records_same_date: "يوجد أكثر من سجل في اليوم نفسه.",
};

const REVIEW_FLAGS: Record<string, string> = {
  individual_target_required: "يحتاج هدفاً فردياً يحدده الطبيب.",
  renal_disease_exception: "يختلف المسار عند وجود مرض كلوي.",
  pregnancy_requires_separate_plan: "الحمل يحتاج خطة منفصلة.",
  source_conflict: "المصادر مختلفة.",
  clinician_interval_required: "يحدد الطبيب التوقيت.",
  high_risk_exception: "يختلف المسار عند ارتفاع الخطورة.",
  legacy_2013: "مصدره دليل قديم (2013).",
  test_specific_interval_unconfirmed: "تكرار هذا الفحص بعينه غير مؤكد.",
  interval_not_specified: "المصدر لا يحدد مدة.",
  long_term_not_numerically_defined: "«الاستخدام الطويل» غير محدد بمدة.",
  diabetes_context: "تخص سياق مرضى السكري.",
  early_monitoring_not_covered: "لا تشمل المتابعة المبكرة بعد بدء الدواء.",
  not_routine_screening: "ليس فحصاً دورياً للجميع.",
  clinic_plan_required: "يتبع خطة العيادة.",
  indication_specific: "يخص استطباباً محدداً للدواء.",
  phase_boundary_review: "حدود المراحل تحتاج مراجعة.",
  baseline_not_covered_by_this_table: "القياس الأساسي غير مشمول.",
};

const FIELDS: Record<string, string> = {
  date_of_birth: "تاريخ الميلاد",
  diabetes_status: "حالة السكري",
  diabetes_type: "نوع السكري",
  diabetes_diagnosis_date: "تاريخ تشخيص السكري",
  hypertension_status: "حالة ضغط الدم",
  medication_start_date: "تاريخ بدء الدواء",
  last_hba1c_date: "تاريخ آخر تحليل سكر تراكمي",
  hba1c_at_individual_target: "هل السكر التراكمي ضمن الهدف الذي حدده الطبيب",
  last_uacr_date: "تاريخ آخر تحليل UACR",
  last_egfr_date: "تاريخ آخر تحليل وظائف الكلى",
  known_kidney_disease: "وجود مرض كلوي معروف",
  previous_eye_exam: "إجراء فحص عين سابق",
  last_eye_exam_date: "تاريخ آخر فحص عين",
  retinopathy_status: "حالة شبكية العين",
  pregnancy_status: "حالة الحمل",
  clinician_next_due_date: "قرار الطبيب بشأن الحاجة والتوقيت",
  clinic_next_due_date: "خطة العيادة للمتابعة",
  encounter_date: "تاريخ زيارة الرعاية الأولية",
  last_foot_exam_date: "تاريخ آخر فحص للقدم",
  foot_ulcer_history: "تاريخ قرح القدم",
  high_risk_foot_status: "تقييم خطورة القدم",
  last_neuropathy_exam_date: "تاريخ آخر تقييم للأعصاب",
  bp_control_status: "تقييم الطبيب لانضباط الضغط",
  stable_since: "منذ متى الضغط مستقر",
  last_review_date: "تاريخ آخر مراجعة",
  medication_change_date: "تاريخ تغيير العلاج",
  last_electrolytes_date: "تاريخ آخر تحليل أملاح",
  last_lipid_profile_date: "تاريخ آخر ملف دهون",
  last_lipid_date: "تاريخ آخر ملف دهون",
  last_fasting_glucose_date: "تاريخ آخر سكر صائم",
  last_urine_assessment_date: "تاريخ آخر تحليل بول",
  last_ecg_date: "تاريخ آخر تخطيط قلب",
  anemia_status: "وجود فقر دم",
  neuropathy_status: "وجود اعتلال أعصاب",
  last_b12_date: "تاريخ آخر تحليل B12",
  renal_status: "تقييم الطبيب لوظائف الكلى",
  baseline_creatinine: "قياس الكرياتينين الأساسي",
  baseline_potassium: "قياس البوتاسيوم الأساسي",
  last_creatinine_date: "تاريخ آخر تحليل كرياتينين",
  last_potassium_date: "تاريخ آخر تحليل بوتاسيوم",
  last_uric_acid_date: "تاريخ آخر تحليل حمض اليوريك",
  last_calcium_date: "تاريخ آخر تحليل كالسيوم",
  last_glucose_date: "تاريخ آخر تحليل سكر",
  medication_start_or_change_date: "تاريخ بدء الدواء أو تعديل جرعته",
  planned_start_or_dose_increase: "هل يُخطط لبدء الدواء أو زيادة جرعته",
  last_alt_date: "تاريخ آخر تحليل ALT",
  last_ast_date: "تاريخ آخر تحليل AST",
  muscle_symptoms: "وجود أعراض عضلية",
  last_ck_date: "تاريخ آخر تحليل CK",
  last_inr_date: "تاريخ آخر تحليل INR",
  inr_stability_since: "منذ متى نتائج INR مستقرة",
  dose_stability_since: "منذ متى الجرعة ثابتة",
  clinical_stability: "تقييم الطبيب للاستقرار",
  change_type: "نوع التغيير في العلاج",
  change_date: "تاريخ التغيير في العلاج",
  medication_indication: "سبب وصف الدواء",
  last_cbc_date: "تاريخ آخر صورة دم",
  last_lft_date: "تاريخ آخر وظائف كبد",
  last_renal_date: "تاريخ آخر وظائف كلى",
};

export const MISSING_REASONS: Record<MissingReason, string> = {
  unknown: "غير مسجّل في ملفك",
  not_collected: "لا يجمعه التطبيق بعد",
};

export const RECORD_SOURCES: Record<RecordSource, string> = {
  patient_reported: "أدخلتُه بنفسي",
  lab_report: "تقرير مختبر",
  clinician_entered: "أدخله الطبيب",
  device: "جهاز قياس",
};

const TRACKS: Record<string, string> = { diabetes: "السكري", hypertension: "ضغط الدم", medication: "الأدوية" };

const REVIEW_STATUSES: Record<string, string> = {
  draft_not_clinician_reviewed: "مسودة لم يراجعها طبيب",
  pending_review: "بانتظار المراجعة الطبية",
};

const lookup = (labels: Record<string, string>, code: string) => labels[code] ?? code;

export const exclusionReason = (code: string) => lookup(EXCLUSION_REASONS, code);
export const reviewReason = (code: string) => lookup(REVIEW_REASONS, code);
export const reviewFlag = (code: string) => lookup(REVIEW_FLAGS, code);
export const fieldLabel = (code: string) => lookup(FIELDS, code);
export const trackLabel = (code: string) => lookup(TRACKS, code);
export const reviewStatusLabel = (code: string) => lookup(REVIEW_STATUSES, code);

export function testCount(count: number): string {
  if (count === 0) return "لا فحوصات";
  if (count === 1) return "فحص واحد";
  if (count === 2) return "فحصان";
  return count <= 10 ? `${count} فحوصات` : `${count} فحصاً`;
}

export type TestGroup = "candidate" | "needs_information" | "other";

export function testGroup(test: ScreeningTestSummary): TestGroup {
  if (test.candidate_rule_ids.length > 0) return "candidate";
  if (test.needs_information_rule_ids.length > 0) return "needs_information";
  return "other";
}

const STATUS_ORDER: RuleStatus[] = ["candidate", "needs_information", "not_applicable", "not_triggered"];

export function sortRules<T extends { status: RuleStatus }>(rules: T[]): T[] {
  return [...rules].sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status));
}

export interface CitedSource extends Omit<SourceReference, "locator"> {
  rule_ids: string[];
}

/** Every source the rules cite, once each, with the rules that cite it. */
export function citedSources(tests: ScreeningTestSummary[]): CitedSource[] {
  const sources = new Map<string, CitedSource>();
  for (const rule of tests.flatMap((test) => test.rules)) {
    for (const source of rule.sources) {
      const { source_id, title, issuer, url, version, limitation_ar } = source;
      const entry = sources.get(source_id) ?? { source_id, title, issuer, url, version, limitation_ar, rule_ids: [] };
      if (!entry.rule_ids.includes(rule.rule_id)) entry.rule_ids.push(rule.rule_id);
      sources.set(source_id, entry);
    }
  }
  return [...sources.values()].sort((a, b) => a.source_id.localeCompare(b.source_id, "en", { numeric: true }));
}
