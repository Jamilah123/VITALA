// DEMO ONLY. Fixed replies chosen by button. There is no model, no matching on
// what the user typed, and no network call: typed text is never sent anywhere.

export interface CannedTopic {
  id: string;
  label: string;
  reply: string;
}

export const CHAT_INTRO =
  "هذه معاينة لشكل مساعد Vitala. اختاري أحد الأسئلة أدناه لرؤية رد مكتوب مسبقاً عن الشخصية التجريبية نورة.";

export const CANNED_TOPICS: CannedTopic[] = [
  {
    id: "checks",
    label: "فحوصاتي",
    reply:
      "في الخريطة التجريبية لنورة 5 فحوصات: السكري التراكمي مستحق بعد 5 أيام، وفحص العين متأخر بأسبوعين، وقياس الضغط مستحق الآن، ووظائف الكلى بعد شهرين، وملف الدهون مكتمل.",
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
  "لا يمكن الإجابة عن الأسئلة المكتوبة: المساعد الذكي غير متاح بعد، ولم يُقرأ سؤالك أو يُرسل إلى أي جهة. إذا كان سؤالك عن حالتك الصحية فراجعي طبيبك، وإذا كانت لديك أعراض طارئة فاتصلي بالطوارئ فوراً.";
