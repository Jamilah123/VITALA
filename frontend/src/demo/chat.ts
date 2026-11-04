// DEMO ONLY. Fixed replies chosen by button. There is no model, no matching on
// what the user typed, and no network call: typed text is never sent anywhere.

export interface CannedTopic {
  id: string;
  label: string;
  reply: string;
}

export const CHAT_INTRO =
  "هذه معاينة لشكل مساعد Vitala. يمكن اختيار أحد الأسئلة أدناه لرؤية رد مكتوب مسبقاً عن الشخصية التجريبية نورة.";

export const CANNED_TOPICS: CannedTopic[] = [
  {
    id: "checks",
    label: "فحوصاتي",
    reply:
      "هذا رد تجريبي لا يقرأ ملفك. الفحوصات التي قد تنطبق على ملفك، وفق قواعد مسودة لم يراجعها طبيب، معروضة في صفحة «الفحوصات» دون مواعيد.",
  },
  {
    id: "hba1c",
    label: "لماذا HbA1c؟",
    reply: "يعكس HbA1c متوسط السكر في آخر 3 أشهر، ويساعد الطبيب على معرفة هل الخطة تعمل. يظهر في الخريطة التجريبية لأن نورة سجّلت إصابتها بالسكري.",
  },
  {
    id: "activity",
    label: "هدفي للنشاط",
    reply: "الهدف التجريبي لنورة 150 دقيقة أسبوعياً، وقد أنجزت منها 98 دقيقة. يمكن للطبيب تعديل الهدف.",
  },
];

export const FREE_TEXT_REPLY =
  "لا يمكن الإجابة عن الأسئلة المكتوبة: المساعد الذكي غير متاح بعد، ولم يُقرأ سؤالك أو يُرسل إلى أي جهة. إذا كان سؤالك عن حالتك الصحية فيُنصح بمراجعة الطبيب، وعند وجود أعراض طارئة يجب الاتصال بالطوارئ فوراً.";
