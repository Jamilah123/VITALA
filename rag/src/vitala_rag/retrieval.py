"""Retrieval: tokenisation, embeddings, FAISS/BM25 indexes, query routing and hybrid search.

  * tokenisation / Arabic normalisation (shared by BM25, grounding and safety rules)
  * Embedder (multilingual e5) and the per-collection FAISS + BM25 index files
  * query processing: language detection, Arabic->English expansion, collection routing, medication scope
  * HybridRetriever: dense + BM25 fused with Reciprocal Rank Fusion
  * AppKnowledgeBase: the VITALA app collection (BM25 over Arabic character n-grams + optional dense)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import numpy as np
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .config import (ACE_INHIBITOR_CLASS, ACE_INHIBITOR_MEMBERS, APP_MIN_BM25, APP_MIN_BM25_EN, APP_MIN_COVERAGE_EN,
                     COLLECTION_APP, COLLECTION_MEDICATION,
                     COLLECTION_PREVENTIVE, COLLECTIONS, E5_PASSAGE_PREFIX, E5_QUERY_PREFIX, EMBED_MODEL, PIPELINE_VERSION,
                     RRF_K, TOP_K_APP, TOP_K_BM25, TOP_K_DENSE, TOP_K_FINAL, Paths)

# ====================================================================================================
# indexing
# Embeddings + FAISS (semantic) and BM25 (keyword) indexes, one pair per collection.
#
# Layout on disk (per collection):
#   indexes/<collection>/chunks.jsonl     chunk records, row i <-> vector i
#   indexes/<collection>/faiss.index      inner-product index over L2-normalised e5 vectors (= cosine)
#   indexes/<collection>/bm25_tokens.json tokenised texts (BM25 is rebuilt in <1 s at load time)
#   indexes/<collection>/index_manifest.json  model, dims, counts, hashes, build time
# ====================================================================================================
# ---------------------------------------------------------------- tokenisation
STOPWORDS = set("""a an and are as at be been but by can could did do does for from had has have how i if in
into is it its may me might more most my no not of on or our should so such than that the their them then
there these they this those to was we were what when where which who why will with would you your about
also any all each other some very per""".split())
AR_DIACRITICS = re.compile(r"[ؗ-ًؚ-ْـ]")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[./][0-9]+)?|[؀-ۿ]+", re.I)


def normalize_arabic(text: str) -> str:
    text = AR_DIACRITICS.sub("", text)
    text = re.sub("[إأآا]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    # Arabic-Indic digits -> Western digits
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


def tokenize(text: str) -> list[str]:
    text = normalize_arabic(unicodedata.normalize("NFKC", text)).lower()
    toks = []
    for t in TOKEN_RE.findall(text):
        if t in STOPWORDS or len(t) == 1 and not t.isdigit():
            continue
        if t.isascii() and len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]                     # crude plural folding: tests -> test
        toks.append(t)
    return toks


# Arabic question words / particles that carry no topic (normalised spelling, MSA + Saudi dialect).
AR_STOPWORDS = set(normalize_arabic(w) for w in """كيف وين فين اين أين هل في من على عن او أو و ما وش ايش إيش ليش لماذا ليه الي
الى إلى اللي التي الذي هذا هذه هذي مع لي عند عندي يمكن ممكن اقدر أقدر تقدر يقدر انا أنا انت أنت هو هي كم متى اذا إذا لو بس
ثم كل اي أي ايه يا قد لا لم لن ان أن إن كان كانت""".split())
_AR_ARTICLE_RE = re.compile(r"^(وال|بال|كال|فال|لل|ال)")


def arabic_ngram_tokens(text: str, n: int = 3) -> list[str]:
    """Word tokens plus character n-grams for Arabic words.

    Arabic (and especially Saudi conversational Arabic) changes word shape a lot: احجز / الحجز / حجز,
    ألغي / إلغاء, موعدي / المواعيد. Character 3-grams of the article-stripped word still overlap, which makes
    keyword search over a small Arabic collection robust without a stemmer dependency. English tokens are kept
    as whole words (same tokenizer as the medical indexes).
    """
    out = []
    for t in tokenize(text):
        if not re.match(r"[؀-ۿ]", t):
            out.append(t)
            continue
        if t in AR_STOPWORDS:
            continue
        w = _AR_ARTICLE_RE.sub("", t)
        w = w if len(w) >= 3 else t
        out.append(w)
        if len(w) > n:
            out += [w[i:i + n] for i in range(len(w) - n + 1)]
    return out


# ---------------------------------------------------------------- embeddings
class Embedder:
    """Thin wrapper around SentenceTransformer with the e5 query/passage prefixes."""

    def __init__(self, model_name: str = EMBED_MODEL, device: str | None = None):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        self.dim = (self.model.get_embedding_dimension() if hasattr(self.model, "get_embedding_dimension")
                    else self.model.get_sentence_embedding_dimension())

    def encode_passages(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        return self._encode([E5_PASSAGE_PREFIX + t for t in texts], batch_size)

    def encode_queries(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        return self._encode([E5_QUERY_PREFIX + t for t in texts], batch_size)

    def _encode(self, texts, batch_size):
        v = self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                              show_progress_bar=len(texts) > 64, convert_to_numpy=True)
        return v.astype("float32")


# ---------------------------------------------------------------- build / load
def _tokenizer(name: str):
    return {"word": tokenize, "arabic_ngram": arabic_ngram_tokens}[name]


def build_collection_index(chunks: list[dict], out_dir: Path, embedder: Embedder, tokenizer: str = "word",
                           extra: dict | None = None) -> dict:
    """Write one collection's index files. Deterministic for a given input: records keep their JSONL order, FAISS is
    an exact (flat) inner-product index, and the manifest records every hash needed to detect a stale index."""
    import faiss
    out_dir.mkdir(parents=True, exist_ok=True)
    if not chunks:
        raise ValueError(f"No chunks to index for {out_dir.name}")
    ids = [c["chunk_id"] for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate chunk_id values; refusing to build an ambiguous index")
    vecs = embedder.encode_passages([c["text_for_embedding"] for c in chunks])
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(out_dir / "faiss.index"))
    stale = out_dir / "embeddings.npy"           # older builds stored a redundant copy of the vectors
    if stale.exists():
        stale.unlink()
    with open(out_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    tok = _tokenizer(tokenizer)
    tokens = [tok(c["text_for_embedding"]) for c in chunks]
    with open(out_dir / "bm25_tokens.json", "w", encoding="utf-8") as f:
        json.dump(tokens, f)
    manifest = {
        "collection": out_dir.name,
        "embedding_model": embedder.model_name,
        "dim": int(vecs.shape[1]),
        "n_chunks": len(chunks),
        "sources": sorted({c["source_id"] for c in chunks}),
        "bm25_tokenizer": tokenizer,
        "faiss_index": "IndexFlatIP over L2-normalised e5 vectors (cosine)",
        "chunks_sha256": hashlib.sha256((out_dir / "chunks.jsonl").read_bytes()).hexdigest(),
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "pipeline_version": PIPELINE_VERSION,
        **(extra or {}),
    }
    with open(out_dir / "index_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def verify_index(index_dir: Path) -> dict:
    """Integrity check without loading a model: manifest vs files (used by `doctor` and notebook 02)."""
    out = {"collection": index_dir.name, "ok": False}
    try:
        manifest = json.loads((index_dir / "index_manifest.json").read_text(encoding="utf-8"))
        chunks = (index_dir / "chunks.jsonl").read_bytes()
        out.update(n_chunks=chunks.count(b"\n"),manifest_n_chunks=manifest["n_chunks"],
                   chunks_hash_ok=manifest["chunks_sha256"] == hashlib.sha256(chunks).hexdigest(),
                   faiss_present=(index_dir / "faiss.index").exists(), bm25_present=(index_dir / "bm25_tokens.json").exists(),
                   embedding_model=manifest.get("embedding_model"), kb_version=manifest.get("kb_version"))
        out["ok"] = out["chunks_hash_ok"] and out["n_chunks"] == manifest["n_chunks"] and out["faiss_present"] and out["bm25_present"]
    except (OSError, ValueError, KeyError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


class CollectionIndex:
    def __init__(self, path: Path, load_faiss: bool = True):
        from rank_bm25 import BM25Okapi
        self.path = path
        self.manifest = json.loads((path / "index_manifest.json").read_text(encoding="utf-8"))
        with open(path / "chunks.jsonl", encoding="utf-8") as f:
            self.chunks = [json.loads(l) for l in f]
        tokens = json.loads((path / "bm25_tokens.json").read_text(encoding="utf-8"))
        self.bm25 = BM25Okapi(tokens)
        self.faiss = None
        if load_faiss:
            import faiss
            self.faiss = faiss.read_index(str(path / "faiss.index"))
            if self.faiss.ntotal != len(self.chunks):
                raise ValueError(f"{path.name}: FAISS has {self.faiss.ntotal} vectors but {len(self.chunks)} chunks")

    def dense_search(self, qvec: np.ndarray, k: int) -> list[tuple[int, float]]:
        scores, idx = self.faiss.search(qvec.reshape(1, -1).astype("float32"), min(k, len(self.chunks)))
        return [(int(i), float(s)) for i, s in zip(idx[0], scores[0]) if i >= 0]

    def bm25_search(self, query_tokens: list[str], k: int) -> list[tuple[int, float]]:
        if not query_tokens:
            return []
        scores = self.bm25.get_scores(query_tokens)
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]


# ====================================================================================================
# query
# Query processing: language detection, Arabic->English term expansion, collection routing.
#
# Why a glossary when e5 is multilingual?
#   The e5 model can match an Arabic question to English text semantically, but BM25 cannot:
#   Arabic words never appear in the English guidelines. The glossary adds English keywords so the
#   keyword half of hybrid search still works. If an LLM is configured, the pipeline also asks it
#   for a faithful English translation of the question (see chatbot.py); the glossary is the
#   deterministic fallback that works with no API at all.
# ====================================================================================================
ARABIC_RE = re.compile(r"[؀-ۿ]")
LATIN_RE = re.compile(r"[A-Za-z]")

# Arabic term (normalised form is computed at load) -> English keywords
AR_EN_GLOSSARY = {
    # medications in scope
    "ميتفورمين": "metformin", "متفورمين": "metformin", "جلوكوفاج": "metformin glucophage",
    "ليسينوبريل": "lisinopril", "ليزينوبريل": "lisinopril", "زيستريل": "lisinopril",
    "إنالابريل": "enalapril", "اينالابريل": "enalapril", "انالابريل": "enalapril", "رينيتك": "enalapril",
    "راميبريل": "ramipril", "رامبريل": "ramipril", "تريتاس": "ramipril", "كابتوبريل": "captopril", "كابوتين": "captopril",
    "بيريندوبريل": "perindopril", "بريندوبريل": "perindopril", "كوفرسيل": "perindopril",
    "مثبطات الانزيم المحول للانجيوتنسين": "ACE inhibitors angiotensin-converting enzyme inhibitors",
    "مثبطات الإنزيم المحول": "ACE inhibitors angiotensin-converting enzyme inhibitors",
    "مثبط الانزيم المحول": "ACE inhibitor angiotensin-converting enzyme inhibitor",
    "مثبطات الاس": "ACE inhibitors", "سعال جاف": "dry cough", "كحة": "cough", "كحه": "cough", "سعال": "cough",
    "تورم الشفايف": "angioedema swelling lips", "تورم الشفاه": "angioedema swelling lips", "وذمة وعائية": "angioedema",
    "البوتاسيوم المرتفع": "hyperkalemia potassium", "ارتفاع البوتاسيوم": "hyperkalemia potassium",
    "مسكنات": "nsaids painkillers", "البروفين": "ibuprofen nsaids", "بروفين": "ibuprofen nsaids",
    "رمضان": "ramadan fasting", "الصيام": "fasting ramadan", "صيام رمضان": "ramadan fasting",
    "الصبغة": "iodinated contrast", "صبغة": "iodinated contrast", "الأشعة بالصبغة": "contrast imaging",
    "فيتامين ب١٢": "vitamin b12", "ب12": "vitamin b12",
    # medication concepts
    "اعراض جانبية": "adverse reactions side effects", "الآثار الجانبية": "adverse reactions side effects",
    "الاثار الجانبيه": "adverse reactions side effects", "آثار جانبية": "adverse reactions side effects",
    "موانع الاستعمال": "contraindications", "موانع": "contraindications", "تداخل": "drug interactions",
    "تداخلات": "drug interactions", "تحذيرات": "warnings precautions", "احتياطات": "precautions warnings",
    "الحمل": "pregnancy", "حامل": "pregnancy pregnant", "الرضاعة": "lactation breastfeeding",
    "جرعة": "dose dosage", "جرعه": "dose dosage", "دواء": "medication drug", "الدواء": "medication drug",
    "مراقبة": "monitoring monitor", "متابعة": "monitoring follow-up", "حماض لبني": "lactic acidosis",
    "الحماض اللبني": "lactic acidosis", "فيتامين ب12": "vitamin b12", "الكلى": "renal kidney",
    "وظائف الكلى": "renal function kidney egfr", "الكبد": "liver hepatic", "وظائف الكبد": "liver enzymes hepatic",
    "الم العضلات": "muscle pain myopathy", "ألم العضلات": "muscle pain myopathy", "العضلات": "muscle myopathy",
    "تورم": "edema swelling", "تورم القدمين": "peripheral edema ankle swelling", "دوخة": "dizziness",
    "الجريب فروت": "grapefruit", "جريب فروت": "grapefruit", "كحول": "alcohol",
    # conditions
    "السكري": "diabetes mellitus", "سكري": "diabetes", "السكر": "diabetes blood glucose", "مقدمات السكري": "prediabetes",
    "ما قبل السكري": "prediabetes", "سكري الحمل": "gestational diabetes", "النوع الثاني": "type 2",
    "النوع الأول": "type 1", "ضغط الدم": "blood pressure hypertension", "الضغط": "blood pressure hypertension",
    "ارتفاع ضغط الدم": "hypertension high blood pressure", "ضغط مرتفع": "hypertension high blood pressure",
    "الكوليسترول": "cholesterol lipid", "كوليسترول": "cholesterol lipid", "الدهون": "lipid profile cholesterol",
    "السمنة": "obesity", "سمنة": "obesity", "الوزن": "weight", "زيادة الوزن": "overweight",
    "مؤشر كتلة الجسم": "body mass index bmi", "كتلة الجسم": "bmi body mass index", "محيط الخصر": "waist circumference",
    "القلب": "cardiovascular heart", "امراض القلب": "cardiovascular disease", "أمراض القلب": "cardiovascular disease",
    "السكتة الدماغية": "stroke", "هشاشة العظام": "osteoporosis", "الاكتئاب": "depression", "التدخين": "smoking tobacco",
    "الإقلاع عن التدخين": "smoking cessation", "تكيس المبايض": "polycystic ovary syndrome",
    # screening / tests
    "فحص": "screening test", "فحوصات": "screening tests", "الفحص": "screening", "الكشف المبكر": "screening early detection",
    "فحص دوري": "periodic health examination screening", "تحليل": "test laboratory", "التحاليل": "laboratory tests",
    "السكر التراكمي": "hba1c a1c glycated hemoglobin", "التراكمي": "hba1c", "سكر صائم": "fasting blood glucose",
    "السكر الصائم": "fasting plasma glucose", "صيام": "fasting", "تحمل الجلوكوز": "oral glucose tolerance test",
    "سرطان الثدي": "breast cancer mammogram", "الماموجرام": "mammogram mammography", "ماموغرام": "mammogram",
    "سرطان القولون": "colorectal cancer colon", "القولون": "colon colorectal", "منظار القولون": "colonoscopy",
    "سرطان عنق الرحم": "cervical cancer pap smear", "مسحة عنق الرحم": "pap smear cervical", "سرطان الرئة": "lung cancer",
    "كثافة العظام": "dexa bone density", "التطعيم": "immunization vaccine", "التطعيمات": "immunization vaccines",
    "لقاح": "vaccine immunization", "الانفلونزا": "influenza", "الإنفلونزا": "influenza",
    "قياس الضغط": "blood pressure measurement", "جهاز قياس الضغط": "home blood pressure monitoring",
    "الملح": "sodium salt", "ملح": "sodium salt", "البوتاسيوم": "potassium", "الرياضة": "physical activity exercise",
    "النشاط البدني": "physical activity", "رياضة": "physical activity exercise", "الغذاء": "diet nutrition",
    "النظام الغذائي": "diet dietary pattern", "حمية": "diet", "الوقاية": "prevention", "وقاية": "prevention",
    "عوامل الخطورة": "risk factors", "عوامل الخطر": "risk factors", "كل كم": "how often interval every years",
    "متى": "when age start", "عمر": "age years", "سنة": "years", "سنوات": "years", "البالغين": "adults",
    "الأطفال": "children", "كبار السن": "older adults elderly", "النساء": "women", "الرجال": "men",
    "الأسبرين": "aspirin", "اسبرين": "aspirin", "الستاتين": "statin", "حمض الفوليك": "folic acid",
    "نتيجة": "result", "نتائج": "results", "طبيعي": "normal", "مرتفع": "elevated high", "منخفض": "low",
    "ماذا يعني": "what does mean definition", "ما معنى": "definition meaning", "تعريف": "definition",
}
AR_PREFIX_RE = re.compile(r"(?<![؀-ۿ])(وال|بال|كال|فال|لل|ال)(?=[؀-ۿ]{2,})")


def _ar_key(text: str) -> str:
    """Normalise Arabic for glossary matching: unify letters and drop the definite article ("الأعراض" -> "اعراض")."""
    return AR_PREFIX_RE.sub("", normalize_arabic(text))


_GLOSS = sorted(((_ar_key(k), v) for k, v in AR_EN_GLOSSARY.items()), key=lambda kv: -len(kv[0]))

IN_SCOPE_DRUGS = {
    "metformin": ["metformin", "glucophage", "ميتفورمين", "متفورمين", "جلوكوفاج", "الميتفورمين"],
    # The ACE inhibitor class itself (questions about "ACE inhibitors" in general).
    ACE_INHIBITOR_CLASS: ["ace inhibitor", "ace inhibitors", "ace-inhibitor", "ace-inhibitors", "acei", "acei's",
                          "angiotensin converting enzyme inhibitor", "angiotensin-converting enzyme inhibitor",
                          "angiotensin-converting-enzyme inhibitor", "مثبطات الانزيم المحول", "مثبط الانزيم المحول",
                          "مثبطات الإنزيم المحول", "مثبطات الاس"],
    "lisinopril": ["lisinopril", "zestril", "prinivil", "ليسينوبريل", "ليزينوبريل", "زيستريل"],
    "enalapril": ["enalapril", "enalaprilat", "vasotec", "renitec", "إنالابريل", "اينالابريل", "انالابريل", "رينيتك"],
    "ramipril": ["ramipril", "tritace", "altace", "راميبريل", "رامبريل", "تريتاس"],
    "captopril": ["captopril", "capoten", "كابتوبريل", "كابوتين"],
    "perindopril": ["perindopril", "coversyl", "aceon", "بيريندوبريل", "بريندوبريل", "كوفرسيل"],
    "benazepril": ["benazepril"], "fosinopril": ["fosinopril"], "quinapril": ["quinapril"],
    "moexipril": ["moexipril"], "trandolapril": ["trandolapril"],
}
# Common drug-name endings. A match that is not an in-scope drug means "medication we do not cover".
OTHER_DRUG_RE = re.compile(
    # \w{3,} prefix avoids everyday words such as "April"
    r"\b\w{3,}(pril|sartan|olol|dipine|gliptin|gliflozin|glutide|statin|prazole|tidine|cillin|mycin|floxacin|"
    r"azepam|oxetine|profen|coxib|parin|xaban|gatran|thiazide|formin|glinide|glitazone)\b", re.I)
OTHER_DRUG_NAMES = {"insulin", "warfarin", "aspirin", "ibuprofen", "paracetamol", "acetaminophen", "amlodipine",
                    "norvasc", "atorvastatin", "lipitor", "أملوديبين", "املوديبين", "اوملوديبين", "نورفاسك",
                    "أتورفاستاتين", "اتورفاستاتين", "ليبيتور", "sacubitril", "entresto", "aliskiren",
                    "losartan", "rosuvastatin", "simvastatin", "ozempic", "semaglutide", "panadol", "glipizide",
                    "gliclazide", "sitagliptin", "empagliflozin", "dapagliflozin", "hydrochlorothiazide", "clopidogrel",
                    "انسولين", "الانسولين", "وارفارين", "بنادول", "اوزمبيك", "ابوبروفين"}
# Medicines that the PREVENTIVE guidelines discuss (aspirin chemoprophylaxis, insulin in diabetes care): a question that
# names them is declined as out of scope only when it is clearly a medication question (MEDICATION_HINTS).
STRICT_MEDICATION_HINTS = re.compile(
    r"\b(side effects?|adverse|contraindicat\w*|interact\w*|dose|dosage|mg|overdos\w*|tablets?|pills?)\b|"
    r"(جرعه|جرعة|اعراض جانبية|أعراض جانبية|الآثار الجانبية|آثار جانبية|تداخل|موانع|حبوب)", re.I)
PREVENTIVE_TOPIC_DRUGS = {"aspirin", "insulin", "انسولين", "الانسولين"}


def is_out_of_scope_medication_question(pq: "ProcessedQuery", question: str) -> bool:
    """Names a medicine outside the demo scope (and none inside it)."""
    if not pq.other_drugs or pq.drugs:
        return False
    if set(pq.other_drugs) - PREVENTIVE_TOPIC_DRUGS:
        return True
    # aspirin / insulin: "should adults take aspirin to prevent heart disease?" is preventive-guideline content;
    # only clearly medication-label questions (side effects, dose, interactions...) are declined.
    return bool(STRICT_MEDICATION_HINTS.search(question + " " + pq.english))


MEDICATION_HINTS = re.compile(
    r"\b(side effects?|adverse|contraindicat\w*|interact\w*|warning\w*|dose|dosage|tablet\w*|pill\w*|medicat\w*|medicine\w*|drug\w*|"
    r"take|taking|prescri\w*|label|lactic acidosis|myopathy|grapefruit|pregnan\w*|breastfeed\w*)\b|"
    r"(دواء|الدواء|ادوية|أدوية|حبوب|جرعة|جرعه|اعراض جانبية|أعراض جانبية|الآثار الجانبية|آثار جانبية|تداخل|موانع|اخذ|آخذ)", re.I)
PREVENTIVE_HINTS = re.compile(
    r"\b(screen\w*|check-?up|guideline\w*|prevent\w*|risk factor\w*|bmi|waist|mammogra\w*|pap|colonoscopy|"
    r"vaccin\w*|immuni[sz]\w*|blood pressure|hypertension|prediabetes|diabetes|hba1c|a1c|glucose|lifestyle|diet|"
    r"exercise|physical activity|salt|sodium|obesity|weight|cholesterol|lipid)\b|"
    r"(فحص|فحوصات|الكشف|وقاية|الوقاية|السكري|الضغط|سكر|الوزن|السمنة|تطعيم|لقاح|كوليسترول|نمط الحياة|رياضة)", re.I)


def _ar(pattern: str) -> str:
    """Write Arabic patterns in normal spelling; match them against normalize_arabic() text."""
    return normalize_arabic(pattern)


# ---- VITALA application questions (routed to the "app" collection, never to medical evidence) -------------
# Nouns that only make sense as parts of the app (screens, workflows, devices, clinic-side features).
APP_NOUN_RE = re.compile(
    r"\b(appointments?|booking|book(ed)? (a|an|my)|reschedul\w*|apple health|health ?kit|wearables?|smart ?watch\w*|"
    r"clinics?|dashboard|home (page|screen)|notifications?|reminders?|(my|an|new|create( an)?) account|sign ?up|"
    r"log ?in|login|password|"
    r"map|overdue|due (and|vs\.?|versus|or) overdue|due (screenings?|tests?)|upcoming (screenings?|tests?)|"
    r"health plan|screening plan|ai assistant|assistant|chat ?bot|health history|results? (section|page|tab)|"
    r"upload\w*|vitala|the app|this app|app)\b|" + _ar(
        r"موعد|مواعيد|الحجز|حجز|العياده|عياده|العيادات|عيادات|التطبيق|تطبيق|ابل هيلث|آبل هيلث|الساعه الذكيه|ساعه ذكيه|"
        r"الساعه|ساعتي|جهاز قابل للارتداء|الاجهزه القابله للارتداء|حسابي|الحساب|حساب|تسجيل الدخول|تسجيل دخول|كلمه المرور|"
        r"الصفحه الرئيسيه|الرئيسيه|الاشعارات|اشعارات|التذكيرات|تذكير|الخريطه|خريطه|المساعد الذكي|المساعد|الشات|"
        r"خطه الفحوصات|الخطه الصحيه|المستحقه|المتاخره|السجل الصحي|رفع النتائج|لوحه التحكم|معلوماتي|بياناتي|فيتالا|"
        r"فايتالا"), re.I)
# Words that signal using / navigating the app.
APP_ACTION_RE = re.compile(
    r"\b(book|cancel\w*|reschedul\w*|edit|modify|change my appointment|connect|link|sync\w*|sign ?up|log ?in|register|"
    r"find (my|the)|see my|view my|access|upload|contact the clinic|open)\b|" + _ar(
        r"احجز|أحجز|نحجز|حجز|الغي|ألغي|الغاء|إلغاء|اعدل|أعدل|تعديل|اغير|أغير|اربط|أربط|ربط|اسجل|أسجل|ادخل|أدخل|القى|ألقى|"
        r"الاقي|ألاقي|احصل|أحصل|اشوف|أشوف|تشوف|يشوف|يستخدم|تستخدم|اضيف|أضيف|ارفع|أرفع|اتواصل|أتواصل|افتح|أفتح"), re.I)
# Question frames: "how do I / where can I / can I / what can ...", "كيف / وين / هل أقدر / تقدر ..."
APP_NAV_FRAME_RE = re.compile(
    r"\b(how (do|can|could|should|does|will|would) (i|we|you|vitala|the app|it)|where (do|can|could|is|are|will) "
    r"(i|we|my|the)|can i|could i|is it possible to|is there a way to|what can (the )?(vitala|app|ai|assistant)|"
    r"(can|does|do|will) (the )?(clinic|clinics|vitala|app|assistant))\b|" + _ar(
        r"كيف|وين|فين|اين|أين|هل اقدر|هل أقدر|اقدر|أقدر|تقدر|يقدر|هل يمكنني|هل يمكن|ممكن|وش يسوي|ايش يسوي|وش تسوي"), re.I)
# Clinical content: when present, an app noun alone is not enough to route away from the medical sources.
MED_SPECIFIC_RE = re.compile(
    r"\b(diabet\w*|prediabet\w*|hba1c|a1c|glucose|blood sugar|blood pressure|hypertension|cholesterol|lipid\w*|ldl|"
    r"cancer|mammogra\w*|colonoscopy|pap|vaccin\w*|side effects?|adverse|dose|dosage|metformin|ace inhibitors?|\w+pril|"
    r"statin|pregnan\w*|kidney|liver|symptoms?|treatment|disease)\b|" + _ar(
        r"سكري|السكر|سكر|التراكمي|ضغط الدم|الضغط|الكوليسترول|كوليسترول|الدهون|سرطان|الماموجرام|القولون|لقاح|تطعيم|"
        r"اعراض|جرعه|ميتفورمين|بريل|مثبطات|الحمل|الكلى|الكبد|علاج|مرض"), re.I)
# "Book an appointment for me" / "cancel my appointment for me": the assistant cannot act inside the app.
APP_ACTION_REQUEST_RE = re.compile(
    r"\b(book|cancel|reschedule|change|upload|send) (me |for me )?(a |an |my )?(appointment|booking|visit|result)s?\b"
    r".{0,20}\bfor me\b|\b(can|could|will) you (please )?(book|cancel|reschedule|upload|connect|send)\b|" + _ar(
        r"احجز لي|أحجز لي|احجزلي|الغ موعدي|ألغ موعدي|الغي موعدي لي|الغي لي|ألغي لي|عدل لي|عدّل لي|غير لي موعدي|"
        r"اربط لي|ارفع لي|سجل لي|تقدر تحجز|تقدر تلغي|ممكن تحجز|ممكن تلغي"), re.I)


WHY_RE = re.compile(r"^\W*(why|what is the reason|" + _ar(r"ليش|لماذا|ليه|لمذا|وش السبب|ايش السبب|ما سبب") + r")", re.I)


def app_intent(text: str) -> str | None:
    """Classify a question as an app question.

    Returns "nav" (how/where/can-I + app usage: always the app collection), "topic" (mentions app-only concepts
    with no clinical content, e.g. due vs overdue screenings) or None.
    """
    t = normalize_arabic(text.lower())
    noun = bool(APP_NOUN_RE.search(t))
    action = bool(APP_ACTION_RE.search(t))
    frame = bool(APP_NAV_FRAME_RE.search(t))
    med = bool(MED_SPECIFIC_RE.search(t))
    why = bool(WHY_RE.search(t))       # "why does VITALA recommend X for me" asks for a reason, not navigation
    if APP_ACTION_REQUEST_RE.search(t) and (noun or action):
        return "nav"
    if frame and not why and (noun or (action and not med)):
        return "nav"
    if noun and not med:
        return "topic"
    return None


def is_app_action_request(text: str) -> bool:
    return bool(APP_ACTION_REQUEST_RE.search(normalize_arabic(text.lower())))


@dataclass
class ProcessedQuery:
    original: str
    language: str                     # "ar" | "en"
    english: str                      # translated / expanded English text used for retrieval
    keywords_en: str                  # glossary expansion
    collections: list[str]
    drugs: list[str] = field(default_factory=list)
    other_drugs: list[str] = field(default_factory=list)
    app_intent: str | None = None     # "nav" | "topic" | None (see app_intent())


def detect_language(text: str) -> str:
    ar, la = len(ARABIC_RE.findall(text)), len(LATIN_RE.findall(text))
    return "ar" if ar >= max(3, la * 0.5) else "en"


# Lay English -> label/guideline vocabulary, for the keyword (BM25) half of search only.
EN_EXPANSIONS = [
    (r"side[- ]?effects?", "adverse reactions"), (r"interact\w*", "drug interactions"),
    (r"\bwho (should not|shouldn't|can't|cannot) take\b|\bnot take\b", "contraindications"),
    (r"pregnan\w*", "pregnancy"), (r"breast ?feed\w*", "lactation"), (r"kidney", "renal"), (r"liver", "hepatic"),
    (r"blood sugar", "glucose glycemic"), (r"high blood pressure", "hypertension"), (r"check[- ]?ups?", "screening"),
    (r"colon cancer|bowel cancer", "colorectal"), (r"muscle (pain|ache)s?", "myopathy myalgia"),
    (r"swelling|swollen", "edema"), (r"how often", "every years interval"), (r"monitor\w*|tests? (do|should) i", "monitoring test"),
    # lay words -> the vocabulary of the medication sources
    (r"pain ?killers?|pain relie\w+|pain medic\w*|analgesic\w*|anti-?inflammator\w*",
     "NSAIDs ibuprofen naproxen diclofenac analgesics"),
    (r"\bcough\w*", "cough bradykinin"), (r"lips?|tongue|throat swell\w*|face swell\w*", "angioedema"),
    (r"potassium", "potassium hyperkalemia"), (r"dizz\w*|light-?headed|faint\w*", "dizziness hypotension"),
    (r"\bfasting|ramadan", "ramadan fasting iftar suhoor"), (r"contrast|ct scan|x-?ray dye", "iodinated contrast"),
    (r"\bfoods?\b|\beat(ing)?\b|\bmeals?\b", "diet dietary DASH nutrition"),
    (r"surgery|operation", "surgery perioperative"), (r"missed (a )?dose|forgot\w* (to take|my)", "missed dose"),
    (r"\bb12\b|vitamin b", "vitamin B12 deficiency"), (r"salt substitute", "potassium salt substitutes"),
]


def english_expand(text: str) -> str:
    extra = [v for p, v in EN_EXPANSIONS if re.search(p, text, re.I)]
    return " ".join(extra)


def glossary_expand(text: str) -> str:
    norm = _ar_key(text)
    found = []
    for ar, en in _GLOSS:
        if ar in norm:
            found.append(en)
            norm = norm.replace(ar, " ")
    # keep any Latin words the user wrote (drug names, "HbA1c", numbers)
    found += re.findall(r"[A-Za-z][A-Za-z0-9\-]+|\d+(?:[./]\d+)?", text)
    return " ".join(dict.fromkeys(found))


def find_drugs(text: str) -> tuple[list[str], list[str]]:
    """(in-scope medications named in the text, other medication names found).

    In-scope names are canonical: "metformin", "ace_inhibitor" (the class) or an ACE inhibitor such as "lisinopril".
    """
    low = normalize_arabic(text.lower())
    drugs = []
    for d, names in IN_SCOPE_DRUGS.items():
        for n in names:
            n = normalize_arabic(n.lower())
            # Latin names need a word boundary ("acei" inside a word is not a drug); Arabic names may carry an
            # attached prefix (\u0627\u0644\u0644\u064A\u0633\u064A\u0646\u0648\u0628\u0631\u064A\u0644\u060C \u0644\u0644\u0645\u064A\u062A\u0641\u0648\u0631\u0645\u064A\u0646), so they match as substrings.
            pattern = re.escape(n) if ARABIC_RE.search(n) else rf"(?<![\w]){re.escape(n)}"
            if re.search(pattern, low):
                drugs.append(d)
                break
    in_scope_words = {normalize_arabic(n.lower()) for ns in IN_SCOPE_DRUGS.values() for n in ns}
    others = set()
    for m in OTHER_DRUG_RE.finditer(text):
        w = m.group(0).lower()
        if w not in in_scope_words:
            others.add(w)
    for name in OTHER_DRUG_NAMES:
        n = normalize_arabic(name.lower())
        # Arabic names may carry an attached prefix (الأتورفاستاتين); Latin names need word boundaries
        pattern = (rf"{re.escape(n)}(?![\w\u0600-\u06FF])" if ARABIC_RE.search(n)
                   else rf"(?<![\w\u0600-\u06FF]){re.escape(n)}(?![\w\u0600-\u06FF])")
        if re.search(pattern, low):
            others.add(name)
    return drugs, sorted(others)


def medication_filter(drugs: list[str]) -> set[str]:
    """Chunk medication tags a medication question may retrieve.

    A question about lisinopril may use lisinopril records and ACE-inhibitor class records, but not another agent's
    monograph (ramipril doses are not lisinopril doses). A question about ACE inhibitors in general may use all of them.
    """
    allowed = set()
    for d in drugs:
        allowed.add(d)
        if d in ACE_INHIBITOR_MEMBERS:
            allowed.add(ACE_INHIBITOR_CLASS)
        if d == ACE_INHIBITOR_CLASS:
            allowed.update(ACE_INHIBITOR_MEMBERS)
    return allowed


def route(text_en: str, original: str, drugs: list[str]) -> list[str]:
    both = f"{text_en} {original}"
    # Prenatal folic-acid prevention belongs to the preventive guideline, not
    # the FDA-label collection. A broad word like "take" should not override that.
    if not drugs and re.search(r"folic acid|حمض الفوليك", both, re.I) and re.search(
        r"pregnan|planning|conceiv|الحمل|حمل", both, re.I
    ):
        return [COLLECTION_PREVENTIVE]
    if drugs:
        # a drug question may still touch screening ("does metformin change my A1C screening?")
        return [COLLECTION_MEDICATION] + ([COLLECTION_PREVENTIVE] if PREVENTIVE_HINTS.search(both) and
                                           re.search(r"screen|فحص", both, re.I) else [])
    med = bool(MEDICATION_HINTS.search(both))
    prev = bool(PREVENTIVE_HINTS.search(both))
    if med and not prev:
        return [COLLECTION_MEDICATION, COLLECTION_PREVENTIVE]
    return [COLLECTION_PREVENTIVE] + ([COLLECTION_MEDICATION] if med else [])


def process_query(question: str, english_translation: str | None = None, allow_app: bool = True) -> ProcessedQuery:
    lang = detect_language(question)
    kw = glossary_expand(question) if lang == "ar" else ""
    english = english_translation or (kw if lang == "ar" else question)
    kw = f"{kw} {english_expand(english)}".strip()
    drugs, others = find_drugs(question + " " + (english_translation or ""))
    cols = route(english + " " + kw, question, drugs)
    # App intent is judged on the user's own words (+ the LLM translation when available), never on glossary
    # keywords, so medical routing is unchanged for every question that is not about the app.
    intent = None
    if allow_app:
        intent = app_intent(question) or (app_intent(english_translation) if english_translation else None)
    if intent:
        cols = [COLLECTION_APP]
    return ProcessedQuery(question, lang, english, kw, cols, drugs, others, intent)


# ====================================================================================================
# retrieval
# Hybrid retrieval: dense (e5 + FAISS) and BM25 fused with Reciprocal Rank Fusion (RRF).
#
# RRF score = sum over rankers of 1 / (RRF_K + rank). It needs no score normalisation, which matters because
# cosine similarities and BM25 scores live on completely different scales.
# ====================================================================================================
@dataclass
class Candidate:
    chunk: dict
    collection: str
    rrf: float
    dense_score: float | None
    dense_rank: int | None
    bm25_score: float | None
    bm25_rank: int | None


def class_level_variant(pq: ProcessedQuery) -> str | None:
    """The query with every named ACE inhibitor replaced by "ACE inhibitor" (None if no ACE inhibitor is named)."""
    members = [d for d in pq.drugs if d in ACE_INHIBITOR_MEMBERS]
    if not members:
        return None
    text = pq.english or pq.original
    for d in members:
        for n in sorted(IN_SCOPE_DRUGS[d], key=len, reverse=True):
            text = re.sub(re.escape(n), "ACE inhibitor", text, flags=re.I)
    return text if "ACE inhibitor" in text else f"{text} ACE inhibitor"


class HybridRetriever:
    def __init__(self, index_root: Path, embedder=None):
        self.embedder = embedder
        self.last_timings: dict = {}
        self.indexes: dict[str, CollectionIndex] = {}
        for c in COLLECTIONS:
            p = index_root / c
            if (p / "index_manifest.json").exists():
                self.indexes[c] = CollectionIndex(p, load_faiss=embedder is not None)
        if not self.indexes:
            raise FileNotFoundError(f"No indexes found under {index_root}. Run notebook 01 (or `python -m vitala_rag build`).")
        if embedder is not None:
            for c, idx in self.indexes.items():
                if idx.manifest["embedding_model"] != embedder.model_name:
                    raise ValueError(f"{c} index was built with {idx.manifest['embedding_model']}, "
                                     f"but the query embedder is {embedder.model_name}")

    def search(self, pq: ProcessedQuery, k: int = TOP_K_FINAL, max_per_page: int = 3) -> list[Candidate]:
        """Hybrid search over pq.collections. Timings of the last call are kept in self.last_timings (ms)."""
        t0 = time.perf_counter()
        # A question naming one ACE inhibitor ("ibuprofen with lisinopril") is often answered by CLASS-level records
        # (the interaction table covers all ACE inhibitors). The agent name dominates both rankers, so a class-level
        # variant of the query is searched as well.
        variant = class_level_variant(pq)
        dense_queries = list(dict.fromkeys([pq.original, pq.english] + ([variant] if variant else [])))
        qvecs = self.embedder.encode_queries(dense_queries) if self.embedder is not None else None
        t_embed = time.perf_counter()
        bm25_text = (f"{pq.original} {pq.keywords_en}" if pq.language == "en"
                     else f"{pq.english} {pq.keywords_en}") + (" ACE inhibitor" if variant else "")
        q_tokens = tokenize(bm25_text)

        fused: dict[str, Candidate] = {}
        for ci, col in enumerate(pq.collections):
            idx = self.indexes.get(col)
            if idx is None:
                continue
            weight = 1.0 if ci == 0 else 0.85
            allowed = None
            if col == COLLECTION_MEDICATION and pq.drugs:
                tags = medication_filter(pq.drugs)
                allowed = {i for i, c in enumerate(idx.chunks)
                           if tags & set(c.get("medications") or ([c["drug"]] if c.get("drug") else []))}
            n_all = len(idx.chunks)

            dense: dict[int, float] = {}
            if qvecs is not None:
                for qv in qvecs:
                    for i, s in idx.dense_search(qv, n_all if allowed is not None else TOP_K_DENSE * 2):
                        if allowed is None or i in allowed:
                            dense[i] = max(dense.get(i, -1.0), s)
            dense_ranked = sorted(dense.items(), key=lambda x: -x[1])[:TOP_K_DENSE]
            bm = [(i, s) for i, s in idx.bm25_search(q_tokens, n_all if allowed is not None else TOP_K_BM25 * 2)
                  if allowed is None or i in allowed][:TOP_K_BM25]

            scores: dict[int, dict] = {}
            for r, (i, s) in enumerate(dense_ranked, 1):
                scores.setdefault(i, {})["dense"] = (r, s)
            for r, (i, s) in enumerate(bm, 1):
                scores.setdefault(i, {})["bm25"] = (r, s)
            for i, d in scores.items():
                rrf = sum(weight / (RRF_K + d[key][0]) for key in d)
                chunk = idx.chunks[i]
                cand = Candidate(chunk, col, rrf,
                                 d.get("dense", (None, None))[1], d.get("dense", (None, None))[0],
                                 d.get("bm25", (None, None))[1], d.get("bm25", (None, None))[0])
                prev = fused.get(chunk["chunk_id"])
                if prev is None or cand.rrf > prev.rrf:
                    fused[chunk["chunk_id"]] = cand

        ranked = sorted(fused.values(), key=lambda c: -c.rrf)
        out, per_page = [], {}
        for c in ranked:
            key = (c.chunk["source_id"], c.chunk.get("pdf_page_start"), c.chunk.get("label_field"))
            if per_page.get(key, 0) >= max_per_page:
                continue
            per_page[key] = per_page.get(key, 0) + 1
            out.append(c)
            if len(out) >= k:
                break
        t_end = time.perf_counter()
        self.last_timings = {"query_embedding": round((t_embed - t0) * 1000, 1),
                             "index_search": round((t_end - t_embed) * 1000, 1)}
        return out


# ====================================================================================================
# app_knowledge (search)
# App collection search (BM25 over Arabic n-grams + optional dense).
# ====================================================================================================
@dataclass
class AppSearchResult:
    candidates: list[Candidate]
    gate: dict


# Words that appear in almost every app question and say nothing about the topic.
GENERIC_APP_WORDS = {"vitala", "app", "application", "use", "using", "find", "get", "see", "where", "please", "help",
                     "want", "need", "know", "tell", "there", "way", "possible", "able"}


class AppKnowledgeBase:
    """Hybrid (BM25 over Arabic n-grams + optional e5 dense) search over the app documentation sections."""

    def __init__(self, paths: Paths | None = None, embedder=None, doc_paths: dict[str, Path] | None = None,
                 status_path: Path | None = None, min_bm25: float = APP_MIN_BM25):
        from rank_bm25 import BM25Okapi

        from .knowledge import load_feature_status, parse_app_document
        paths = paths or Paths()
        custom = doc_paths is not None or status_path is not None
        doc_paths = doc_paths if doc_paths is not None else paths.app_docs
        status_file = status_path if status_path is not None else paths.app_feature_status
        self.chunks: list[dict] = []
        self.missing_docs = [str(p) for p in doc_paths.values() if not p.exists()]
        self.embedder = embedder
        self.vectors = None
        # Prefer the built index (indexes/app/), but only if it was built from exactly these documents and this
        # feature-status file; otherwise parse the documents directly so the collection can never be stale.
        self.loaded_from, self.index_note = "documents", ""
        if not custom:
            self.index_note = self._load_index(paths.indexes / COLLECTION_APP, doc_paths, status_file, embedder)
        if not self.chunks:
            status = load_feature_status(status_file)
            for audience, p in doc_paths.items():
                if p.exists():
                    self.chunks += parse_app_document(p, audience, status)
        self.min_bm25 = min_bm25
        self.min_bm25_en, self.min_coverage_en = APP_MIN_BM25_EN, APP_MIN_COVERAGE_EN
        self.bm25 = BM25Okapi([arabic_ngram_tokens(c["text_for_embedding"]) for c in self.chunks]) if self.chunks else None
        if embedder is not None and self.chunks and self.vectors is None:
            self.vectors = embedder.encode_passages([c["text_for_embedding"] for c in self.chunks])

    def _load_index(self, idx_dir: Path, doc_paths: dict, status_file: Path, embedder) -> str:
        from .knowledge import APP_SOURCES, sha256_file
        mpath = idx_dir / "index_manifest.json"
        if not mpath.exists():
            return "no app index built yet; parsed the documents"
        m = json.loads(mpath.read_text(encoding="utf-8"))
        current = {APP_SOURCES[a]["source_id"]: sha256_file(p) for a, p in doc_paths.items() if p.exists()}
        if m.get("source_sha256") != current:
            return "app index is older than the documents; parsed the documents (rebuild indexes)"
        if m.get("feature_status_sha256", "") != (sha256_file(status_file) if status_file.exists() else ""):
            return "feature status changed since the app index was built; parsed the documents"
        if embedder is not None and m.get("embedding_model") != embedder.model_name:
            return "app index was built with a different embedding model; parsed the documents"
        with open(idx_dir / "chunks.jsonl", encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f]
        if embedder is not None:
            import faiss
            fx = faiss.read_index(str(idx_dir / "faiss.index"))
            self.vectors = fx.reconstruct_n(0, fx.ntotal).astype("float32")
        self.loaded_from = "index"
        return "loaded indexes/app"

    @property
    def available(self) -> bool:
        return bool(self.chunks)

    def _coverage(self, question: str, chunk: dict) -> float | None:
        """Share of the English question's content words that the section contains (None for Arabic questions).

        English questions get no Arabic n-gram overlap, so BM25 scores are small and a generic word such as
        "appointment" can carry an uncovered topic ("How do I pay for my appointment?"). Requiring most content
        words to be present keeps the gate honest.
        """
        words = [t for t in tokenize(question) if t.isascii() and not t.isdigit() and t not in GENERIC_APP_WORDS]
        if not words or re.search(r"[؀-ۿ]", question):
            return None
        have = set(arabic_ngram_tokens(chunk["text_for_embedding"]))
        return sum(w in have for w in words) / len(words)

    def search(self, question: str, english: str | None = None, k: int = TOP_K_APP) -> AppSearchResult:
        if not self.chunks:
            return AppSearchResult([], {"reason": "app_documents_missing", "passed": False})
        text = question if not english or english == question else f"{question} {english}"
        q_tokens = arabic_ngram_tokens(text)
        bm_scores = self.bm25.get_scores(q_tokens) if q_tokens else np.zeros(len(self.chunks))
        bm_ranked = [(int(i), float(bm_scores[i])) for i in np.argsort(-bm_scores) if bm_scores[i] > 0]
        dense_ranked = []
        if self.vectors is not None:
            qv = self.embedder.encode_queries(list(dict.fromkeys([question, english or question])))
            sims = (self.vectors @ qv.T).max(axis=1)
            dense_ranked = [(int(i), float(sims[i])) for i in np.argsort(-sims)]
        scores: dict[int, dict] = {}
        for r, (i, s) in enumerate(bm_ranked, 1):
            scores.setdefault(i, {})["bm25"] = (r, s)
        for r, (i, s) in enumerate(dense_ranked, 1):
            scores.setdefault(i, {})["dense"] = (r, s)
        cands = []
        for i, d in scores.items():
            rrf = sum(1.0 / (RRF_K + d[key][0]) for key in d)
            cands.append(Candidate(self.chunks[i], COLLECTION_APP, rrf,
                                   d.get("dense", (None, None))[1], d.get("dense", (None, None))[0],
                                   d.get("bm25", (None, None))[1], d.get("bm25", (None, None))[0]))
        cands.sort(key=lambda c: -c.rrf)
        cands = cands[:k]
        best_bm = max((c.bm25_score or 0.0 for c in cands), default=0.0)
        best_dense = max((c.dense_score for c in cands if c.dense_score is not None), default=None)
        coverage = self._coverage(question, cands[0].chunk) if cands else None
        # Keyword evidence decides in both modes (see config.APP_MIN_BM25 for why dense similarity does not).
        ok = best_bm >= (self.min_bm25 if coverage is None else self.min_bm25_en)
        if coverage is not None and coverage < self.min_coverage_en:
            ok = False
        gate = {"collection": COLLECTION_APP, "best_bm25": round(best_bm, 3),
                "best_dense": round(best_dense, 4) if best_dense is not None else None,
                "en_term_coverage": round(coverage, 2) if coverage is not None else None, "passed": ok}
        return AppSearchResult(cands, gate)
