# VITALA — بيانات السكري والضغط ومراقبة الأدوية

تاريخ الجمع: 2026-11-01. نسخة بحثية 0.1.0.

النطاق: فحوصات متابعة السكري والضغط فقط، إضافة إلى مراقبة 10 مواد دوائية مختارة. لا يشمل الكشف العام عن أمراض أخرى أو بناء مسارات علاجها.

## حالة البيانات

هذه سجلات مستخرجة ومنظمة وليست مكتبة قواعد سريرية معتمدة. لم يراجعها طبيب أو صيدلي سريري بعد. حُفظت كل قاعدة كمسودة، وتعطلت جدولة المواعيد تلقائيًا إلى حين اعتمادها. يمكن بناء الواجهات وتجربة عرض البيانات الوهمية الآن.

المصادر كلها مستضافة على موقع وزارة الصحة السعودية. دليل السكري 2021 صادر عن المركز الوطني للسكري بالمجلس الصحي السعودي؛ لم نغيّر جهة إصداره. لا تعني الاستضافة لدى الوزارة أن كل وثيقة هي أحدث إرشاد.

## حصيلة الجمع

- 10 سجلات للسكري، و9 للضغط.
- 10 مواد دوائية و14 قاعدة مراقبة مشتركة حسب الفئة والسياق.
- 11 مقاطع شرح عربية مختصرة للـAI، مع مصادرها؛ جميعها إعادة صياغة وليست اقتباسات.
- النطاقات الزمنية محفوظة كنطاقات؛ لم نخترع موعدًا ثابتًا من عبارة «دوريًا».

## الأدوية المختارة

Metformin, Enalapril, Lisinopril, Losartan, Valsartan, Hydrochlorothiazide, Atorvastatin, Rosuvastatin, Warfarin, Methotrexate.

القائمة مناسبة كبداية عملية، ولا يوجد ادعاء أنها الأكثر استخدامًا إحصائيًا في السعودية. الميثوتريكسات هنا مراقبة دواء ضمن استطبابه المحدد، وليس إضافة مسار مرض ثالث.

## البيانات المستخرجة

| المعرّف | المسار | الفحص / المتابعة | لمن؟ | التوقيت كما استُخلص | المصدر | ملاحظة |
|---|---|---|---|---|---|---|
| DM01 | السكري | السكر التراكمي | سكري مشخص؛ آخر تراكمي ضمن الهدف الفردي المعتمد | كل 6 أشهر | [S01](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/periodic-check-ups-for-diabetic-patients.aspx) — فقرة A1C | لا تفترض أن هدف الجميع 7%. تغير العلاج أو الحالة يحتاج مراجعة. |
| DM02 | السكري | السكر التراكمي | سكري مشخص؛ آخر تراكمي خارج الهدف الفردي المعتمد | كل 3 أشهر | [S01](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/periodic-check-ups-for-diabetic-patients.aspx) — فقرة A1C | مسودة للمراجعة |
| DM03 | السكري | نسبة ألبومين البول إلى الكرياتينين UACR | النوع الثاني، أو النوع الأول بعد مرور 5 سنوات | سنويًا | [S01](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/periodic-check-ups-for-diabetic-patients.aspx) — فقرة ACR | تغيير التكرار عند مرض كلوي يحتاج مسارًا فرديًا. |
| DM04 | السكري | وظائف الكلى بالدم / eGFR | النوع الثاني، أو النوع الأول بعد مرور 5 سنوات | سنويًا في المسار الروتيني | [S01](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/periodic-check-ups-for-diabetic-patients.aspx) — فقرة وظائف الكلى؛ [S02](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf) — PDF p. 82 | S01 يذكر مرتين سنويًا عند مشكلة بالكلى؛ S02 يفرق حسب مرحلة المرض. لا تختزل كل مرض كلوي إلى 6 أشهر. |
| DM05 | السكري | فحص العين الأولي | السكري النوع الثاني | عند التشخيص | [S07](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/impact-of-diabetes-on-eyes.aspx) — إرشادات فحص العين | فحص عند التشخيص ليس موعد إعادة الفحص. |
| DM06 | السكري | فحص العين الأولي | السكري النوع الأول | خلال 5 سنوات من التشخيص | [S07](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/impact-of-diabetes-on-eyes.aspx) — إرشادات فحص العين | خلال 5 سنوات لا تعني منع الفحص قبلها. |
| DM07 | السكري | إعادة فحص العين | سكري مشخص؛ سبق إجراء الفحص | الموعد حسب اعتماد الطبيب؛ اختلاف بين المصادر | [S07](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/impact-of-diabetes-on-eyes.aspx) — الإرشادات: سنويًا؛ [S01](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/periodic-check-ups-for-diabetic-patients.aspx) — العين: التكرار حسب النوع؛ [S02](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf) — PDF p. 80 | اختلافات التكرار محفوظة في conflicts.json. |
| DM08 | السكري | قياس ضغط الدم | سكري مشخص | في كل زيارة للرعاية الأولية | [S01](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/periodic-check-ups-for-diabetic-patients.aspx) — فقرة قياس ضغط الدم | تكرار مرتبط بزيارة، لا بمدة تقويمية. |
| DM09 | السكري | الفحص السريري للقدم | سكري مشخص | مرة سنويًا على الأقل | [S02](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf) — PDF pp. 81–82 | قد يلزم تكرار أقرب عند الخطورة؛ وجود قرحة أو عدوى ليس تذكيرًا روتينيًا. |
| DM10 | السكري | تقييم الاعتلال العصبي الطرفي | النوع الثاني من التشخيص؛ النوع الأول يبدأ التقييم خلال 5 سنوات | سنويًا بعد بدء مسار التقييم | [S02](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf) — PDF p. 81 | قد يتداخل مع فحص القدم؛ لا تضاعف الزيارة. |
| HTN01 | الضغط | متابعة الضغط المستقر | ضغط مشخص؛ استقرار أكثر من 6 أشهر حسب الدليل القديم | كل 3–6 أشهر | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF p. 52 | ليست مدة معتمدة تلقائيًا للنسخة الحالية. |
| HTN02 | الضغط | متابعة بعد بدء علاج الضغط | ضغط مشخص؛ بدء أو تغيير العلاج في سياق الخوارزمية | مراجعة خلال 2–4 أسابيع في الخوارزمية القديمة | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF p. 52 | زيارة متابعة؛ ليست بالضرورة موعد كل تحليل. |
| HTN03 | الضغط | التقييم الشامل للضغط | بالغ غير حامل لديه ضغط مشخص | عند التقييم الأولي وسنويًا حسب المصدر القديم | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 16, 35–36 | السجل التالي يبين فحوصات التقييم؛ لا يلزم إجراء كل فحص سنويًا آليًا. |
| HTN04 | الضغط | كرياتينين الدم وتقدير وظائف الكلى | ضمن تقييم مريض الضغط؛ يحدد الطبيب الحاجة والتكرار | مذكور ضمن تقييم الضغط الأولي/السنوي؛ تكرار الفحص نفسه يحتاج اعتمادًا | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 35–36 | المصدر يدرج أيضًا حمض اليوريك والهيموغلوبين والهيماتوكريت؛ لم تُفعّل كفحوصات دورية للجميع. |
| HTN05 | الضغط | الصوديوم والبوتاسيوم | ضمن تقييم مريض الضغط؛ يحدد الطبيب الحاجة والتكرار | مذكور ضمن تقييم الضغط الأولي/السنوي؛ تكرار الفحص نفسه يحتاج اعتمادًا | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 35–36 | المصدر يدرج أيضًا حمض اليوريك والهيموغلوبين والهيماتوكريت؛ لم تُفعّل كفحوصات دورية للجميع. |
| HTN06 | الضغط | ملف الدهون | ضمن تقييم مريض الضغط؛ يحدد الطبيب الحاجة والتكرار | مذكور ضمن تقييم الضغط الأولي/السنوي؛ تكرار الفحص نفسه يحتاج اعتمادًا | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 35–36 | المصدر يدرج أيضًا حمض اليوريك والهيموغلوبين والهيماتوكريت؛ لم تُفعّل كفحوصات دورية للجميع. |
| HTN07 | الضغط | سكر الدم الصائم | ضمن تقييم مريض الضغط؛ يحدد الطبيب الحاجة والتكرار | مذكور ضمن تقييم الضغط الأولي/السنوي؛ تكرار الفحص نفسه يحتاج اعتمادًا | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 35–36 | المصدر يدرج أيضًا حمض اليوريك والهيموغلوبين والهيماتوكريت؛ لم تُفعّل كفحوصات دورية للجميع. |
| HTN08 | الضغط | تحليل البول وتقييم الألبومين | ضمن تقييم مريض الضغط؛ يحدد الطبيب الحاجة والتكرار | مذكور ضمن تقييم الضغط الأولي/السنوي؛ تكرار الفحص نفسه يحتاج اعتمادًا | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 35–36 | المصدر يدرج أيضًا حمض اليوريك والهيموغلوبين والهيماتوكريت؛ لم تُفعّل كفحوصات دورية للجميع. |
| HTN09 | الضغط | تخطيط القلب ECG | ضمن تقييم مريض الضغط؛ يحدد الطبيب الحاجة والتكرار | مذكور ضمن تقييم الضغط الأولي/السنوي؛ تكرار الفحص نفسه يحتاج اعتمادًا | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 35–36 | المصدر يدرج أيضًا حمض اليوريك والهيموغلوبين والهيماتوكريت؛ لم تُفعّل كفحوصات دورية للجميع. |
| MED01 | دواء | فيتامين B12 | استخدام طويل المدى للميتفورمين؛ خصوصًا مع فقر الدم أو اعتلال الأعصاب | النظر في قياس دوري؛ لا يحدد المصدر عدد أشهر | [S02](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf) — PDF p. 53 | توصية للنظر في الفحص؛ ليست إلزامًا سنويًا لكل مستخدم. |
| MED02 | دواء | وظائف الكلى / eGFR | استخدام الميتفورمين | مراقبة أثناء الاستخدام؛ التوقيت حسب الحالة | [S02](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf) — PDF p. 84 | مسودة للمراجعة |
| MED03 | دواء | كرياتينين الدم والبوتاسيوم | استخدام ACE inhibitor أو ARB أو مدر بول ضمن سياق دليل السكري | قياس أساسي عند بدء المسار | [S02](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf) — PDF p. 83 | الاستدلال من فئة الدواء؛ لا يتجاوز سياق المصدر. |
| MED04 | دواء | وظائف الكلى والبوتاسيوم | سكري مع استخدام ACE inhibitor أو ARB أو مدر بول | سنويًا على الأقل في سياق المصدر | [S03](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Protocol-018.pdf) — PDF p. 26, hypertension item l | ليس هذا جدول الفحوصات المبكرة بعد بدء الدواء أو تغيير الجرعة. |
| MED05 | دواء | الكرياتينين والبوتاسيوم | مستخدم ACE inhibitor أو ARB خارج سياق السكري | مراقبة دورية؛ لا مدة محددة | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF pp. 55–56 | لا تعمم مدة MED04 السنوية على هذه الفئة دون اعتماد. |
| MED06 | دواء | الأملاح وحمض اليوريك والكالسيوم والسكر الصائم | استخدام مدر ثيازيدي | مراقبة دورية مذكورة دون فاصل ثابت | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF p. 55 | مسودة للمراجعة |
| MED07 | دواء | ملف الدهون | سكري مع بدء ستاتين أو تعديل جرعته | بعد 4–12 أسبوعًا | [S03](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Protocol-018.pdf) — PDF p. 26, dyslipidemia item b | المصدر يذكر أيضًا فحصًا عند البدء؛ مدة ضمن نطاق يختاره الطبيب. |
| MED08 | دواء | ملف الدهون | سكري مع استمرار علاج الستاتين | سنويًا بعد متابعة البدء/التعديل | [S03](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Protocol-018.pdf) — PDF p. 26, dyslipidemia item b | فحص فعالية العلاج؛ مختلف عن فحوصات سلامته. |
| MED09 | دواء | ALT وAST | قبل وصف الستاتين أو الزيادة المخطط لها بالجرعة | قبل الوصف أو زيادة الجرعة حسب المصدر القديم | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF p. 69 | لا تعتمد جدول إنزيمات دوري للجميع من هذا المصدر القديم. |
| MED10 | دواء | CK / CPK | مستخدم ستاتين يبلغ عن أعراض عضلية | عند الأعراض؛ ليس فحصًا دوريًا للجميع | [S04](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf) — PDF p. 69 | مسودة للمراجعة |
| MED11 | دواء | INR | وارفارين؛ مستقر طبيًا ونتائج ثابتة دون تغيير جرعة مدة 3 أشهر على الأقل | كل 4–12 أسبوعًا وفق خطة العيادة | [S08](https://www.moh.gov.sa/ministry/mediacenter/publications/documents/protocol-017.pdf) — PDF p. 6, Table 2 and footnote c | لا تختار 12 أسبوعًا افتراضيًا. |
| MED12 | دواء | INR | وارفارين؛ المتابعة غير المستقرة ضمن جدول المصدر | كل 1–2 أسبوع وفق خطة العيادة | [S08](https://www.moh.gov.sa/ministry/mediacenter/publications/documents/protocol-017.pdf) — PDF p. 6, Table 2 | الحالات الحادة وخارج المجال ليست مجرد جدولة روتينية. |
| MED13 | دواء | INR بعد تغيير مؤثر | وارفارين؛ تعديل جرعة أو دواء متداخل أو تغيير آخر مؤثر | خلال أسبوع أو 1–2 أسبوع بحسب نوع التغيير في الجدول | [S08](https://www.moh.gov.sa/ministry/mediacenter/publications/documents/protocol-017.pdf) — PDF p. 6, Table 2 and footnote b | يلزم اختيار الفرع بواسطة العيادة؛ لم تُضمّن خوارزمية تعديل الجرعة. |
| MED14 | دواء | صورة الدم ووظائف الكبد والكلى | ميثوتريكسات في سياق روماتويد البالغين | أول <3 أشهر: كل 2–4 أسابيع؛ 3–6 أشهر: كل 8–12 أسبوعًا؛ >6 أشهر: كل 12 أسبوعًا | [S09](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Protocol-014.pdf) — PDF p. 15, monitoring table | حدود الأشهر وتعديل الجدول عند تغير الجرعة/الحالة تحتاج اعتمادًا. |

## نقاط المراجعة المحددة

- **إعادة فحص العين:** S07 يذكر السنوي؛ S01 يذكر للنوع الثاني سنة إلى سنتين أو أكثر وللنوع الأول مرة أو مرتين سنويًا؛ S02 ص80 يذكر فروعًا تشمل 3 سنوات وعبارة إحالة إذا مضى أكثر من عام. لا دمج تلقائي.
- **تكرار وظائف الكلى عند وجود مرض كلوي:** صياغة عامة مرتين سنويًا في S01، وتفصيل حسب eGFR في S02. يلزم اعتماد فرع الحالة.
- **حداثة دليل الضغط:** الإصدار الطبي 2013؛ تاريخ رفع الملف أو فهرسته لا يغير سنة الإصدار. لم يُتحقق من بديل أحدث على موقع الوزارة في البحث الحالي.
- **تعميم قواعد الأدوية:** بعض القواعد تخص مرضى السكري أو استطباب الروماتويد؛ وجود اسم الدواء وحده لا يكفي لتطبيقها على كل المستخدمين.

كذلك لا يحدد المصدر فاصلًا عدديًا لفحص B12 مع الميتفورمين أو لكل فحوصات ACE/ARB خارج سياق السكري. فحوصات البدء وتغيير الجرعة منفصلة عن المتابعة المستقرة. لا يُعامل فحص CK المرتبط بالأعراض كفحص دوري لكل مستخدم.

## استخدام الملفات مع Claude

1. اقرأ metadata.json ثم sources.json وconflicts.json قبل تحويل البيانات إلى منطق.
2. اربط disease_rules.json وmedication_monitoring.json بالملف الصحي وقائمة المواد الفعالة. الأهلية الحالية وصفية وتحتاج تحويلًا صريحًا إلى شروط برمجية واختبارات.
3. كل حقول التاريخ المفقودة تنتج «نحتاج معلومات»؛ لا تفترض أن الفحص متأخر أو أن الحالة غير موجودة.
4. لا تشغّل قاعدة clinical_status فيها مسودة كإرشاد معتمد. اعرضها في وضع تجريبي معلّم، ثم وثّق المراجع والتاريخ عند اعتمادها.
5. استخدم explanation_knowledge.json لشرح التوصية التي اختارها محرك القواعد فقط. هذه مقاطع موجزة وليست قاعدة أسئلة طبية شاملة.
6. إذا تداخل سبب المرض والدواء، اعرض الفحص مرة واحدة واحتفظ بالسببين. لا تعتمد أقصر مدة آليًا قبل حسم السياق.
7. لا تستنتج أن الأدوية غير الموجودة لا تحتاج مراقبة. الأسماء التجارية غير مجموعة في هذه النسخة.

## المصادر

### S01 — الفحوصات الدورية لمريض السكري

[المصدر الأصلي](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/periodic-check-ups-for-diabetic-patients.aspx)

الجهة: وزارة الصحة السعودية. الإصدار: تعديل المحتوى: 13 صفر 1445 هـ. موضع المعلومة: الفحوصات الدورية لمرضى السكري.
تاريخ تحديث تذييل الموقع ليس تاريخ تحديث التوصية الطبية. توقيت العين يختلف عن مصادر أخرى.

### S02 — Saudi Diabetes Clinical Practice Guidelines

[المصدر الأصلي](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Saudi-Diabetes-Clinical-Practice-Guidelines.pdf)

الجهة: Saudi National Diabetes Center / Saudi Health Council. الإصدار: First Edition 2021. موضع المعلومة: PDF pp. 53, 80–84.
منشور لدى الوزارة؛ الجهة المصدرة هي المركز الوطني للسكري بالمجلس الصحي السعودي. لم يثبت أنه أحدث إصدار.

### S03 — Diabetes Pharmacotherapy Clinic Guideline (Protocol-018)

[المصدر الأصلي](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Protocol-018.pdf)

الجهة: وزارة الصحة / الإدارة العامة للرعاية الصيدلية. الإصدار: ينص الملف على أن النسخة الأولى أُنشئت عام 2020. موضع المعلومة: PDF pp. 4, 26–27.
السياق عيادات السكري؛ لا تعمم قواعده الدوائية على كل المستخدمين دون اعتماد. ذكر تحديث سنوي لا يثبت أن الملف محدّث سنويًا.

### S04 — Cardiometabolic Risk Management Guidelines in Primary Care

[المصدر الأصلي](https://www.moh.gov.sa/Ministry/About/Health%20Policies/026.pdf)

الجهة: وزارة الصحة السعودية. الإصدار: Third Edition, 2013. موضع المعلومة: PDF pp. 5, 16, 35–36, 52, 55–56, 69.
قديم. توقيتات الضغط ومراقبة الأدوية المستخرجة منه تحتاج مراجعة إصدار أحدث قبل تفعيل الجدولة.

### S05 — التوعية بارتفاع ضغط الدم

[المصدر الأصلي](https://www.moh.gov.sa/awarenessplateform/chronicdisease/pages/hypertension.aspx)

الجهة: وزارة الصحة السعودية. الإصدار: تاريخ المحتوى الظاهر: 14/05/2026. موضع المعلومة: تعليمات قياس ضغط الدم والمضاعفات.
تثقيف المريض؛ لا يوفر وحده جدولًا كاملًا للتحاليل الدورية.

### S06 — تأثير السكري على الكلى

[المصدر الأصلي](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/0010.aspx)

الجهة: وزارة الصحة السعودية. الإصدار: لم يثبت تاريخ الإصدار من المصدر المفحوص. موضع المعلومة: الأعراض؛ تأثير السكري على الكلى.
يستخدم للشرح؛ لا يستنتج منه موعد فحص غير منصوص عليه.

### S07 — تأثير السكري على العين

[المصدر الأصلي](https://www.moh.gov.sa/healthawareness/educationalcontent/diseases/diabetic/pages/impact-of-diabetes-on-eyes.aspx)

الجهة: وزارة الصحة السعودية. الإصدار: تعديل المحتوى: 15 محرم 1447 هـ. موضع المعلومة: إرشادات فحص العين لمرض السكري؛ الأعراض.
ينص على متابعة سنوية؛ توجد صيغ مختلفة للتكرار في S01 وS02. الحمل مسار خاص.

### S08 — Anticoagulation Pharmacotherapy Clinic Guideline (Protocol-017)

[المصدر الأصلي](https://www.moh.gov.sa/ministry/mediacenter/publications/documents/protocol-017.pdf)

الجهة: وزارة الصحة / الإدارة العامة للرعاية الصيدلية. الإصدار: لم يثبت تاريخ الإصدار من المصدر المفحوص. موضع المعلومة: PDF p. 6, Table (2) and footnotes.
توقيت INR يعتمد على الاستقرار والنتائج وتغييرات العلاج؛ فاصل 12 أسبوعًا ليس قاعدة لكل مستخدم للوارفارين.

### S09 — Guideline for Management of Rheumatoid Arthritis in Adult Patient (Protocol-014)

[المصدر الأصلي](https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/Protocol-014.pdf)

الجهة: وزارة الصحة السعودية. الإصدار: لم يثبت تاريخ الإصدار من المصدر المفحوص. موضع المعلومة: PDF p. 15, csDMARD monitoring table.
قاعدة مراقبة الميثوتريكسات هنا في سياق روماتويد البالغين؛ لا تعمم على استخدامه في الأورام أو بقية الاستطبابات.

