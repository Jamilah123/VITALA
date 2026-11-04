/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

function sourceFiles(folder: string): string[] {
  return readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(name) && !name.endsWith(".test.ts") ? [path] : [];
  });
}

// Common feminine-specific instructions and address forms the UI must not use.
const FEMININE = new RegExp(
  [
    "أدخلي", "اختاري", "اكتبي", "أعيدي", "راجعي", "تأكدي", "عدّلي", "عدلي", "استخدمي", "أضيفي", "ابدئي",
    "احفظي", "افتحي", "اتصلي", "ناقشي", "سجّلي", "تريدين", "تستطيعين", "تختارين", "تحتاجين", "تدخلي",
    "ترَي", "أنتِ", "لكِ", "عليكِ", "سجّلتِ", "أجريتِ",
  ].join("|"),
  "g",
);

describe("Arabic UI wording", () => {
  it("uses no feminine-specific instructions in any source file", () => {
    const found = sourceFiles(SRC).flatMap((file) =>
      [...readFileSync(file, "utf-8").matchAll(FEMININE)].map((match) => `${relative(SRC, file)}: ${match[0]}`),
    );
    expect(found).toEqual([]);
  });

  it("never promises when a check is due or calls recommendations approved", () => {
    for (const file of sourceFiles(join(SRC, "screens"))) {
      expect(readFileSync(file, "utf-8"), file).not.toMatch(/ومتى موعدها|الخريطة التجريبية|توصياتك المعتمدة|التوصيات المعتمدة/);
    }
  });
});
