"""PDF -> structured page records, with extraction-quality flags.

What this module does for every page:
  * extracts text blocks with font size / bold information (for heading detection)
  * detects tables with PyMuPDF and converts them to Markdown rows, so a table like
    "Normal | <120 mm Hg | and | <80 mm Hg" stays on one line instead of being scattered
  * re-orders two-column pages (left column, then right column)
  * removes running headers/footers and page numbers, but records the printed page label
  * repairs the one known font-ligature defect ("Edi)on" -> "Edition") and counts every fix
  * flags pages that need human checking: tables, numeric thresholds, low text, odd characters

Nothing here rewrites medical wording. Cleaning only removes layout artefacts.
"""
from __future__ import annotations

import collections
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

NUMERIC_THRESHOLD_RE = re.compile(
    r"([<>≥≤]=?\s*\d)|(\d+(\.\d+)?\s*(mm\s?hg|mg/dl|mmol/l|mmol|kg/m2|kg/ m2|kg|%|mg|µg|mcg|years?))", re.I)
LIGATURE_RE = re.compile(r"\b([A-Za-z]*[a-z])\)([a-z]+)\b")
PAGE_NUM_RE = re.compile(r"^\s*([0-9]{1,3}|[ivxlcdm]{1,6})\s*$", re.I)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]")
DOT_LEADER_RE = re.compile(r"(\.{6,}|…{3,})")
# leftovers of the broken font encoding, e.g. "2*77" (OGTT), "3&26" (PCOS), ")UHTXHQWO\"
RESIDUAL_GARBLE_RE = re.compile(r"\b[A-Z0-9]{1,6}[*&\\$][A-Z0-9*&\\$']{1,6}|[)(,][A-Z]{3,}\\")  # not "(USPSTF)"


@dataclass
class Block:
    kind: str          # "text" | "table"
    text: str
    bbox: tuple
    font_size: float = 0.0
    bold: bool = False


@dataclass
class PageRecord:
    pdf_page: int
    printed_page: str
    blocks: list[Block]
    flags: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


FONT_SHIFT = 29            # observed in the PHA diabetes guideline: glyph codes offset by 29 ("3ODVPD" = "Plasma")
WORD_RE = re.compile(r"[A-Za-z]{2,}")
SHIFT_CTRL_RE = re.compile(r"[\x03-\x1c]")


def _shift(text: str, k: int = FONT_SHIFT) -> str:
    # a literal space is a genuine space (the broken fonts encode their own spaces as \x03).
    # In the same broken fonts glyph 0x95 is the "≥" sign ("\x95200 mg/dl" = "≥200 mg/dl"); this mapping is
    # flagged for medical review in the extraction report (flag: geq_glyph_mapped).
    out = "".join(chr(ord(c) + k) if ord(c) <= 0x5D and c != " " else c for c in text)
    return out.replace("\x95", "≥")


def _english_shape(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if re.fullmatch(r"[A-Z]?[a-z]+", t) and re.search("[aeiouy]", t.lower())) / len(tokens)


def _build_vocab(doc: pymupdf.Document) -> set[str]:
    """Vocabulary from spans that already look like normal prose (used to recognise mis-encoded spans)."""
    vocab = collections.Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    toks = WORD_RE.findall(s["text"])
                    good = [t for t in toks if re.fullmatch(r"[A-Z]?[a-z]+", t) and re.search("[aeiouy]", t.lower())]
                    if len(toks) >= 3 and len(good) / len(toks) >= 0.6:
                        vocab.update(t.lower() for t in good)
                        # acronyms that appear inside clean prose (OGTT, FPG, PCOS ...), kept upper-case
                        vocab.update(t for t in toks if re.fullmatch(r"[A-Z]{2,6}", t))
    return {w for w, c in vocab.items() if c >= 1}


def _hits(tokens: list[str], vocab: set[str]) -> float:
    return sum(1 for t in tokens if t.lower() in vocab or t in vocab) / len(tokens) if tokens else 0.0


def _maybe_unshift(text: str, vocab: set[str]) -> tuple[str, bool]:
    """Repair a span whose characters are offset by FONT_SHIFT code points (broken ToUnicode map)."""
    if not text.strip():
        return text, False
    has_ctrl = bool(SHIFT_CTRL_RE.search(text))
    candidate = _shift(text)
    if has_ctrl and not re.search(r"[a-z]", text):
        # control characters never occur in real text: these are encoded spaces/digits ("\x14\x13" = "10")
        return candidate, True
    # Safety rails against corrupting good text (numbers, acronyms, normal words):
    if re.search(r"[a-z]", text):                       # broken spans contain no lower-case letters
        return text, False
    if re.fullmatch(r"[\d\s.,:;%()\-–/+<>=≥≤]*", text):  # numbers and punctuation are left untouched
        return text, False
    if re.search(r"[\^_`]", candidate):                 # A, B, C would decode to ^ _ ` : not a broken span
        return text, False
    raw_o, raw_s = WORD_RE.findall(text), WORD_RE.findall(candidate)
    toks_s = raw_s
    hit_o, hit_s = _hits(raw_o, vocab), _hits(raw_s, vocab)
    if toks_s and hit_s >= 0.5 and hit_s > hit_o + 0.3:
        return candidate, True
    # short garbled fragments with rare words ("PDFURVRPLF EDE\" = "macrosomic baby")
    if toks_s and hit_s >= 0.3 and hit_o <= 0.1 and _english_shape(raw_o) <= 0.2 and _english_shape(raw_s) >= 0.5:
        return candidate, True
    return text, False


def _fix_ligatures(text: str) -> tuple[str, int]:
    """Repair 'ti' ligatures that were extracted as ')'. Only touches words with no '('."""
    count = 0

    def repl(m):
        nonlocal count
        count += 1
        return f"{m.group(1)}ti{m.group(2)}"

    out = []
    for token in re.split(r"(\s+)", text):
        if ")" in token and "(" not in token:
            token = LIGATURE_RE.sub(repl, token)
        out.append(token)
    return "".join(out), count


def _clean_text(text: str) -> str:
    text = CONTROL_RE.sub(" ", text)
    text = text.replace("­", "")              # soft hyphen
    text = text.replace("›", "'")                  # seen in SCPG: doctor›s
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)   # de-hyphenate line breaks
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def _table_to_markdown(rows: list[list]) -> tuple[str, float]:
    """Return markdown and the fraction of empty cells (an extraction-confidence proxy)."""
    clean = [[re.sub(r"\s+", " ", (c or "")).strip() for c in r] for r in rows]
    clean = [r for r in clean if any(r)]
    if not clean:
        return "", 1.0
    # drop columns that are empty in every row (e.g. blank "Date (Month/Year)" tick columns)
    width = max(len(r) for r in clean)
    clean = [r + [""] * (width - len(r)) for r in clean]
    body = clean[1:] or clean
    keep = [j for j in range(width) if any(r[j] for r in body)]
    clean = [[r[j] for j in keep] for r in clean]
    n_cells = sum(len(r) for r in clean)
    empty = sum(1 for r in clean for c in r if not c) / max(1, n_cells)
    header = clean[0]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in clean[1:]:
        r = r + [""] * (len(header) - len(r))
        lines.append("| " + " | ".join(r[: len(header)]) + " |")
    return "\n".join(lines), empty


def _overlap(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    area = (a[2] - a[0]) * (a[3] - a[1])
    return (x1 - x0) * (y1 - y0) / max(area, 1e-6)


def _repaired_spans(page_dict: dict, vocab: set[str], flags: dict) -> None:
    """Repair mis-encoded spans in place and count the repairs."""
    n = geq = 0
    for b in page_dict["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                fixed, changed = _maybe_unshift(s["text"], vocab)
                if changed:
                    geq += s["text"].count("\x95")
                    s["text"] = fixed
                    n += 1
    flags["font_shift_repairs"] = n
    flags["geq_glyph_mapped"] = geq


def _cell_text(cell_bbox, span_index, used: set) -> str:
    x0, y0, x1, y1 = cell_bbox
    inside = []
    for k, (sx, sy, cx, cy, t) in enumerate(span_index):
        if k not in used and x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1:
            inside.append((sy, sx, t))
            used.add(k)            # a span belongs to one cell only (merged cells overlap)
    inside.sort(key=lambda v: (round(v[0] / 3), v[1]))
    return re.sub(r"\s+", " ", " ".join(t for _, _, t in inside)).strip()


def _table_rows(t, span_index) -> list[list]:
    """Rebuild table cells from (repaired) spans; fall back to PyMuPDF's own extract()."""
    try:
        rows, used = [], set()
        for r in t.rows:
            row = [_cell_text(c, span_index, used) if c else "" for c in r.cells]
            rows.append(row)
        if any(any(c for c in r) for r in rows):
            return rows
    except Exception:
        pass
    return t.extract()


def _page_blocks(page: pymupdf.Page, vocab: set[str] | None = None) -> tuple[list[Block], dict]:
    flags = {"tables": 0, "table_low_confidence": 0, "two_column": False}
    width = page.rect.width
    d = page.get_text("dict")
    _repaired_spans(d, vocab or set(), flags)
    span_index = [(s["bbox"][0], s["bbox"][1], (s["bbox"][0] + s["bbox"][2]) / 2, (s["bbox"][1] + s["bbox"][3]) / 2,
                   CONTROL_RE.sub(" ", s["text"]))
                  for b in d["blocks"] for l in b.get("lines", []) for s in l["spans"] if s["text"].strip()]

    tables = []        # each entry: (bbox, [Block, ...]) inserted as a group
    flags["layout_tables"] = 0
    try:
        for t in page.find_tables().tables:
            rows = _table_rows(t, span_index)
            if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                cells = [re.sub(r"\s+", " ", c or "").strip() for r in rows for c in r]
                filled = [c for c in cells if c]
                # A "layout table" is prose arranged in a grid (e.g. two columns of numbered
                # footnotes). Treat each cell as its own paragraph, column by column, so unrelated
                # footnotes are not glued into one row.
                if filled and sum(len(c) for c in filled) / len(filled) > 120:
                    ncol = max(len(r) for r in rows)
                    group = []
                    for j in range(ncol):
                        for r in rows:
                            if j < len(r) and r[j] and r[j].strip():
                                group.append(Block("text", r[j].strip(), tuple(t.bbox)))
                    tables.append((tuple(t.bbox), group))
                    flags["layout_tables"] += 1
                    continue
                md, empty = _table_to_markdown(rows)
                if md:
                    tables.append((tuple(t.bbox), [Block("table", md, tuple(t.bbox))]))
                    flags["tables"] += 1
                    if empty > 0.35:
                        flags["table_low_confidence"] += 1
    except Exception as exc:  # table finder can fail on unusual pages; keep text
        flags["table_error"] = str(exc)[:200]

    text_blocks = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        bbox = tuple(b["bbox"])
        if any(_overlap(bbox, tb) > 0.5 for tb, _ in tables):
            continue
        spans = [s for l in b["lines"] for s in l["spans"] if s["text"].strip()]
        if not spans:
            continue
        lines = [" ".join(s["text"] for s in l["spans"]).strip() for l in b["lines"]]
        txt = "\n".join(x for x in lines if x)
        sizes = [s["size"] for s in spans]
        bold = sum(len(s["text"]) for s in spans if (s["flags"] & 16) or "bold" in s["font"].lower())
        total = sum(len(s["text"]) for s in spans)
        text_blocks.append(Block("text", txt, bbox, font_size=max(sizes), bold=bold > 0.6 * total))

    # two-column detection: substantial blocks entirely left AND entirely right of centre
    mid = width / 2
    left = [b for b in text_blocks if b.bbox[2] < mid + 15 and len(b.text) > 40]
    right = [b for b in text_blocks if b.bbox[0] > mid - 15 and len(b.text) > 40]
    if len(left) >= 2 and len(right) >= 2:
        flags["two_column"] = True

        def col(b):
            if b.bbox[2] < mid + 15:
                return 0
            if b.bbox[0] > mid - 15:
                return 1
            return -1  # spanning block (titles)

        first_col_y = min(b.bbox[1] for b in left + right)
        def key(b):
            c = col(b)
            if c == -1:
                return (0 if b.bbox[1] <= first_col_y else 2, 0, b.bbox[1])
            return (1, c, b.bbox[1])
        text_blocks.sort(key=key)
    else:
        text_blocks.sort(key=lambda b: (round(b.bbox[1], 0), b.bbox[0]))

    # merge tables back into reading order by vertical position
    blocks = text_blocks
    for tb, group in sorted(tables, key=lambda x: x[0][1], reverse=True):
        pos = next((i for i, b in enumerate(blocks) if b.bbox[1] > tb[1] and not flags["two_column"]), len(blocks))
        blocks[pos:pos] = group
    return blocks, flags


def _detect_running_lines(doc: pymupdf.Document) -> set[str]:
    """Lines that repeat in the top/bottom margin on >= 40% of pages are headers/footers."""
    counter = collections.Counter()
    for page in doc:
        h = page.rect.height
        seen = set()
        for b in page.get_text("blocks"):
            if b[6] != 0:
                continue
            if b[1] < 0.09 * h or b[3] > 0.91 * h:
                for line in b[4].splitlines():
                    line = _clean_text(line)
                    if line and not PAGE_NUM_RE.match(line):
                        seen.add(line)
        counter.update(seen)
    threshold = max(3, int(0.4 * doc.page_count))
    return {line for line, c in counter.items() if c >= threshold}


def extract_pdf(path: Path) -> tuple[list[PageRecord], dict]:
    doc = pymupdf.open(path)
    running = _detect_running_lines(doc)
    vocab = _build_vocab(doc)
    pages: list[PageRecord] = []
    doc_flags = collections.Counter()
    for i, page in enumerate(doc):
        h = page.rect.height
        blocks, flags = _page_blocks(page, vocab)
        printed = ""
        kept = []
        lig_fixes = 0
        for b in blocks:
            in_margin = b.bbox[1] < 0.09 * h or b.bbox[3] > 0.91 * h
            if b.kind == "text":
                lines = []
                for line in b.text.splitlines():
                    s = line.strip()
                    if in_margin and PAGE_NUM_RE.match(s):
                        printed = printed or s
                        continue
                    if _clean_text(s) in running:
                        continue
                    lines.append(line)
                txt, n = _fix_ligatures(_clean_text("\n".join(lines)))
                lig_fixes += n
                if txt:
                    kept.append(Block(b.kind, txt, b.bbox, b.font_size, b.bold))
            else:
                txt, n = _fix_ligatures(b.text)
                lig_fixes += n
                kept.append(Block(b.kind, txt, b.bbox))
        raw = page.get_text()
        page_text = "\n".join(b.text for b in kept)
        flags.update({
            "chars": len(page_text),
            "low_text": len(page_text) < 80,
            "images": len(page.get_images()),
            "numeric_thresholds": len(NUMERIC_THRESHOLD_RE.findall(page_text)),
            "ligature_fixes": lig_fixes,
            "control_chars_removed": len(CONTROL_RE.findall(raw)),
            "toc_like": _looks_like_toc(page_text),
            "residual_garble": len(RESIDUAL_GARBLE_RE.findall(page_text)),
        })
        for k, v in flags.items():
            if isinstance(v, bool):
                doc_flags[k] += int(v)
            elif isinstance(v, int):
                doc_flags[k] += v
        pages.append(PageRecord(pdf_page=i + 1, printed_page=printed, blocks=kept, flags=flags))
    summary = dict(doc_flags)
    summary["pages"] = doc.page_count
    summary["running_lines_removed"] = sorted(running)
    summary["body_font_size"] = _body_font_size(pages)
    return pages, summary


def _looks_like_toc(text: str) -> bool:
    if len(DOT_LEADER_RE.findall(text)) >= 3:
        return True
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines or not re.search(r"\b(table of )?contents?\b", " ".join(lines[:5]), re.I):
        return False
    ending_in_num = sum(1 for l in lines if re.search(r"\s\d{1,3}$", l) or re.fullmatch(r"\d{1,3}", l))
    return ending_in_num / len(lines) > 0.25


def _body_font_size(pages: list[PageRecord]) -> float:
    sizes = []
    for p in pages:
        for b in p.blocks:
            if b.kind == "text" and b.font_size:
                sizes += [round(b.font_size, 1)] * min(len(b.text), 2000)
    return statistics.median(sizes) if sizes else 11.0
