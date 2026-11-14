"""Create a clean, publishable copy of the project for GitHub (the private working folder is never modified).

    python scripts/prepare_public_release.py ../VITALA_RAG_public

What it does
  * copies code, tests, notebooks (outputs stripped), docs, the source registry, evaluation datasets, synthetic
    profiles and evaluation summaries (summary.json / report.md only)
  * copies raw source files ONLY when data/source_registry.csv says redistribution_allowed=yes
    (today: the public-domain openFDA metformin label); everything else must be obtained by each user
  * never copies .env, virtual environments, caches, processed chunks, indexes, archives or logs
  * scans every copied file for the values in your local .env, for key-like strings and for local user paths,
    and refuses to finish if anything is found

It does not run git. Review the folder, then: cd <target> && git init && git add . && git commit.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY_DIRS = ["src", "tests", "notebooks", "scripts", "data/eval", "data/synthetic", ".vscode"]
COPY_FILES = ["requirements.txt", "pyproject.toml", ".env.example", ".gitignore", "data/source_registry.csv",
              "data/raw/medications/candidate_drug_manifest.json", "LICENSE"]
SKIP_PARTS = {".venv", "venv", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", ".mypy_cache"}
TEXT_EXT = {".py", ".md", ".txt", ".json", ".jsonl", ".csv", ".toml", ".ipynb", ".cfg", ".ini", ".yml", ".yaml", ""}
KEY_RE = re.compile(r"(sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9\-_]{20,}|\b[a-f0-9]{32}\b(?=.*key)|"
                    r"(API_KEY|api_key)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,})", re.I)
USER_PATH_RE = re.compile(r"[A-Za-z]:\\\\?Users\\\\?[^\\\\/\s\"']+|/Users/[^/\s\"']+|/home/[^/\s\"']+")


def strip_notebook(src: Path, dst: Path) -> None:
    nb = json.loads(src.read_text(encoding="utf-8"))
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"], cell["execution_count"] = [], None
        cell.get("metadata", {}).pop("execution", None)
    dst.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def env_values() -> list[str]:
    p = ROOT / ".env"
    if not p.exists():
        return []
    vals = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            name, v = line.split("=", 1)
            v = v.split("#")[0].strip().strip("'\"")
            # only secret-bearing settings (provider names, model names and API versions are not secrets)
            secret_name = any(s in name.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "ENDPOINT"))
            if secret_name and len(v) >= 8 and not v.startswith("<"):
                vals.append(v)
    return vals


def main(target: Path) -> int:
    target = target.resolve()
    if target == ROOT or ROOT in target.parents:
        print("Choose a target folder OUTSIDE the project.")
        return 2
    if target.exists():
        shutil.rmtree(target)
    copied = []
    for d in COPY_DIRS:
        for src in (ROOT / d).rglob("*") if (ROOT / d).exists() else []:
            if src.is_dir() or SKIP_PARTS & set(src.parts) or any(x.endswith(".egg-info") for x in src.parts):
                continue
            dst = target / src.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix == ".ipynb":
                strip_notebook(src, dst)
            else:
                shutil.copy2(src, dst)
            copied.append(dst)
    for f in COPY_FILES:
        if (ROOT / f).exists():
            (target / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, target / f)
            copied.append(target / f)
    # raw sources whose licence allows redistribution
    with open(ROOT / "data/source_registry.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["redistribution_allowed"] == "yes" and row["scope_status"] == "in_scope" and (ROOT / row["raw_path"]).exists():
                dst = target / row["raw_path"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / row["raw_path"], dst)
                copied.append(dst)
                print("  raw source included (redistribution allowed):", row["raw_path"])
    # evaluation summaries only (per-question files quote licensed source text)
    for run in sorted((ROOT / "results/evaluation").glob("*/")):
        for name in ("summary.json", "report.md"):
            if (run / name).exists():
                dst = target / "results/evaluation" / run.name / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(run / name, dst)
                copied.append(dst)
    # ---- scans
    secrets, problems = env_values(), []
    for p in copied:
        if p.suffix.lower() not in TEXT_EXT:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel = p.relative_to(target)
        for v in secrets:
            if v in text:
                problems.append(f"{rel}: contains a value from your local .env")
        if KEY_RE.search(text):
            problems.append(f"{rel}: key-like string: {KEY_RE.search(text).group(0)[:12]}...")
        m = USER_PATH_RE.search(text)
        if m and p.name != "prepare_public_release.py":
            problems.append(f"{rel}: local user path '{m.group(0)}'")
    if problems:
        print("REFUSED - fix these before publishing:\n  " + "\n  ".join(problems))
        shutil.rmtree(target)
        return 1
    print(f"Public copy written to {target} ({len(copied)} files). Not included: .env, data/raw (except files whose "
          "licence allows redistribution), data/processed, indexes, archives, per-question results.")
    print("Next: review it, then  git init && git add . && git commit -m 'Initial public version'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "VITALA_RAG_public"))
