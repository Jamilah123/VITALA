"""Knowledge base: sources, licensing gate, chunking and processed knowledge records.

Responsibilities (one module so the whole data path can be read top to bottom):
  * source registry: what each source is, its licence, scope and clinical-review status
  * the activation gate: which sources may enter the active indexes
  * chunking of PDF guidelines, FDA labels, the app documentation and the medication knowledge PDFs
  * processed knowledge records (JSONL) with stable IDs, content hashes and provenance
  * build stages used by notebook 01 and `python -m vitala_rag build`
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import statistics
import time

import pymupdf
import requests
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import (ACE_INHIBITOR_CLASS, ACE_INHIBITOR_MEMBERS, ACE_INHIBITORS_WITH_MONOGRAPHS, ALL_COLLECTIONS,
                     CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS, CHUNK_TARGET_CHARS, COLLECTION_APP, COLLECTION_MEDICATION,
                     COLLECTION_PREVENTIVE, IN_SCOPE_MEDICATIONS, KB_VERSION, LICENCE_STATUSES_ALLOWED, PIPELINE_VERSION,
                     REQUIRE_CLINICAL_APPROVAL, Paths)
from .pdf_extract import NUMERIC_THRESHOLD_RE, RESIDUAL_GARBLE_RE, Block, PageRecord, extract_pdf
from .retrieval import normalize_arabic

# ====================================================================================================
# registry: the activation gate
#
# data/source_registry.csv is the single, human-editable record of every source: what it is, where it came from,
# its licence, whether it is in the demo scope and whether a clinician has reviewed it. A source enters the active
# indexes ONLY when every check passes:
#   1. the raw file exists and its SHA-256 equals the registered hash (a replaced or edited file is blocked)
#   2. the licence status allows indexing (permitted / permitted_internal_use) and the automatic licence scan of the
#      PDF finds no text-and-data-mining / machine-learning restriction (this scan cannot be overridden)
#   3. scope_status is in_scope and the collection is one of preventive / medication / app
#   4. if VITALA_REQUIRE_CLINICAL_APPROVAL=1 (production), clinical_review_status is APPROVED
# The index builder re-checks every record against the gate, so an unapproved document cannot slip in later.
# ====================================================================================================
# Phrases that mean "do not use this for ML / text mining / redistribution".
RESTRICTIVE_PATTERNS = [
    r"text\s+(and|or)\s+data\s+mining",
    r"machine\s+learning",
    r"artificial\s+intelligence\s+(training|purposes)",
    r"may\s+not\s+be\s+reproduced",
    r"without\s+(prior\s+)?written\s+permission",
    r"all\s+rights\s+reserved",
]
# Phrases that grant reuse
PERMISSIVE_PATTERNS = [r"creative\s+commons", r"\bCC[\s-]BY\b", r"open\s+access", r"public\s+domain"]

REGISTRY_COLUMNS = ["source_id", "title", "authors", "publisher", "document_type", "collection", "topic", "medications",
                    "raw_path", "source_url", "version", "publication_date", "revision_date", "retrieval_date", "sha256",
                    "pages", "licence", "licence_status", "redistribution_allowed", "scope_status",
                    "clinical_review_status", "clinical_reviewer", "clinical_review_date", "notes"]
LIST_COLUMNS = ("topic", "medications")
VALID_COLLECTIONS = (COLLECTION_PREVENTIVE, COLLECTION_MEDICATION, COLLECTION_APP)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan_licence(pdf_path: Path, pages_to_scan: int = 6) -> tuple[str, bool, bool]:
    """Scan the front and back matter for licence language.

    Returns (evidence_snippet, restrictive_found, permissive_found).
    Only front/back pages are scanned so citations in the reference list
    (e.g. a paper titled "Machine learning for ...") are not mistaken for licence terms.
    """
    doc = pymupdf.open(pdf_path)
    idx = list(range(min(pages_to_scan, doc.page_count)))
    idx += [i for i in range(max(0, doc.page_count - 2), doc.page_count) if i not in idx]
    text = "\n".join(doc[i].get_text() for i in idx)
    restrictive, permissive, snippet = False, False, ""
    # The match must sit next to licence vocabulary (not e.g. a journal called "Human Reproduction").
    licence_ctx = re.compile(r"(copyright|©|permission|licen[cs]e|\breuse\b)", re.I)
    for pat in RESTRICTIVE_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            window = text[max(0, m.start() - 300): m.end() + 300]
            if licence_ctx.search(window):
                restrictive = True
                snippet = snippet or re.sub(r"\s+", " ", window).strip()
    for pat in PERMISSIVE_PATTERNS:
        if re.search(pat, text, re.I):
            permissive = True
    return snippet[:600], restrictive, permissive


def read_registry(path: Path) -> list[dict]:
    """Read data/source_registry.csv. List-valued columns (topic, medications) use ';' as separator."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in LIST_COLUMNS:
            r[c] = [x.strip() for x in (r.get(c) or "").split(";") if x.strip()]
    return rows


def write_registry(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REGISTRY_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: ";".join(r[c]) if c in LIST_COLUMNS and isinstance(r.get(c), list) else r.get(c, "")
                        for c in REGISTRY_COLUMNS})


@dataclass
class GateDecision:
    source_id: str
    collection: str
    active: bool
    reasons: list            # why the source is NOT active (empty when active)
    checks: dict             # every individual check, for the gate report

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_source(row: dict, root: Path, require_clinical: bool | None = None, scan: bool = True) -> GateDecision:
    """Apply the activation gate to one registry row (see the module notes above)."""
    require_clinical = REQUIRE_CLINICAL_APPROVAL if require_clinical is None else require_clinical
    path = root / row["raw_path"] if row.get("raw_path") else None
    checks, reasons = {}, []
    checks["file_present"] = bool(path and path.exists())
    if not checks["file_present"]:
        reasons.append(f"raw file missing: {row.get('raw_path')}")
    if checks["file_present"]:
        digest = sha256_file(path)
        checks["sha256_matches_registry"] = bool(row.get("sha256")) and digest == row["sha256"]
        if not row.get("sha256"):
            reasons.append(f"no sha256 registered (file hash is {digest}); register it after review")
        elif digest != row["sha256"]:
            reasons.append("file content changed since registration (sha256 mismatch): re-review licence and "
                           "clinical status, then update the registry")
    checks["licence_permits_indexing"] = row.get("licence_status") in LICENCE_STATUSES_ALLOWED
    if not checks["licence_permits_indexing"]:
        reasons.append(f"licence_status={row.get('licence_status') or 'unknown'}")
    if scan and checks["file_present"] and path.suffix.lower() == ".pdf":
        snippet, restrictive, _ = scan_licence(path)
        checks["no_ml_restriction_detected"] = not restrictive
        if restrictive:
            reasons.append("automatic licence scan found a text/data-mining or ML restriction: " + snippet[:160])
    checks["in_scope"] = row.get("scope_status") == "in_scope"
    if not checks["in_scope"]:
        reasons.append(f"scope_status={row.get('scope_status')}")
    checks["valid_collection"] = row.get("collection") in VALID_COLLECTIONS
    if checks["in_scope"] and not checks["valid_collection"]:
        reasons.append(f"collection={row.get('collection')} is not an index collection")
    approved = row.get("clinical_review_status") == "APPROVED"
    checks["clinical_review_status"] = row.get("clinical_review_status") or "NOT_REVIEWED"
    if row.get("clinical_review_status") == "REJECTED":
        reasons.append("clinical review REJECTED this source")
    elif require_clinical and not approved:
        reasons.append("clinical approval required (VITALA_REQUIRE_CLINICAL_APPROVAL=1) but status is "
                       + checks["clinical_review_status"])
    return GateDecision(row["source_id"], row.get("collection", ""), not reasons, reasons, checks)


def evaluate_registry(paths: Paths, require_clinical: bool | None = None, scan: bool = True) -> list[GateDecision]:
    return [evaluate_source(r, paths.root, require_clinical, scan) for r in read_registry(paths.registry_csv)]


def active_sources(paths: Paths, require_clinical: bool | None = None, scan: bool = True) -> dict[str, dict]:
    """source_id -> registry row, for sources that pass the activation gate (in registry order)."""
    rows = {r["source_id"]: r for r in read_registry(paths.registry_csv)}
    return {d.source_id: rows[d.source_id] for d in evaluate_registry(paths, require_clinical, scan) if d.active}


# ====================================================================================================
# chunking
# Section-aware chunking of extracted guideline pages into JSONL-ready records.
#
# Rules:
#   * Headings (numbered "2.1 ...", ALL CAPS, or larger/bold short lines) open a new section.
#   * A chunk never crosses a section boundary.
#   * Tables are kept whole (split by rows with the header repeated only if very large).
#   * Numbered footnotes such as "(7) Check Fasting Blood Sugar ..." become their own unit,
#     because the SCPG checklists put the actual recommendations in those footnotes.
#   * Table-of-contents, acknowledgement/contributor lists and reference lists are not indexed
#     (they match many queries but contain no recommendations).
#   * Every chunk carries source id, version, PDF page, printed page, section path and a ready-made citation.
# ====================================================================================================
NUMBERED_HEADING_RE = re.compile(r"^(\d{1,2}(\.\d{1,2}){0,3})\s*[-–.)]?\s+[A-Z][^\n]{2,110}$")
CHAPTER_RE = re.compile(r"^(chapter|section|part)\s*[-–]?\s*[IVX\d]+", re.I)
FOOTNOTE_RE = re.compile(r"^\(\d{1,2}\)\s+\S")
SKIP_SECTION_RE = re.compile(
    r"^(\d[\d.]*\s*)?(references?|bibliography|acknowledge?ments?|acknowledgment|"
    r"([a-z]+\s+){0,3}(edition\s+)?contributors?|"
    r"table of contents|contents|list of (tables|figures)|scientific committee)\b", re.I)
# Upper-case numbered headings that are often glued to the paragraph after them in the
# Diabetes guideline, e.g. "13.4. DIETARY PATTERNS: Adopting a healthy dietary pattern ..."
INLINE_HEADING_RE = re.compile(r"^(\d{1,2}(\.\d{1,2}){0,3})\.?\s+([A-Z][A-Z0-9 ,&/()\-–']{3,90}?)(:|\n|$)")


def _split_inline_headings(blocks: list[Block]) -> list[Block]:
    """Split text blocks at lines that start with an upper-case numbered heading."""
    out = []
    for b in blocks:
        if b.kind != "text":
            out.append(b)
            continue
        cur: list[str] = []
        for line in b.text.splitlines():
            m = INLINE_HEADING_RE.match(line.strip())
            letters = [c for c in (m.group(3) if m else "") if c.isalpha()]
            if m and len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.9:
                if cur:
                    out.append(Block("text", "\n".join(cur), b.bbox, b.font_size, b.bold))
                    cur = []
                out.append(Block("text", (m.group(1) + " " + m.group(3)).strip(), b.bbox, b.font_size + 2, True))
                rest = line.strip()[m.end():].strip()
                if rest:
                    cur.append(rest)
            else:
                cur.append(line)
        if cur:
            out.append(Block("text", "\n".join(cur), b.bbox, b.font_size, b.bold))
    return out


def _is_strong_heading(text: str) -> bool:
    return bool(NUMBERED_HEADING_RE.match(text) or CHAPTER_RE.match(text) or INLINE_HEADING_RE.match(text)
                or re.match(r"^(foreword|preface|introduction|abbreviations?)\b", text, re.I))


@dataclass
class Unit:
    text: str
    kind: str          # text | table | footnote
    page: int
    printed: str


def _is_heading(b: Block, body_size: float) -> bool:
    t = b.text.strip()
    if b.kind != "text" or "\n" in t and len(t) > 120:
        return False
    first = t.splitlines()[0].strip()
    if len(first) < 3 or len(first) > 120 or first.endswith((".", ",", ";")) and not NUMBERED_HEADING_RE.match(first):
        return False
    if NUMBERED_HEADING_RE.match(first) or CHAPTER_RE.match(first):
        return True
    letters = [c for c in first if c.isalpha()]
    if len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.85 and len(t) < 90:
        return True
    return (b.font_size >= body_size + 1.5 or b.bold) and len(t) < 90 and len(t.split()) <= 14


def _heading_level(text: str) -> int:
    m = NUMBERED_HEADING_RE.match(text)
    if m:
        return m.group(1).count(".") + 1
    return 1


def _split_long(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.;:])\s+|\n", text):
        if len(cur) + len(sent) + 1 > limit and cur:
            parts.append(cur.strip())
            cur = ""
        cur += sent + " "
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _split_table(md: str, limit: int) -> list[str]:
    lines = md.splitlines()
    if len(md) <= limit or len(lines) < 4:
        return [md]
    head, rows = lines[:2], lines[2:]
    out, cur = [], list(head)
    for r in rows:
        if sum(len(x) for x in cur) + len(r) > limit and len(cur) > 2:
            out.append("\n".join(cur))
            cur = list(head)
        cur.append(r)
    out.append("\n".join(cur))
    return out


CAPTION_RE = re.compile(r"^(Table|Figure)\s*\d+[.:]?\s+\S", re.I)


def linearize_table(md: str) -> str:
    """Markdown table -> 'Header: value; Header: value' lines. Embeddings and BM25 match these far better than
    pipe-separated cells (e.g. 'Test: HbA1c; Normal: < 5.7; Prediabetes: 5.7 – 6.4; Diabetes: ≥6.5')."""
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in md.splitlines()
            if l.strip().startswith("|") and not re.match(r"^\|[-| ]+\|$", l.strip())]
    if len(rows) < 2:
        return md
    if any(re.search(r"\d|[<>≥≤]", h) for h in rows[0]):
        # the detected "header" is really a data row (e.g. "Normal | <120 mm Hg | and | <80 mm Hg"):
        # do not use its cells as labels
        return "\n".join("; ".join(c for c in r if c) for r in rows if any(r))
    header, out, last_first = rows[0], [], ""
    for r in rows[1:]:
        if r and r[0]:
            last_first = r[0]
        cells = [f"{h}: {v}" if h else v for h, v in zip(header, r) if v]
        if cells:
            prefix = f"[{last_first}] " if r and not r[0] and last_first else ""
            out.append(prefix + "; ".join(cells))
    return "\n".join(out)


FRAGMENT_MAX_CHARS = 200


def merge_fragments(chunks: list[dict], max_chars: int = FRAGMENT_MAX_CHARS) -> tuple[list[dict], int]:
    """Merge tiny text fragments (sentence remnants, captions, abbreviation legends) into a neighbouring chunk on the
    same page. BM25 length normalisation strongly favours very short chunks, so a 175-character abbreviation legend
    would otherwise outrank the passage it belongs to. Numbered footnotes and tables are kept as they are (they are
    short but self-contained facts). Captions ("Table 5 ...") merge forward into the chunk they introduce."""
    out, merged = [], 0
    for i, c in enumerate(chunks):
        tiny = c["chunk_type"] == "text" and len(c["text"]) < max_chars
        if not tiny:
            out.append(c)
            continue
        nxt = chunks[i + 1] if i + 1 < len(chunks) else None
        squash = lambda s: re.sub(r"\s+", " ", s).strip()
        if nxt and squash(c["text"]) in squash(nxt["text"]):
            merged += 1                  # already contained in the next chunk (chunk overlap): drop the fragment
            continue
        if CAPTION_RE.match(c["text"]) and nxt and nxt["pdf_page_start"] == c["pdf_page_end"] \
                and len(nxt["text"]) + len(c["text"]) < CHUNK_MAX_CHARS:
            nxt["text"] = c["text"] + "\n" + nxt["text"]
            nxt["text_for_embedding"] = nxt["text_for_embedding"].replace("\n", "\n" + c["text"] + "\n", 1)
            merged += 1
            continue
        prev = out[-1] if out else None
        if prev and prev["pdf_page_end"] == c["pdf_page_start"] and prev["chunk_type"] in ("text", "footnote") \
                and len(prev["text"]) + len(c["text"]) < CHUNK_MAX_CHARS:
            prev["text"] += "\n" + c["text"]
            prev["text_for_embedding"] += "\n" + c["text"]
            prev["char_len"] = len(prev["text"])
            prev["extraction_warnings"] = sorted(set(prev["extraction_warnings"]) | set(c["extraction_warnings"]))
            merged += 1
            continue
        out.append(c)                    # nothing suitable on the same page: keep it
    return out, merged


def citation_for(src: dict, page_start: int, page_end: int, printed: str, section: str) -> str:
    pages = f"PDF p. {page_start}" if page_start == page_end else f"PDF pp. {page_start}-{page_end}"
    if printed:
        pages += f" (printed p. {printed})"
    sec = f", section: {section}" if section else ""
    return f"{src['title']} ({src['version']}), {pages}{sec}"


def chunk_document(src: dict, pages: list[PageRecord], body_size: float) -> tuple[list[dict], dict]:
    """src is one source-registry row (dict). Returns (chunks, stats)."""
    stats = {"skipped_pages_toc": 0, "skipped_units_section": 0, "units": 0}
    section_stack: list[tuple[int, str]] = []
    skip_section = False
    sections: list[tuple[str, bool, list[Unit]]] = []   # (section_path, skip, units)
    cur_units: list[Unit] = []

    def flush():
        nonlocal cur_units
        if cur_units:
            path = " > ".join(t for _, t in section_stack)
            sections.append((path, skip_section, cur_units))
        cur_units = []

    for p in pages:
        if p.flags.get("toc_like"):
            stats["skipped_pages_toc"] += 1
            continue
        for b in _split_inline_headings(p.blocks):
            if _is_heading(b, body_size):
                head = re.sub(r"\s+", " ", b.text).strip()
                # Inside a skipped section (e.g. acknowledgements) bold names look like headings;
                # only a strong heading ends the skipped section.
                if skip_section and not _is_strong_heading(head):
                    cur_units.append(Unit(b.text, "text", p.pdf_page, p.printed_page))
                    continue
                flush()
                lvl = _heading_level(head)
                while section_stack and section_stack[-1][0] >= lvl:
                    section_stack.pop()
                section_stack.append((lvl, head[:120]))
                skip_section = bool(SKIP_SECTION_RE.match(head))
                continue
            kind = b.kind
            if kind == "text" and FOOTNOTE_RE.match(b.text):
                kind = "footnote"
            cur_units.append(Unit(b.text, kind, p.pdf_page, p.printed_page))
            stats["units"] += 1
    flush()

    chunks = []
    for path, skip, units in sections:
        if skip:
            stats["skipped_units_section"] += len(units)
            continue
        buf: list[Unit] = []

        def emit(group: list[Unit], kind: str):
            text = "\n".join(u.text for u in group).strip()
            if len(text) < 40:      # page furniture, stray labels
                return
            pieces = _split_table(text, CHUNK_MAX_CHARS) if kind == "table" else _split_long(text, CHUNK_MAX_CHARS)
            for piece in pieces:
                chunks.append(_make_chunk(src, piece, kind, group, path))

        for u in units:
            if u.kind in ("table", "footnote"):
                caption = None
                if u.kind == "table" and buf:
                    # a "Table 3 Categories of BP ..." line just before the table belongs to the table
                    last_line = buf[-1].text.strip().splitlines()[-1] if buf[-1].text.strip() else ""
                    if CAPTION_RE.match(last_line):
                        caption = last_line
                if buf:
                    emit(buf, "text")
                    buf = []
                if caption:
                    u = Unit(caption + "\n" + u.text, u.kind, u.page, u.printed)
                emit([u], u.kind)
                continue
            if buf and sum(len(x.text) for x in buf) + len(u.text) > CHUNK_TARGET_CHARS:
                emit(buf, "text")
                tail = buf[-1]
                buf = [tail] if len(tail.text) <= CHUNK_OVERLAP_CHARS else []
            buf.append(u)
        if buf:
            emit(buf, "text")

    # stable ids
    for i, c in enumerate(chunks):
        c["chunk_id"] = f"{src['source_id']}::p{c['pdf_page_start']:03d}::{i:04d}"
    return chunks, stats


def _make_chunk(src: dict, text: str, kind: str, group: list[Unit], section: str) -> dict:
    p0, p1 = group[0].page, group[-1].page
    printed = group[0].printed
    warnings = []
    if kind == "table":
        warnings.append("table_extracted_verify_against_pdf")
    n_thresh = len(NUMERIC_THRESHOLD_RE.findall(text))
    if n_thresh:
        warnings.append("contains_numeric_thresholds")
    if RESIDUAL_GARBLE_RE.search(text):
        warnings.append("possible_garbled_text")
    if "≥" in text and src["source_id"] == "SA-PHA-DM-2025":
        warnings.append("contains_repaired_geq_glyph_verify")
    header = f"{src['title']} | {section}" if section else src["title"]
    embed_body = text
    if kind == "table":
        lines = text.splitlines()
        cap = lines[0] if lines and CAPTION_RE.match(lines[0]) else ""
        embed_body = (cap + "\n" if cap else "") + linearize_table("\n".join(lines[1:] if cap else lines))
    return {
        "chunk_id": "",
        "collection": src["collection"],
        "source_id": src["source_id"],
        "source_type": src["source_type"],
        "title": src["title"],
        "publisher": src["publisher"],
        "version": src["version"],
        "filename": src["filename"],
        "sha256": src["sha256"],
        "pdf_page_start": p0,
        "pdf_page_end": p1,
        "printed_page": printed,
        "section_path": section,
        "chunk_type": kind,
        "text": text,
        "text_for_embedding": f"{header}\n{embed_body}",
        "char_len": len(text),
        "numeric_threshold_count": n_thresh,
        "extraction_warnings": warnings,
        "needs_clinical_review": bool(warnings),
        "citation": citation_for(src, p0, p1, printed, section),
        "url": "",
        "pipeline_version": PIPELINE_VERSION,
    }


# ====================================================================================================
# fda
# Official FDA drug-label collection through the openFDA drug label API.
#
# Principles:
#   * Labels are fetched ONLY by the exact SPL set_id from the manifest. No search-and-pick,
#     no silent substitution: if the set_id does not resolve, the drug is reported as failed.
#   * Identity is validated (active ingredient, single-ingredient product, human Rx, oral route).
#   * Text is stored verbatim. "Monitoring" is not an openFDA field, so we derive it by quoting
#     label sentences that mention monitoring/testing, and we record which section each came from.
#   * Dosage text is stored in the structured record but NOT indexed for the chatbot, so the bot
#     cannot be pulled into dose recommendations.
# ====================================================================================================
OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
DAILYMED_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}"

# openFDA field -> human-readable section name. Both PLR (new) and older label formats.
INDEXED_FIELDS = {
    "boxed_warning": "Boxed Warning",
    "indications_and_usage": "Indications and Usage",
    "contraindications": "Contraindications",
    "warnings_and_cautions": "Warnings and Precautions",
    "warnings": "Warnings",
    "precautions": "Precautions",
    "adverse_reactions": "Adverse Reactions",
    "drug_interactions": "Drug Interactions",
    "use_in_specific_populations": "Use in Specific Populations",
    "pregnancy": "Pregnancy",
    "lactation": "Lactation",
    "pediatric_use": "Pediatric Use",
    "geriatric_use": "Geriatric Use",
    "mechanism_of_action": "Mechanism of Action",
    "information_for_patients": "Patient Counseling Information",
    "spl_patient_package_insert": "Patient Information (Patient Package Insert)",
}
STORED_NOT_INDEXED = ["dosage_and_administration", "dosage_forms_and_strengths", "overdosage",
                      "description", "clinical_pharmacology", "how_supplied", "storage_and_handling"]
# dosage_and_administration is deliberately NOT a source: it would pull dose-titration text into the index
MONITORING_SOURCE_FIELDS = ["boxed_warning", "warnings_and_cautions", "warnings", "precautions",
                            "use_in_specific_populations", "information_for_patients"]
DOSE_SENTENCE_RE = re.compile(r"\b(\d+\s*mg|increase (the )?dos|titrat|maximum (recommended )?dose)\b", re.I)
MONITORING_RE = re.compile(
    r"\b(monitor\w*|measur\w+|assess\w*|evaluat\w+|check\w*|test(s|ing)?|periodic\w*|obtain\w*)\b[^.]{0,200}?"
    r"\b(renal|kidney|eGFR|creatinine|hepatic|liver|enzyme|transaminase|ALT|AST|vitamin B12|B12|hematolog|"
    r"blood pressure|lipid|LDL|CK|creatine kinase|glucose|HbA1c|A1C|potassium|heart rate)\b", re.I)


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    # openFDA prefixes most fields with the section number+title, e.g. "5 WARNINGS AND PRECAUTIONS 5.1 ..."
    return s


def fetch_label(set_id: str, retries: int = 3, timeout: int = 30, api_key: str | None = None) -> dict:
    params = {"search": f'set_id:"{set_id}"', "limit": 1}
    if api_key:
        params["api_key"] = api_key
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(OPENFDA_LABEL_URL, params=params, timeout=timeout)
            if r.status_code == 404:
                raise LookupError(f"openFDA returned no label for set_id {set_id}")
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            if len(results) != 1:
                raise LookupError(f"Expected exactly 1 label for set_id {set_id}, got {len(results)}")
            return {"meta": data.get("meta", {}), "label": results[0], "request_url": r.url}
        except LookupError:
            raise
        except Exception as exc:  # network / 5xx -> retry
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"openFDA request failed for {set_id}: {last}")


def validate_label(label: dict, spec: dict) -> dict:
    """spec comes from the manifest: drug, set_id, expected_active_ingredient, optional expected fields."""
    errors, warnings = [], []
    o = label.get("openfda", {})
    if label.get("set_id") != spec["set_id"]:
        errors.append(f"set_id mismatch: got {label.get('set_id')}")
    expected = spec["expected_active_ingredient"].upper()
    substances = [s.upper() for s in o.get("substance_name", [])]
    generics = [g.upper() for g in o.get("generic_name", [])]
    base = expected.split()[0]   # METFORMIN / AMLODIPINE / ATORVASTATIN
    if not any(base in s for s in substances + generics):
        errors.append(f"active ingredient {expected} not found (substance={substances}, generic={generics})")
    if len(substances) > 1:
        errors.append(f"combination product (substances={substances}); a single-ingredient label is required")
    if generics and any(" AND " in g for g in generics):
        errors.append(f"combination product by generic name: {generics}")
    if "HUMAN PRESCRIPTION DRUG" not in o.get("product_type", []):
        errors.append(f"not a human prescription label: {o.get('product_type')}")
    if o.get("route") and "ORAL" not in o.get("route", []):
        errors.append(f"route is not oral: {o.get('route')}")
    for key in ("expected_application_number", "expected_spl_id", "expected_version"):
        if spec.get(key):
            got = {"expected_application_number": (o.get("application_number") or [""])[0],
                   "expected_spl_id": label.get("id"), "expected_version": label.get("version")}[key]
            if str(got) != str(spec[key]):
                # a newer SPL version under the same set_id is a label UPDATE, not a different product
                (warnings if key in ("expected_spl_id", "expected_version") else errors).append(
                    f"{key}: manifest={spec[key]} fetched={got}")
    if not label.get("indications_and_usage"):
        errors.append("label has no indications_and_usage section")
    for f in ("boxed_warning", "contraindications", "adverse_reactions", "drug_interactions"):
        if not label.get(f):
            warnings.append(f"field missing in label: {f} (recorded as missing, not filled in)")
    if not (label.get("warnings_and_cautions") or label.get("warnings")):
        warnings.append("no warnings section found")
    return {"passed": not errors, "errors": errors, "warnings": warnings}


def extract_monitoring(label: dict) -> list[dict]:
    out, seen = [], set()
    for f in MONITORING_SOURCE_FIELDS:
        for txt in label.get(f, []):
            for sent in re.split(r"(?<=[.])\s+(?=[A-Z])", _clean(txt)):
                if (MONITORING_RE.search(sent) and not DOSE_SENTENCE_RE.search(sent)
                        and sent not in seen and len(sent) < 600):
                    seen.add(sent)
                    out.append({"source_field": f, "source_section": INDEXED_FIELDS.get(f, f.replace("_", " ").title()),
                                "text": sent})
    return out


def build_record(spec: dict, fetched: dict, raw_path: Path, manifest_status: str) -> dict:
    label = fetched["label"]
    o = label.get("openfda", {})
    validation = validate_label(label, spec)
    sections = {}
    for f, name in INDEXED_FIELDS.items():
        if label.get(f):
            sections[f] = {"name": name, "text": "\n".join(_clean(t) for t in label[f])}
    stored = {f: "\n".join(_clean(t) for t in label[f]) for f in STORED_NOT_INDEXED if label.get(f)}
    brand = (o.get("brand_name") or [spec["drug"]])[0]
    generic = (o.get("generic_name") or [spec["expected_active_ingredient"]])[0]
    raw_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    return {
        "source_id": f"FDA-LABEL-{spec['drug'].upper()}",
        "drug": spec["drug"].lower(),
        "title": f"{generic.title()} ({brand}) - FDA prescribing information",
        "brand_name": brand,
        "generic_name": generic,
        "manufacturer": (o.get("manufacturer_name") or [""])[0],
        "application_number": (o.get("application_number") or [""])[0],
        "substance_name": o.get("substance_name", []),
        "set_id": label["set_id"],
        "spl_id": label.get("id"),
        "spl_version": label.get("version"),
        "effective_time": label.get("effective_time", ""),
        "dailymed_url": DAILYMED_URL.format(set_id=label["set_id"]),
        "openfda_request_url": fetched["request_url"],
        "openfda_last_updated": fetched["meta"].get("last_updated"),
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "manifest_status": manifest_status,
        "raw_file": raw_path.name,
        "raw_sha256": raw_sha,
        "validation": validation,
        "sections": sections,
        "monitoring_extract": extract_monitoring(label),
        "stored_not_indexed": stored,
        "missing_fields": [f for f in INDEXED_FIELDS if not label.get(f)],
        "clinical_review_status": "NOT_REVIEWED",
    }


SUBSECTION_RE = re.compile(r"(?=(?<![\d.])\b\d{1,2}\.\d{1,2}\s+[A-Z][a-z])")


def medication_chunks(rec: dict, max_chars: int = 1600) -> list[dict]:
    chunks = []

    def add(section_name: str, field: str, text: str):
        pieces = []
        for part in SUBSECTION_RE.split(text):
            part = part.strip()
            if not part:
                continue
            while len(part) > max_chars:
                cut = part.rfind(". ", 0, max_chars)
                cut = cut + 1 if cut > 200 else max_chars
                pieces.append(part[:cut].strip())
                part = part[cut:].strip()
            if part:
                pieces.append(part)
        # merge very small pieces with the next one
        merged = []
        for p in pieces:
            if merged and len(merged[-1]) < 250:
                merged[-1] = merged[-1] + " " + p
            else:
                merged.append(p)
        for p in merged:
            sub = re.match(r"^(\d{1,2}\.\d{1,2}\s+[A-Z][\w ,/()-]{2,60}?)(?=\s[A-Z][a-z]|\s\[|:)", p)
            sec = section_name + (f" > {sub.group(1)}" if sub else "")
            idx = len(chunks)
            chunks.append({
                "chunk_id": f"{rec['source_id']}::{field}::{idx:03d}",
                "collection": COLLECTION_MEDICATION,
                "source_id": rec["source_id"],
                "source_type": "fda_drug_label",
                "drug": rec["drug"],
                "title": rec["title"],
                "publisher": "U.S. Food and Drug Administration (openFDA)",
                "version": f"SPL v{rec['spl_version']}, effective {rec['effective_time']}",
                "filename": rec["raw_file"],
                "sha256": rec["raw_sha256"],
                "pdf_page_start": None, "pdf_page_end": None, "printed_page": "",
                "section_path": sec,
                "label_field": field,
                "chunk_type": "label_section" if field != "monitoring_extract" else "derived_monitoring_quotes",
                "text": p,
                "text_for_embedding": f"{rec['generic_name']} ({rec['brand_name']}) drug label | {sec}\n{p}",
                "char_len": len(p),
                "numeric_threshold_count": 0,
                "extraction_warnings": ["derived_section_verbatim_quotes"] if field == "monitoring_extract" else [],
                "needs_clinical_review": True,
                "citation": f"FDA label: {rec['title']} (set ID {rec['set_id']}, version {rec['spl_version']}, effective {rec['effective_time']}), section: {sec}",
                "url": rec["dailymed_url"],
                "pipeline_version": PIPELINE_VERSION,
            })

    for field, s in rec["sections"].items():
        add(s["name"], field, s["text"])
    if rec["monitoring_extract"]:
        text = "\n".join(f"[{m['source_section']}] {m['text']}" for m in rec["monitoring_extract"])
        add("Monitoring-related statements (verbatim quotes from the label)", "monitoring_extract", text)
    return chunks


def load_manifest(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ====================================================================================================
# medication knowledge PDFs: the Saudi medication knowledge base and the StatPearls reviews
#
# Both parsers work from PyMuPDF span fonts (sizes / bold), which are regular in these documents, and keep the
# PDF page of every paragraph so each chunk can be traced back to the exact page.
#   * Saudi medication KB: one chunk per record "KSA-MED-NNNN · Title" (the document's own stable identifiers),
#     with its numbered section, the cited source IDs (S001...) resolved to the URLs in the document's source
#     registry, and borderless tables rebuilt from cell positions.
#   * StatPearls: one chunk per ~1,200 characters inside each section / sub-section; reference markers such as
#     [12] are removed (they are not evidence); exact duplicate paragraphs are dropped and reported.
# Dose-titration content is tagged content_type="dosing_reference" and kept out of the active index unless
# VITALA_INDEX_DOSING=1, following the FDA-label policy above (the chatbot must not be pulled into dosing advice).
# ====================================================================================================
INDEX_DOSING_REFERENCE = os.environ.get("VITALA_INDEX_DOSING", "0") == "1"
ZERO_WIDTH_RE = re.compile(r"[​‌‍﻿]")
REF_MARKER_RE = re.compile(r"\s?(\[\d{1,3}\])+")
URL_FRAGMENT_RE = re.compile(r"^https?:|%2[0-9A-F]|#:~:text=|^\S{40,}$")
MED_NAME_RE = {
    "metformin": re.compile(r"\bmetformin|glucophage|biguanide", re.I),
    ACE_INHIBITOR_CLASS: re.compile(r"\bACE[- ]?inhibitor|angiotensin[- ]converting[- ]enzyme inhibit|\bACEi\b", re.I),
    **{m: re.compile(rf"\b{m}", re.I) for m in ACE_INHIBITOR_MEMBERS},
}

# Saudi KB: numbered section -> medications the section is about ([] = general diabetes / hypertension content).
MEDKB_SECTION_MEDS = {1: [], 2: [], **{n: ["metformin"] for n in range(3, 14)},
                      **{n: [ACE_INHIBITOR_CLASS] for n in (14, 15, 16, 17, 18, 19, 25, 26, 28)},
                      20: ["lisinopril"], 21: ["enalapril"], 22: ["ramipril"], 23: ["captopril"], 24: ["perindopril"],
                      27: ["metformin"], 29: []}
# Records that are dose-titration / maximum-dose references (see INDEX_DOSING_REFERENCE).
MEDKB_DOSING_RECORDS = {"KSA-MED-0046", "KSA-MED-0049", "KSA-MED-0129", "KSA-MED-0130", "KSA-MED-0133", "KSA-MED-0134",
                        "KSA-MED-0138", "KSA-MED-0139", "KSA-MED-0140", "KSA-MED-0145", "KSA-MED-0149", "KSA-MED-0150"}
# StatPearls (H2, H3) sections that are dose-titration references.
STATPEARLS_DOSING_SECTIONS = {
    ("Administration", "Available Dosage Forms"), ("Administration", "General Dosing Information"),
    ("Administration", "ACE Inhibitors are Classified into Three Groups According to Chemical Structure"),
    ("Administration", ""), ("Administration", "Recommended Adult Dosages"), ("Administration", "Treatment of Type 2 Diabetes"),
    ("Administration", "Off-Labeled Uses"), ("Administration", "Prevention of Type 2 Diabetes"),
    ("Administration", "Treatment of Antipsychotic-Induced Weight Gain"), ("Administration", "Treatment of Gestational Diabetes"),
    ("Administration", "Treatment of Oligomenorrhea due to PCOS"), ("Tables", ""),
}
STATPEARLS_SKIP_H2 = {"Continuing Education Activity", "Review Questions", "References", "Figures"}
# Known source problems found while building the knowledge base (shown in the clinical review queue).
KNOWN_ISSUES = {
    "STATPEARLS-METFORMIN-2023": [
        (re.compile(r"half-life is\s+about 20 hours", re.I),
         "Internal inconsistency: half-life 'about 20 hours' here vs 'approximately 6.2 hours' in Pharmacokinetics."),
        (re.compile(r"Standards of Medical Care in Diabetes 2018|ACOG\)? guidelines", re.I),
         "Cites superseded guidance (2018); check against current ADA / Saudi guidance (SA-MEDKB-2026)."),
    ],
    "STATPEARLS-ACEI-2025": [
        (re.compile(r"maximum of 450 mg", re.I),
         "Internal inconsistency: captopril maximum 450 mg in the text vs 150 mg/day in the dosing table."),
        (re.compile(r"except for enalapril, which can be given intravenously", re.I),
         "Imprecise: the intravenous form is enalaprilat (see SA-MEDKB-2026 KSA-MED-0135)."),
    ],
}


def tag_medications(text: str, base: list[str] | None = None) -> list[str]:
    """Medications a chunk is about: the section's own medications plus any in-scope medicine it names."""
    found = list(base or [])
    for med, rx in MED_NAME_RE.items():
        if med not in found and rx.search(text):
            found.append(med)
    return found


def _spans(page) -> list[dict]:
    """Lines of a page as dicts with text, size, bold, font, bbox (PyMuPDF 'dict' output)."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for i, line in enumerate(b.get("lines", [])):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = ZERO_WIDTH_RE.sub("", "".join(s["text"] for s in spans)).strip()
            out.append({"text": text, "size": round(spans[0]["size"], 1), "font": spans[0]["font"],
                        "bold": bool(spans[0]["flags"] & 16) or "Bold" in spans[0]["font"],
                        "all_bold": all(bool(s["flags"] & 16) or "Bold" in s["font"] for s in spans),
                        "bbox": tuple(line["bbox"]), "block": b["number"], "first_in_block": i == 0})
    return out


def _join_lines(lines: list[str]) -> str:
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not out:
            out = ln
        elif out.endswith("-") and ln[:1].islower():
            out += ln                       # "renin-" + "angiotensin"
        else:
            out += " " + ln
    return re.sub(r"\s+", " ", out).strip()


def _layout_table(cells: list[dict]) -> list[list[str]]:
    """Rebuild a borderless table from its cell lines: columns from the header row, rows from vertical gaps."""
    cells = sorted(cells, key=lambda c: (round(c["bbox"][1], 0), c["bbox"][0]))
    rows, cur, cur_y1 = [], [], None
    for c in cells:
        if cur and c["bbox"][1] > cur_y1 + 3:
            rows.append(cur)
            cur = []
        cur.append(c)
        cur_y1 = max(cur_y1 or 0, c["bbox"][3]) if len(cur) > 1 else c["bbox"][3]
    if cur:
        rows.append(cur)
    header_x = sorted({round(c["bbox"][0]) for c in rows[0]})
    table = []
    for row in rows:
        cols = [[] for _ in header_x]
        for c in sorted(row, key=lambda c: c["bbox"][1]):
            col = max(i for i, x in enumerate(header_x) if c["bbox"][0] >= x - 6) if c["bbox"][0] >= header_x[0] - 6 else 0
            cols[col].append(c["text"])
        table.append([_join_lines(x) for x in cols])
    return table


def _rows_to_markdown(rows: list[list[str]]) -> str:
    head, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def parse_saudi_medkb(path: Path) -> tuple[list[dict], dict]:
    """Saudi medication knowledge base PDF -> one unit per KSA-MED record (+ the document's source registry)."""
    doc = pymupdf.open(path)
    records, sources, section, cur = [], {}, (0, ""), None
    in_registry, reg_cur = False, None
    record_re = re.compile(r"^(KSA-MED-\d{4})\s*[·•·�]\s*(.+)$")
    section_re = re.compile(r"^(\d{1,2})\.\s+(.+)$")
    src_line_re = re.compile(r"^(S\d{3})\s*[·•·�]\s*(.+)$")

    def close():
        nonlocal cur
        if cur:
            records.append(cur)
        cur = None

    for pno in range(doc.page_count):
        page_no = pno + 1
        lines = _spans(doc[pno])
        table_cells = []
        for ln in lines:
            t = ln["text"]
            if ln["size"] <= 7.0 and (t.startswith("Saudi medication knowledge base") or t.isdigit()):
                continue                                   # running header / page number
            if ln["size"] >= 14.0 and ln["bold"]:
                if table_cells and cur:
                    cur["tables"].append(_layout_table(table_cells))
                    table_cells = []
                close()
                if t.strip().lower() == "source registry":
                    in_registry = True
                    continue
                m = section_re.match(t)
                section = (int(m.group(1)), m.group(2).strip()) if m else (0, t.strip())
                continue
            if in_registry:
                m = src_line_re.match(t)
                if m:
                    reg_cur = {"id": m.group(1), "citation": m.group(2).strip(), "url": ""}
                    sources[m.group(1)] = reg_cur
                elif reg_cur and t.startswith("http"):
                    reg_cur["url"] = (reg_cur["url"] + t).strip()
                elif reg_cur and reg_cur["url"] and not t.startswith("http"):
                    reg_cur["url"] += t if not re.search(r"\s", t) else ""
                elif reg_cur:
                    reg_cur["citation"] += " " + t
                continue
            m = record_re.match(t) if ln["bold"] and ln["size"] >= 10 else None
            if m:
                if table_cells and cur:
                    cur["tables"].append(_layout_table(table_cells))
                    table_cells = []
                close()
                cur = {"record_id": m.group(1), "title": m.group(2).strip(), "section_number": section[0],
                       "section_title": section[1], "page_start": page_no, "page_end": page_no, "paragraphs": [],
                       "tables": [], "source_ids": []}
                continue
            if cur is None:
                continue                                   # title page / "Use and evidence boundaries" (not clinical content)
            cur["page_end"] = page_no
            if t.startswith("Sources:"):
                if table_cells:
                    cur["tables"].append(_layout_table(table_cells))
                    table_cells = []
                cur["source_ids"] += re.findall(r"S\d{3}", t)
                continue
            if 7.9 <= ln["size"] <= 8.3:
                table_cells.append(ln)                     # borderless table cell line
                continue
            if ln["first_in_block"] or not cur["paragraphs"]:
                cur["paragraphs"].append([t])
            else:
                cur["paragraphs"][-1].append(t)
        if table_cells and cur:
            cur["tables"].append(_layout_table(table_cells))
    close()
    for s in sources.values():
        s["url"] = ZERO_WIDTH_RE.sub("", s["url"]).strip()
        s["citation"] = re.sub(r"\s+", " ", s["citation"]).strip()
    units = []
    for r in records:
        body = "\n".join(_join_lines(p) for p in r["paragraphs"])
        md_tables = [_rows_to_markdown(t) for t in r["tables"] if len(t) > 1]
        text = "\n".join(x for x in [body] + md_tables if x)
        units.append({**{k: v for k, v in r.items() if k not in ("paragraphs", "tables")}, "text": text,
                      "has_table": bool(md_tables),
                      "references": [{"id": s, **{k: v for k, v in sources.get(s, {}).items() if k != "id"}}
                                     for s in dict.fromkeys(r["source_ids"])]})
    return units, {"records": len(units), "source_registry_entries": len(sources),
                   "records_without_sources": [u["record_id"] for u in units if not u["references"]]}


def parse_statpearls(path: Path) -> tuple[list[dict], dict]:
    """StatPearls article PDF -> paragraphs with (H2, H3) section and PDF page; tables from the 'Tables' section."""
    doc = pymupdf.open(path)
    body_size = statistics.mode([ln["size"] for p in doc for ln in _spans(p) if "Times" in ln["font"]])
    paras, h2, h3, title, seen, dropped = [], "", "", "", set(), []
    started = False
    for pno in range(doc.page_count):
        page_no = pno + 1
        lines = _spans(doc[pno])
        for ln in lines:
            t = ln["text"]
            if "Georgia" in ln["font"] or ln["size"] < body_size - 2:
                continue                                    # NCBI header/footer, licence footer, superscripts
            if "Arial" in ln["font"] and ln["bold"] and ln["size"] >= 13.5:
                title = title or t
                continue
            if "Arial" in ln["font"] and ln["bold"] and ln["size"] >= body_size + 1:
                h2, h3, started = t.strip(), "", True       # section heading (12.6 pt)
                continue
            if not started or "Arial" in ln["font"]:
                continue                                    # authors / affiliations block before the first section
            if h2 in STATPEARLS_SKIP_H2 or h2 == "Tables":
                continue
            if ln["all_bold"] and ln["first_in_block"]:
                h3 = t.strip().rstrip(":")                   # sub-heading on its own line
                continue
            if URL_FRAGMENT_RE.search(t) or t.lower().startswith("access free multiple choice") or \
                    t.lower().startswith("comment on this article"):
                continue
            new_para = ln["first_in_block"] or not paras or paras[-1]["page_block"] != (page_no, ln["block"])
            continues = (new_para and paras and paras[-1]["page"] == page_no - 1 and t[:1].islower()
                         and not re.search(r"[.:;!?)]$", paras[-1]["lines"][-1]))
            if continues:                                   # paragraph broken by a page break
                paras[-1]["lines"].append(t)
                paras[-1]["page_block"] = (page_no, ln["block"])
                paras[-1]["page_end"] = page_no
            elif new_para:
                paras.append({"h2": h2, "h3": h3, "page": page_no, "page_end": page_no,
                              "page_block": (page_no, ln["block"]), "lines": [t]})
            else:
                paras[-1]["lines"].append(t)
    out, near = [], []
    for p in paras:
        text = REF_MARKER_RE.sub("", _join_lines(p["lines"])).strip()
        if len(text) < 3:
            continue
        key = re.sub(r"\W+", " ", text.lower()).strip()
        if key in seen and len(key) > 80:
            dropped.append({"page": p["page"], "section": f"{p['h2']} > {p['h3']}", "text": text[:120]})
            continue
        sh = _shingles(text)
        for prev in out:
            j = len(sh & prev["_sh"]) / len(sh | prev["_sh"]) if sh and prev["_sh"] else 0.0
            if j >= 0.5 and len(key) > 200:
                near.append({"page": p["page"], "similar_to_page": prev["page"], "jaccard": round(j, 2),
                             "text": text[:100]})
        seen.add(key)
        out.append({"h2": p["h2"], "h3": p["h3"], "page": p["page"], "page_end": p["page_end"], "text": text, "_sh": sh})
    for o in out:
        o.pop("_sh")
    tables = []
    for pno in range(doc.page_count):
        page_text = doc[pno].get_text()
        if not re.search(r"^\s*Tables\s*$", page_text, re.M):
            continue
        for t in doc[pno].find_tables().tables:
            rows = [[re.sub(r"\s+", " ", c or "").strip() for c in r] for r in t.extract()]
            rows = [r for r in rows if any(r) and not (r[1:2] == ["Tables"] or r[:2] == ["", "Tables"])]
            keep = [i for i in range(len(rows[0])) if any(r[i] for r in rows)]
            rows = [[r[i] for i in keep] for r in rows]
            if len(rows) > 1:
                tables.append({"page": pno + 1, "rows": rows})
    return out, {"title": title, "body_font_size": body_size, "paragraphs": len(out), "tables": len(tables),
                 "duplicate_paragraphs_dropped": dropped, "near_duplicate_paragraphs": near, "_tables": tables}


def statpearls_chunks(row: dict, path: Path, target: int = 1200) -> tuple[list[dict], dict]:
    paras, rep = parse_statpearls(path)
    tables = rep.pop("_tables")
    slug = lambda s: re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "section"
    chunks, buf = [], []

    def flush():
        if not buf:
            return
        h2, h3s = buf[0]["h2"], list(dict.fromkeys(p["h3"] for p in buf if p["h3"]))
        text = "\n".join(p["text"] for p in buf)
        dosing = all((p["h2"], p["h3"]) in STATPEARLS_DOSING_SECTIONS for p in buf)
        n = sum(1 for c in chunks if c["_h2"] == h2)
        chunks.append({"_h2": h2, "chunk_id": f"{row['source_id']}::{slug(h2)}::{n:02d}", "heading": h2,
                       "section_path": h2 + (f" > {'; '.join(h3s)}" if h3s else ""),
                       "pdf_page_start": min(p["page"] for p in buf), "pdf_page_end": max(p["page_end"] for p in buf),
                       "text": text, "chunk_type": "text", "content_type": "dosing_reference" if dosing else "clinical"})
        buf.clear()

    split = []
    for p in paras:                                   # very long paragraphs: split at sentence boundaries
        if len(p["text"]) <= int(target * 1.4):
            split.append(p)
            continue
        part = ""
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", p["text"]):
            if part and len(part) + len(s) > target:
                split.append({**p, "text": part.strip()})
                part = ""
            part += " " + s
        if part.strip():
            split.append({**p, "text": part.strip()})
    for p in split:
        if buf and (p["h2"] != buf[0]["h2"] or sum(len(x["text"]) for x in buf) + len(p["text"]) > target
                    or ((p["h2"], p["h3"]) in STATPEARLS_DOSING_SECTIONS) != ((buf[-1]["h2"], buf[-1]["h3"]) in STATPEARLS_DOSING_SECTIONS)):
            flush()
        buf.append(p)
    flush()
    for i, t in enumerate(tables):
        md = _rows_to_markdown(t["rows"])
        chunks.append({"_h2": "Tables", "chunk_id": f"{row['source_id']}::table::{i:02d}", "heading": "Tables",
                       "section_path": "Tables > " + t["rows"][0][0], "pdf_page_start": t["page"], "pdf_page_end": t["page"],
                       "text": md, "text_for_embedding_body": linearize_table(md), "chunk_type": "table",
                       "content_type": "dosing_reference"})
    for c in chunks:
        c.pop("_h2")
        c["medications"] = tag_medications(c["text"], row["medications"])
    return chunks, rep


def medkb_chunks(row: dict, path: Path) -> tuple[list[dict], dict]:
    units, rep = parse_saudi_medkb(path)
    chunks = []
    for u in units:
        base = MEDKB_SECTION_MEDS.get(u["section_number"], [])
        meds = tag_medications(u["title"] + " " + u["text"], base)
        if base and base[0] in ACE_INHIBITORS_WITH_MONOGRAPHS:
            meds = [base[0]] + [m for m in meds if m == "metformin"]   # agent monograph: not the whole class
        topic = ("metformin" if meds[:1] == ["metformin"] else
                 "ace_inhibitors" if meds and meds[0] != "metformin" else "diabetes_hypertension_general")
        text = f"{u['title']}\n{u['text']}"
        chunks.append({"chunk_id": f"{row['source_id']}::{u['record_id']}", "record_id": u["record_id"],
                       "heading": u["title"], "section_path": f"{u['section_number']}. {u['section_title']} > "
                                                              f"{u['record_id']} {u['title']}",
                       "pdf_page_start": u["page_start"], "pdf_page_end": u["page_end"], "text": text,
                       "chunk_type": "table" if u["has_table"] else "record", "medications": meds, "topic": topic,
                       "content_type": "dosing_reference" if u["record_id"] in MEDKB_DOSING_RECORDS else "clinical",
                       "references": u["references"]})
    return chunks, rep


# ====================================================================================================
# knowledge records: one schema for every collection
# ====================================================================================================
RECORD_FIELDS = ["chunk_id", "collection", "source_id", "source_type", "title", "authors", "publisher", "version",
                 "publication_date", "revision_date", "url", "filename", "raw_path", "sha256", "licence_status",
                 "clinical_review_status", "topic", "medications", "drug", "heading", "section_path", "pdf_page_start",
                 "pdf_page_end", "printed_page", "chunk_type", "content_type", "text", "text_for_embedding",
                 "content_sha256", "char_len", "extraction_warnings", "known_issues", "needs_clinical_review",
                 "references", "citation", "active", "inactive_reason", "kb_version", "pipeline_version"]


def content_hash(text: str) -> str:
    """Hash of the normalised chunk text: equal for exact duplicates regardless of whitespace or case."""
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().lower().encode("utf-8")).hexdigest()


def _citation(row: dict, rec: dict) -> str:
    if rec.get("citation"):
        return rec["citation"]
    p0, p1 = rec.get("pdf_page_start"), rec.get("pdf_page_end")
    pages = "" if p0 is None else (f", PDF p. {p0}" if p0 == p1 or p1 is None else f", PDF pp. {p0}-{p1}")
    who = f"{row['authors'].replace(';', ',')}. " if row.get("authors") else ""
    return f"{who}{row['title']} ({row['version']}){pages}, section: {rec.get('section_path', '')}"


def to_record(row: dict, rec: dict) -> dict:
    """Normalise a chunk from any producer into the knowledge-record schema (provenance + hashes + gate fields)."""
    r = dict(rec)
    r.setdefault("collection", row["collection"])
    r["source_id"] = row["source_id"]
    r.setdefault("source_type", row["document_type"])
    r.setdefault("title", row["title"])
    r["authors"] = row.get("authors", "")
    r.setdefault("publisher", row["publisher"])
    r.setdefault("version", row["version"])
    r["publication_date"], r["revision_date"] = row.get("publication_date", ""), row.get("revision_date", "")
    r["url"] = r.get("url") or row.get("source_url", "")
    r["raw_path"] = row["raw_path"]
    r.setdefault("filename", Path(row["raw_path"]).name)
    r["sha256"] = row["sha256"]
    r["licence_status"], r["clinical_review_status"] = row["licence_status"], row.get("clinical_review_status", "")
    r.setdefault("topic", (row.get("topic") or [""])[0])
    meds = r.get("medications")
    if meds is None:
        meds = tag_medications(r.get("text", ""), row.get("medications")) if row["collection"] == COLLECTION_MEDICATION else []
    r["medications"] = meds
    r["drug"] = r.get("drug") or (meds[0] if meds else "")       # primary medication (backward compatible field)
    r.setdefault("heading", (r.get("section_path") or "").split(" > ")[0])
    r.setdefault("pdf_page_start", None)
    r.setdefault("pdf_page_end", r.get("pdf_page_start"))
    r.setdefault("printed_page", "")
    r.setdefault("chunk_type", "text")
    r.setdefault("content_type", "clinical" if row["collection"] != COLLECTION_APP else "app_documentation")
    if "text_for_embedding" not in r:
        body = r.pop("text_for_embedding_body", None) or r["text"]
        meds_label = ", ".join(meds)
        r["text_for_embedding"] = f"{row['title']}{' (' + meds_label + ')' if meds_label else ''} | {r['section_path']}\n{body}"
    r.pop("text_for_embedding_body", None)
    r["content_sha256"] = content_hash(r["text"])
    r["char_len"] = len(r["text"])
    r.setdefault("extraction_warnings", [])
    issues = [msg for rx, msg in KNOWN_ISSUES.get(row["source_id"], []) if rx.search(r["text"])]
    r["known_issues"] = r.get("known_issues", []) + issues
    r["needs_clinical_review"] = row.get("clinical_review_status") != "APPROVED"
    r.setdefault("references", [])
    r["citation"] = _citation(row, r)
    r["active"], r["inactive_reason"] = True, ""
    if r["content_type"] == "dosing_reference" and not INDEX_DOSING_REFERENCE:
        r["active"], r["inactive_reason"] = False, "dosing_reference_excluded_by_policy (set VITALA_INDEX_DOSING=1)"
    r["kb_version"], r["pipeline_version"] = KB_VERSION, PIPELINE_VERSION
    ordered = {k: r[k] for k in RECORD_FIELDS if k in r}
    return {**ordered, **{k: v for k, v in r.items() if k not in ordered}}


def _shingles(text: str, n: int = 5) -> set:
    w = re.findall(r"\w+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def deduplicate(records: list[dict], near_threshold: float = 0.9) -> tuple[list[dict], dict]:
    """Drop exact duplicates (same content hash) within a collection; report near-duplicates (shingle Jaccard)."""
    kept, seen, exact = [], {}, []
    for r in records:
        h = r["content_sha256"]
        if h in seen:
            exact.append({"dropped": r["chunk_id"], "duplicate_of": seen[h]})
            continue
        seen[h] = r["chunk_id"]
        kept.append(r)
    near, sh = [], [(r["chunk_id"], _shingles(r["text"])) for r in kept if r.get("active", True)]
    for i in range(len(sh)):
        for j in range(i + 1, len(sh)):
            a, b = sh[i][1], sh[j][1]
            if a and b and len(a & b) / len(a | b) >= near_threshold:
                near.append({"a": sh[i][0], "b": sh[j][0], "jaccard": round(len(a & b) / len(a | b), 3)})
    return kept, {"exact_duplicates_dropped": exact, "near_duplicates_reported": near}


def assert_records_allowed(records: list[dict], active: dict[str, dict], collection: str) -> None:
    """Refuse to index anything from an inactive / unregistered / modified source or the wrong collection."""
    problems = []
    for r in records:
        src = active.get(r["source_id"])
        if src is None:
            problems.append(f"{r['chunk_id']}: source {r['source_id']} is not active in the registry")
        elif src["sha256"] != r.get("sha256"):
            problems.append(f"{r['chunk_id']}: built from a different file version than the registered one")
        elif src["collection"] != collection or r["collection"] != collection:
            problems.append(f"{r['chunk_id']}: belongs to {src['collection']}, not {collection}")
        elif r["collection"] == COLLECTION_MEDICATION and r.get("medications") and not \
                set(r["medications"]) & set(IN_SCOPE_MEDICATIONS):
            problems.append(f"{r['chunk_id']}: medications {r['medications']} are outside the demo scope")
    if problems:
        raise ValueError(f"{len(problems)} record(s) blocked by the activation gate:\n" + "\n".join(problems[:20]))


# ====================================================================================================
# build stages (notebook 01 and `python -m vitala_rag build`)
# ====================================================================================================
def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_knowledge(paths: Paths, collection: str, active_only: bool = True) -> list[dict]:
    recs = _read_jsonl(paths.knowledge_file(collection))
    return [r for r in recs if r.get("active", True)] if active_only else recs


def run_source_verification(paths: Paths, require_clinical: bool | None = None) -> dict:
    """Stage 1: apply the activation gate to every registered source and write the gate report."""
    paths.ensure()
    decisions = evaluate_registry(paths, require_clinical)
    report = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
              "require_clinical_approval": REQUIRE_CLINICAL_APPROVAL if require_clinical is None else require_clinical,
              "sources": [d.as_dict() for d in decisions],
              "active": [d.source_id for d in decisions if d.active],
              "inactive": {d.source_id: d.reasons for d in decisions if not d.active}}
    (paths.reports / "source_gate_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def run_extraction(paths: Paths, require_clinical: bool | None = None) -> dict:
    """Stage 2: extract text from every ACTIVE source (pages with blocks for guidelines, plain page text for the
    medication PDFs, structured records for FDA labels) into data/processed/."""
    active = active_sources(paths, require_clinical)
    report = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"), "documents": []}
    review_rows = []
    for sid, row in active.items():
        raw = paths.root / row["raw_path"]
        entry = {"source_id": sid, "raw_path": row["raw_path"], "document_type": row["document_type"]}
        if row["document_type"] == "national_guideline":
            pages, summary = extract_pdf(raw)
            _write_jsonl(paths.processed / "pages" / f"{sid}.jsonl",
                         [{"pdf_page": p.pdf_page, "printed_page": p.printed_page, "flags": p.flags,
                           "blocks": [asdict(b) for b in p.blocks]} for p in pages])
            entry["extraction_summary"] = summary
            for p in pages:
                issues = _page_review_issues(p)
                if issues:
                    review_rows.append({"source_id": sid, "pdf_page": p.pdf_page, "printed_page": p.printed_page,
                                        "issues": "; ".join(issues), "reviewer": "", "status": "TO_CHECK", "comment": ""})
        elif row["document_type"] == "fda_drug_label":
            fetched = json.loads(raw.read_text(encoding="utf-8"))
            drug = row["medications"][0]
            spec = next((d for d in load_manifest(paths.candidate_manifest).get("drugs", []) if d["drug"] == drug),
                        {"drug": drug, "set_id": fetched["label"]["set_id"]})
            spec = {**spec, "expected_active_ingredient": spec.get("expected_active_ingredient") or drug.upper()}
            rec = build_record(spec, fetched, raw, "CANDIDATE_NOT_USER_VERIFIED")
            rec["retrieved_at"] = row.get("retrieval_date") or rec["retrieved_at"]   # reproducible output
            out = paths.processed / "medications" / f"{drug}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            entry["validation"] = rec["validation"]
        elif raw.suffix.lower() == ".pdf":
            doc = pymupdf.open(raw)
            _write_jsonl(paths.processed / "pages" / f"{sid}.jsonl",
                         [{"pdf_page": i + 1, "text": ZERO_WIDTH_RE.sub("", doc[i].get_text())} for i in range(doc.page_count)])
            entry["pages"] = doc.page_count
        report["documents"].append(entry)
    (paths.reports / "extraction_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(paths.reports / "extraction_review_queue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source_id", "pdf_page", "printed_page", "issues", "reviewer", "status", "comment"])
        w.writeheader()
        w.writerows(review_rows)
    report["review_pages"] = len(review_rows)
    return report


def _page_review_issues(p) -> list[str]:
    issues = []
    if p.flags.get("tables"):
        issues.append(f"{p.flags['tables']} table(s)")
    if p.flags.get("table_low_confidence"):
        issues.append("table with many empty cells (check merged cells)")
    if p.flags.get("layout_tables"):
        issues.append("prose in grid layout (re-ordered column by column)")
    if p.flags.get("two_column"):
        issues.append("two-column page re-ordered")
    if p.flags.get("low_text"):
        issues.append("very little text (image/scanned content may be missing)")
    if p.flags.get("font_shift_repairs"):
        issues.append(f"{p.flags['font_shift_repairs']} span(s) with broken font encoding repaired (verify against PDF)")
    if p.flags.get("geq_glyph_mapped"):
        issues.append(f"{p.flags['geq_glyph_mapped']} glyph(s) mapped to '≥' (verify thresholds)")
    if p.flags.get("residual_garble"):
        issues.append("possible unrepaired garbled text")
    if p.flags.get("ligature_fixes"):
        issues.append(f"{p.flags['ligature_fixes']} ligature repair(s)")
    if p.flags.get("numeric_thresholds", 0) >= 3:
        issues.append(f"{p.flags['numeric_thresholds']} numeric thresholds")
    return issues


def load_pages(path: Path) -> list[PageRecord]:
    pages = []
    for row in _read_jsonl(path):
        blocks = [Block(b["kind"], b["text"], tuple(b["bbox"]), b.get("font_size", 0.0), b.get("bold", False)) for b in row["blocks"]]
        pages.append(PageRecord(row["pdf_page"], row["printed_page"], blocks, row["flags"]))
    return pages


def build_knowledge_base(paths: Paths, require_clinical: bool | None = None) -> dict:
    """Stage 3: chunk every active source into knowledge records, deduplicate, gate-check and write
    data/processed/knowledge/<collection>.jsonl + kb_manifest.json + the clinical review queue."""
    active = active_sources(paths, require_clinical)
    extraction = json.loads((paths.reports / "extraction_report.json").read_text(encoding="utf-8"))
    body_sizes = {d["source_id"]: d["extraction_summary"]["body_font_size"] for d in extraction["documents"]
                  if "extraction_summary" in d}
    status = load_feature_status(paths.app_feature_status)
    out = {c: [] for c in ALL_COLLECTIONS}
    stats = {}
    for sid, row in active.items():
        raw = paths.root / row["raw_path"]
        dtype, col = row["document_type"], row["collection"]
        if dtype == "national_guideline":
            src = {**row, "source_type": dtype, "filename": raw.name}
            chunks, st = chunk_document(src, load_pages(paths.processed / "pages" / f"{sid}.jsonl"), body_sizes[sid])
            chunks, st["fragments_merged"] = merge_fragments(chunks)
        elif dtype == "fda_drug_label":
            rec = json.loads((paths.processed / "medications" / f"{row['medications'][0]}.json").read_text(encoding="utf-8"))
            if not rec["validation"]["passed"]:
                stats[sid] = {"chunks": 0, "error": "FDA label validation failed"}
                continue
            chunks, st = medication_chunks(rec), {}
            for c in chunks:
                c["medications"], c["topic"] = [rec["drug"]], rec["drug"]
        elif dtype == "clinical_reference_review":
            chunks, st = statpearls_chunks(row, raw)
        elif dtype == "compiled_clinical_knowledge_base":
            chunks, st = medkb_chunks(row, raw)
        elif dtype == "app_documentation":
            audience = "patient" if "PATIENT" in sid else "clinic"
            chunks, st = parse_app_document(raw, audience, status), {}
        else:
            stats[sid] = {"chunks": 0, "error": f"no chunker for document_type={dtype}"}
            continue
        recs = [to_record(row, c) for c in chunks]
        stats[sid] = {**{k: v for k, v in st.items() if k != "duplicate_paragraphs_dropped"},
                      "duplicate_paragraphs_dropped": len(st.get("duplicate_paragraphs_dropped", [])),
                      "chunks": len(recs), "active_chunks": sum(r["active"] for r in recs)}
        out[col] += recs
    dedup = {}
    manifest = {"kb_version": KB_VERSION, "pipeline_version": PIPELINE_VERSION,
                "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "require_clinical_approval": REQUIRE_CLINICAL_APPROVAL if require_clinical is None else require_clinical,
                "index_dosing_reference": INDEX_DOSING_REFERENCE, "collections": {}, "sources": {}}
    for col, recs in out.items():
        recs, dedup[col] = deduplicate(recs)
        assert_records_allowed([r for r in recs if r["active"]], active, col)
        ids = [r["chunk_id"] for r in recs]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{col}: duplicate chunk IDs")
        _write_jsonl(paths.knowledge_file(col), recs)
        manifest["collections"][col] = {
            "records": len(recs), "active_records": sum(r["active"] for r in recs),
            "file": str(paths.knowledge_file(col).relative_to(paths.root)).replace("\\", "/"),
            "file_sha256": sha256_file(paths.knowledge_file(col)),
            "sources": sorted({r["source_id"] for r in recs})}
        out[col] = recs
    for sid, row in active.items():
        manifest["sources"][sid] = {"sha256": row["sha256"], "version": row["version"], **stats.get(sid, {})}
    (paths.knowledge / "kb_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (paths.reports / "dedup_report.json").write_text(json.dumps(dedup, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(paths.reports / "chunk_review_queue.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["chunk_id", "collection", "active", "citation", "warnings", "known_issues",
                                          "text_preview", "reviewer", "status", "comment"])
        w.writeheader()
        for col, recs in out.items():
            for c in recs:
                if c["extraction_warnings"] or c["known_issues"] or c["content_type"] == "dosing_reference":
                    w.writerow({"chunk_id": c["chunk_id"], "collection": col, "active": c["active"],
                                "citation": c["citation"], "warnings": ";".join(c["extraction_warnings"]),
                                "known_issues": " | ".join(c["known_issues"]) +
                                                (" | dosing reference (excluded)" if not c["active"] else ""),
                                "text_preview": c["text"][:300].replace("\n", " "), "reviewer": "", "status": "TO_REVIEW",
                                "comment": ""})
    manifest["dedup"] = {c: {k: len(v) for k, v in d.items()} for c, d in dedup.items()}
    return manifest


def build_indexes(paths: Paths, embedder, collections: tuple = ALL_COLLECTIONS) -> dict:
    """Stage 4: FAISS + BM25 per collection from the knowledge JSONL files (active records only)."""
    from .retrieval import build_collection_index
    active = active_sources(paths, scan=False)
    status_sha = sha256_file(paths.app_feature_status) if paths.app_feature_status.exists() else ""
    manifests = {}
    for col in collections:
        recs = load_knowledge(paths, col)
        assert_records_allowed(recs, active, col)
        extra = {"kb_version": KB_VERSION, "knowledge_file_sha256": sha256_file(paths.knowledge_file(col)),
                 "source_sha256": {sid: active[sid]["sha256"] for sid in sorted({r["source_id"] for r in recs})}}
        if col == COLLECTION_APP:
            extra["feature_status_sha256"] = status_sha
        manifests[col] = build_collection_index(recs, paths.indexes / col, embedder,
                                                tokenizer="arabic_ngram" if col == COLLECTION_APP else "word", extra=extra)
    (paths.reports / "index_build_report.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    return manifests


def build_all(paths: Paths, embedder=None, require_clinical: bool | None = None) -> dict:
    """Run stages 1-4. Without an embedder the indexes are not rebuilt (stages 1-3 only)."""
    out = {"gate": run_source_verification(paths, require_clinical), "extraction": run_extraction(paths, require_clinical),
           "knowledge": build_knowledge_base(paths, require_clinical)}
    if embedder is not None:
        out["indexes"] = build_indexes(paths, embedder)
    return out


def refresh_fda_labels(paths: Paths, api_key: str | None = None) -> dict:
    """Optional, needs network: re-download the in-scope FDA labels listed in the drug manifest (raw JSON only).
    Update the sha256 / version in data/source_registry.csv afterwards, or the gate will block the new file."""
    manifest = load_manifest(paths.drug_manifest if paths.drug_manifest.exists() else paths.candidate_manifest)
    results = []
    for spec in manifest.get("drugs") or manifest.get("medications") or []:
        drug = spec.get("drug") or spec.get("name")
        if drug not in IN_SCOPE_MEDICATIONS:
            results.append({"drug": drug, "skipped": "outside the demo scope"})
            continue
        try:
            fetched = fetch_label(spec["set_id"], api_key=api_key)
        except Exception as exc:
            results.append({"drug": drug, "ok": False, "error": str(exc)})
            continue
        raw_path = paths.raw_meds / f"{drug}_openfda_label_raw.json"
        raw_path.write_text(json.dumps(fetched, ensure_ascii=False, indent=1), encoding="utf-8")
        results.append({"drug": drug, "ok": True, "sha256": sha256_file(raw_path), "version": fetched["label"].get("version")})
    return {"results": results}


# ====================================================================================================
# traceability: from any retrieved chunk back to the exact original document and page
# ====================================================================================================
def find_record(paths: Paths, chunk_id: str) -> dict | None:
    col_guess = [c for c in ALL_COLLECTIONS if paths.knowledge_file(c).exists()]
    for col in col_guess:
        with open(paths.knowledge_file(col), encoding="utf-8") as f:
            for line in f:
                if chunk_id in line:
                    r = json.loads(line)
                    if r["chunk_id"] == chunk_id:
                        return r
    return None


def trace_chunk(paths: Paths, chunk_id: str, verify_text: bool = True) -> dict:
    """Where did this chunk come from? Registry entry, raw file, page, URL, hashes, and (optionally) a check that
    the chunk text really appears on the cited PDF page(s) of the original document."""
    rec = find_record(paths, chunk_id)
    if rec is None:
        return {"chunk_id": chunk_id, "found": False}
    reg = {r["source_id"]: r for r in read_registry(paths.registry_csv)}.get(rec["source_id"], {})
    raw = paths.root / rec["raw_path"]
    out = {"chunk_id": chunk_id, "found": True, "collection": rec["collection"], "active": rec.get("active", True),
           "source_id": rec["source_id"], "title": rec["title"], "version": rec["version"], "url": rec.get("url"),
           "raw_path": rec["raw_path"], "raw_file_exists": raw.exists(), "pdf_page_start": rec.get("pdf_page_start"),
           "pdf_page_end": rec.get("pdf_page_end"), "printed_page": rec.get("printed_page"),
           "section_path": rec.get("section_path"), "doc_sha256_registered": reg.get("sha256"),
           "doc_sha256_record": rec.get("sha256"), "content_sha256": rec.get("content_sha256"),
           "licence_status": reg.get("licence_status"), "clinical_review_status": reg.get("clinical_review_status"),
           "references": rec.get("references", []), "citation": rec["citation"]}
    out["doc_hash_matches"] = raw.exists() and sha256_file(raw) == rec.get("sha256")
    page_text = None
    if verify_text and raw.exists() and raw.suffix.lower() == ".pdf" and rec.get("pdf_page_start"):
        doc = pymupdf.open(raw)
        p0, p1 = rec["pdf_page_start"], rec.get("pdf_page_end") or rec["pdf_page_start"]
        page_text = " ".join(doc[i - 1].get_text() for i in range(p0, p1 + 1))
    elif verify_text and raw.exists() and raw.suffix.lower() == ".json":
        def strings(x):
            if isinstance(x, str):
                yield x
            elif isinstance(x, dict):
                for v in x.values():
                    yield from strings(v)
            elif isinstance(x, list):
                for v in x:
                    yield from strings(v)
        page_text = " ".join(strings(json.loads(raw.read_text(encoding="utf-8"))))
    elif verify_text and raw.exists() and raw.suffix.lower() == ".txt":
        page_text = raw.read_text(encoding="utf-8-sig")
    if page_text is not None:
        norm = lambda s: re.sub(r"[^a-z0-9ء-ي]+", "", normalize_arabic(ZERO_WIDTH_RE.sub("", s.lower())))
        # contiguous 8-word windows of the chunk text (tables and line wraps are compared without spaces/punctuation)
        words = [w for w in re.split(r"\s+", REF_MARKER_RE.sub("", rec["text"])) if w and w != "|" and not set(w) <= set("|-")]
        step = max(1, (len(words) - 8) // 4)
        probe = [" ".join(words[i:i + 8]) for i in range(0, max(1, len(words) - 7), step)][:5]
        page_norm = norm(page_text)
        hits = [norm(p) in page_norm for p in probe if norm(p)]
        out["text_found_on_cited_pages"] = f"{sum(hits)}/{len(hits)} probe phrases" if hits else "no probe phrases"
    return out


# ====================================================================================================
# app_knowledge (parsing)
# VITALA application knowledge base ("app" collection, C).
#
# Source of truth: the two Arabic application-description documents supplied by the VITALA team
#   data/raw/app/vitala_features_patient_ar.txt   (patient mobile app, sections 2-24)
#   data/raw/app/vitala_features_clinic_ar.txt    (clinic dashboard, sections 25-33)
# Each numbered section becomes one knowledge record (data/processed/knowledge/app.jsonl, indexes/app/). If the
# index is missing or older than the documents, retrieval.AppKnowledgeBase parses the documents directly, so the
# app collection can never silently go stale.
#
# Honesty rules encoded here (the LLM prompt repeats them):
#   * Each section keeps its source document, section number and Arabic/English title for citation.
#   * The documents are design descriptions. Nothing in this project proves which features are shipped, so every
#     section's implementation_status is "unverified" unless data/raw/app/vitala_app_feature_status.json says
#     otherwise (the VITALA team can mark sections "implemented" or "planned" there).
#   * Sections the documents themselves mark as possibly not needed ("ما نحتاجها" blocks and inline "(ما يحتاج)"
#     notes) are tagged so answers never present them as available features.
#   * `search_terms` are retrieval aids only (dialect / English synonyms). They are never shown or cited as facts.
# ====================================================================================================

APP_SOURCES = {
    "patient": {"source_id": "VITALA-APP-PATIENT-AR",
                "title": "VITALA patient app - feature description (Arabic)",
                "title_ar": "وصف خصائص تطبيق VITALA للمستخدم"},
    "clinic": {"source_id": "VITALA-APP-CLINIC-AR",
               "title": "VITALA clinic dashboard - feature description (Arabic)",
               "title_ar": "وصف خصائص لوحة تحكم العيادة في VITALA"},
}

HEADER_RE = re.compile(r"^\s*(\d{1,2})\.\s+(.+?)\s*\(([A-Za-z][^()]*)\)\s*$")
SEPARATOR_RE = re.compile(r"^\s*[—–_\-]{10,}\s*$")
NOT_NEEDED_BLOCK_RE = re.compile(normalize_arabic(r"^\s*ما\s+(احس\s+)?نحتاج"))
INLINE_NOTE_RE = re.compile(r"\(\s*(ما\s*يحتاج|ممكن\s+ما\s+نحتاجها|ما\s+نحتاجها)\s*\)")
INLINE_NOTE_TEXT = "[ملاحظة في الوثيقة: قد لا تكون هذه الخاصية مطلوبة]"

IMPLEMENTATION_STATUSES = ("implemented", "planned", "unverified")

# Retrieval aids per (audience, section number): Saudi dialect + English phrasings users actually type.
SEARCH_TERMS = {
    ("patient", 2): "sign up register create account log in login phone number full name انشاء حساب تسجيل دخول اسجل ادخل رقم الجوال",
    ("patient", 3): "personal information profile age birth date sex gender height weight enter معلومات شخصية العمر الجنس الطول الوزن ملفي ادخل طولي ووزني",
    ("patient", 4): "bmi body mass index calculation calculate category مؤشر كتلة الجسم يحسب",
    ("patient", 5): "medical history diseases conditions family history current medications previous results add edit التاريخ المرضي امراض ادويتي اضيف",
    ("patient", 6): "risk factors عوامل الخطورة عوامل الخطر",
    ("patient", 7): "apple health healthkit wearable device smart watch smartwatch apple watch connect link sync permission skip steps sleep heart rate ابل هيلث الساعة الذكية ساعه جهاز اربط ربط خطوات نوم نبض اذن",
    ("patient", 8): "how vitala uses my health data information analysis analyse privacy what data compare guidelines يستخدم معلوماتي بياناتي الصحية تحليل خصوصية",
    ("patient", 9): "personalized screening recommendations why recommended reason test list how vitala decides توصيات الفحوصات سبب التوصية رشح يحدد",
    ("patient", 10): "health plan summary due overdue upcoming screenings difference goals الخطة الصحية الفحوصات المستحقة المتأخرة القادمة الفرق",
    ("patient", 11): "home dashboard main page home screen notifications reminders الصفحة الرئيسية الاشعارات التذكيرات الرئيسيه",
    ("patient", 12): "ai assistant chatbot chat what can the assistant do help explain المساعد الذكي الشات بوت وش يسوي المساعد",
    ("patient", 13): "screening plan details test page description purpose reference where find my screening plan خطة الفحوصات تفاصيل الفحص صفحة الفحص وين القى خطة الفحوصات خطتي",
    ("patient", 14): "nearby clinics find clinic search location city area near me العيادات القريبة ابحث عن عيادة الموقع المدينة",
    ("patient", 15): "clinics list map distance rating working hours services خريطة قائمة العيادات المسافة التقييم",
    ("patient", 16): "clinic details contact information working hours location تفاصيل العيادة ساعات العمل",
    ("patient", 17): "select screening service blood test cholesterol diabetes test choose service اختيار خدمة الفحص تحليل الدم",
    ("patient", 18): "available appointments times slots dates schedule المواعيد المتاحة الاوقات المتاحة",
    ("patient", 19): "book appointment booking confirm reserve how to book a test what happens after booking احجز حجز موعد احجز فحص تأكيد الحجز وش يصير بعد ما احجز بعد الحجز",
    ("patient", 20): "booking confirmation my appointments upcoming past edit reschedule cancel change modify appointment تأكيد الحجز مواعيدي اعدل تعديل الغي الغاء اغير موعدي",
    ("patient", 21): "contact clinic message send inquiry question doctor reply التواصل مع العيادة استفسار رسالة الطبيب",
    ("patient", 22): "results health history previous test results reports files uploaded where find see my results نتائج الفحوصات السابقة السجل الصحي التقارير وين القى نتائجي",
    ("patient", 23): "health monitoring goals activity steps sleep heart rate reminders tracking متابعة الصحة الاهداف النشاط التذكيرات",
    ("patient", 24): "continuous follow up update plan new results new recommendations المتابعة المستمرة تحديث الخطة نتائج جديدة",
    ("clinic", 25): "clinic login sign in clinic account email password تسجيل دخول العيادة",
    ("clinic", 26): "clinic dashboard sections overview لوحة تحكم العيادة",
    ("clinic", 27): "can the clinic see my information access my data patient profile what clinic sees privacy هل العيادة تشوف معلوماتي بياناتي ملفي الصحي تطلع على",
    ("clinic", 28): "clinic services management add edit delete service ادارة الخدمات",
    ("clinic", 29): "clinic appointments management availability booked appointments status completed cancelled no show ادارة المواعيد حالة الموعد ملغي مكتمل لم يحضر",
    ("clinic", 30): "upload results clinic uploads test result report file رفع النتائج العيادة ترفع النتيجة",
    ("clinic", 31): "reports analytics statistics clinic activity التقارير التحليلات الاحصائيات",
    ("clinic", 32): "clinic profile logo description location contact الملف التعريفي للعيادة",
    ("clinic", 33): "contact requests inquiries doctor reply clinic messages طلبات التواصل",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_feature_status(path: Path | None) -> dict:
    """Optional team-maintained status overrides. Missing file -> everything 'unverified'."""
    if path is None or not path.exists():
        return {"default_status": "unverified", "sections": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    default = data.get("default_status", "unverified")
    if default not in IMPLEMENTATION_STATUSES:
        raise ValueError(f"{path.name}: default_status must be one of {IMPLEMENTATION_STATUSES}")
    for sid, entry in data.get("sections", {}).items():
        if entry.get("status") not in IMPLEMENTATION_STATUSES:
            raise ValueError(f"{path.name}: {sid} status must be one of {IMPLEMENTATION_STATUSES}")
    return {"default_status": default, "sections": data.get("sections", {})}


def parse_app_document(path: Path, audience: str, status: dict | None = None) -> list[dict]:
    """Split one application-description document into one chunk per numbered section."""
    meta = APP_SOURCES[audience]
    status = status or {"default_status": "unverified", "sections": {}}
    raw = path.read_text(encoding="utf-8-sig")
    sha = _sha256(path)
    sections, cur, in_not_needed = [], None, False
    for line in raw.splitlines():
        if SEPARATOR_RE.match(line):
            in_not_needed = False       # a separator opens or closes a "not needed" block
            continue
        if NOT_NEEDED_BLOCK_RE.match(normalize_arabic(line)):
            in_not_needed = True
            continue
        m = HEADER_RE.match(line)
        if m:
            cur = {"number": int(m.group(1)), "title_ar": m.group(2).strip(), "title_en": m.group(3).strip(),
                   "lines": [], "not_needed_block": in_not_needed, "inline_notes": 0}
            sections.append(cur)
            continue
        if cur is None or not line.strip():
            continue                    # document heading ("Patient", "Clinic") or blank line
        if INLINE_NOTE_RE.search(line):
            cur["inline_notes"] += 1
            line = INLINE_NOTE_RE.sub(INLINE_NOTE_TEXT, line)
        cur["lines"].append(re.sub(r"\s+", " ", line).strip())

    chunks = []
    for s in sections:
        chunk_id = f"{meta['source_id']}::s{s['number']:02d}"
        header = f"{s['number']}. {s['title_ar']} ({s['title_en']})"
        text = header + "\n" + "\n".join(s["lines"])
        doc_status = "marked_possibly_not_needed" if s["not_needed_block"] else "described"
        override = status["sections"].get(chunk_id, {})
        terms = SEARCH_TERMS.get((audience, s["number"]), "")
        chunks.append({
            "chunk_id": chunk_id, "collection": COLLECTION_APP, "source_id": meta["source_id"],
            "source_type": "app_documentation", "audience": audience,
            "title": meta["title"], "title_ar": meta["title_ar"], "publisher": "VITALA team",
            "version": f"sha256 {sha[:12]}", "filename": path.name, "sha256": sha,
            "section_number": s["number"], "section_title_ar": s["title_ar"], "section_title_en": s["title_en"],
            "section_path": header, "pdf_page_start": None, "printed_page": "", "url": "",
            "doc_status": doc_status, "has_inline_not_needed_notes": s["inline_notes"] > 0,
            "implementation_status": override.get("status", status["default_status"]),
            "text": text, "search_terms": terms,
            "text_for_embedding": f"{meta['title']} | {s['title_en']}\n{text}\n{terms}",
            "citation": f"{meta['title']}, section {s['number']}: {s['title_en']} ({s['title_ar']})",
        })
    return chunks
