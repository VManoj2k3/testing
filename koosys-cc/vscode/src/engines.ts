// KooSys CC engine invocation and output parsing. No vscode imports, so it can be unit-tested with plain node.
// Two bundled engines (see THIRD_PARTY_NOTICES.md): the MISRA engine and the pattern rule engine.
import * as path from "path";

export type Category = "Mandatory" | "Required" | "Advisory";
export type Level = "error" | "warning" | "info";

export interface Finding {
  rule: string; // MISRA rule number ("15.1") or KooSys guideline id ("KSYS-NAME-01")
  file: string;
  line: number; // 1-based
  column: number; // 1-based
  endLine: number;
  endColumn: number;
  engine: "misra" | "rules" | "text";
  detail: string;
  level?: Level; // KooSys guideline findings; MISRA findings take their level from the rule category
}

export interface RuleInfo {
  category: Category;
  latestAmendment: boolean;
}

const TAB = "\t";
export const MISRA_TEMPLATE = ["{file}", "{line}", "{column}", "{id}", "{message}"].join("\\t");
const MISRA_ID = /^\d+\.\d+$/;

export function parseRuleCsv(text: string): Map<string, RuleInfo> {
  const rules = new Map<string, RuleInfo>();
  for (const line of text.split(/\r?\n/).slice(1)) {
    const [rule, category, amendment] = line.split(",");
    if (rule && category) {
      rules.set(rule, { category: category as Category, latestAmendment: amendment === "yes" });
    }
  }
  return rules;
}

/** Optional company-provided rule texts: "rule,text" per line; text may contain commas. */
export function parseRuleTexts(text: string): Map<string, string> {
  const texts = new Map<string, string>();
  for (const line of text.split(/\r?\n/)) {
    const i = line.indexOf(",");
    if (i > 0 && MISRA_ID.test(line.slice(0, i).trim())) {
      texts.set(line.slice(0, i).trim(), line.slice(i + 1).trim().replace(/^"|"$/g, ""));
    }
  }
  return texts;
}

/** Paths of the engines shipped inside the extension (engines/, assembled by scripts/fetch-engines.py). */
export interface EnginePaths {
  misra: string;
  misraAddon: string;
  python: string;
  rules: string;
}

export function bundledEngines(extensionDir: string, platform = process.platform): EnginePaths {
  const e = path.join(extensionDir, "engines");
  const exe = platform === "win32" ? ".exe" : "";
  return {
    misra: path.join(e, "misra", `koosyscc-misra${exe}`),
    misraAddon: path.join(e, "misra", "addons", "misra.py"),
    python: platform === "win32" ? path.join(e, "python", "python.exe") : path.join(e, "python", "bin", "python3.12"),
    rules: path.join(e, "rules", `koosyscc-rules${exe}`),
  };
}

export function misraArgs(file: string, includePaths: string[], defines: string[], eng: Pick<EnginePaths, "misraAddon" | "python">): string[] {
  return [
    `--addon=${eng.misraAddon}`,
    `--addon-python=${eng.python}`,
    "--enable=style,warning,portability",
    "--report-type=misra-c-2023",
    "--language=c",
    "--std=c11",
    "-q",
    `--template=${MISRA_TEMPLATE}`,
    ...includePaths.map((p) => `-I${p}`),
    ...defines.map((d) => `-D${d}`),
    file,
  ];
}

/** The MISRA engine writes findings to stderr; keep only MISRA-numbered ones (core checks are mapped by --report-type). */
export function parseMisra(stderr: string): Finding[] {
  const out: Finding[] = [];
  for (const line of stderr.split(/\r?\n/)) {
    const parts = line.split(TAB);
    if (parts.length < 5 || !MISRA_ID.test(parts[3])) {
      continue;
    }
    const ln = Math.max(1, parseInt(parts[1], 10) || 1);
    const col = Math.max(1, parseInt(parts[2], 10) || 1);
    const msg = parts.slice(4).join(TAB);
    out.push({
      rule: parts[3], file: parts[0], line: ln, column: col, endLine: ln, endColumn: col + 1, engine: "misra",
      // Without rule texts the addon's message is a placeholder; the hover shows our own text instead.
      detail: msg.startsWith("misra violation") ? "" : msg,
    });
  }
  return out;
}

/** Rule engine: one C file against one merged rules file (no network, no Python). */
export function ruleEngineArgs(file: string, rulesFile: string): string[] {
  return ["-rules", rulesFile, "-lang", "c", "-json", file];
}

export interface RuleEngineResult {
  findings: Finding[];
  errors: string[];
}

export function parseRuleEngine(stdout: string): RuleEngineResult {
  let data: any;
  try {
    const start = stdout.indexOf("{"); // progress dots may precede the JSON document
    data = JSON.parse(start >= 0 ? stdout.slice(start) : "{}");
  } catch {
    return { findings: [], errors: ["rule engine output was not JSON: " + stdout.slice(0, 200)] };
  }
  const findings: Finding[] = [];
  for (const r of data.results ?? []) {
    const meta = r?.extra?.metadata ?? {};
    const rule = meta.misra ?? meta.koosys;
    if (!rule) {
      continue;
    }
    findings.push({
      rule: String(rule), file: r.path, line: r.start.line, column: r.start.col,
      endLine: r.end.line, endColumn: r.end.col, engine: "rules", detail: r.extra.message ?? "",
      ...(meta.koosys ? { level: (meta.level ?? "warning") as Level } : {}),
    });
  }
  const errors = (data.errors ?? []).map((e: any) => String(e.message ?? e.error_type ?? e.type ?? "rule engine error"));
  return { findings, errors };
}

export function samePath(a: string, b: string, platform = process.platform): boolean {
  const norm = (p: string) => {
    const r = path.resolve(p);
    return platform === "win32" ? r.toLowerCase() : r;
  };
  return norm(a) === norm(b);
}

/**
 * Keep findings located in the checked file (the MISRA engine also reports included headers: ~350 per
 * FreeRTOS file), drop disabled and whole-program rules, and merge duplicates across engines.
 */
export function selectFindings(findings: Finding[], file: string, hidden: Set<string>): Finding[] {
  const seen = new Set<string>();
  const out: Finding[] = [];
  for (const f of findings) {
    if (!samePath(f.file, file) || hidden.has(f.rule)) {
      continue;
    }
    const key = `${f.rule}:${f.line}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push(f);
    }
  }
  return out.sort((a, b) => a.line - b.line || a.column - b.column);
}

export function describe(f: Finding, info: RuleInfo | undefined, text: string | undefined): string {
  if (f.rule.startsWith("KSYS-")) {
    return f.detail.startsWith(f.rule) ? f.detail : `${f.rule}: ${f.detail}`;
  }
  const cat = info ? ` (${info.category})` : "";
  const body = text || f.detail || "see the KooSys MISRA rule list";
  return `MISRA C:2023 Rule ${f.rule}${cat}: ${body}`;
}

export function levelOf(f: Finding, info: RuleInfo | undefined): Level {
  if (f.level) {
    return f.level;
  }
  return info?.category === "Advisory" ? "warning" : "error";
}

/** KooSys guideline catalogue (rules/koosys_rules.csv): ids per status. */
export function parseKsysCatalogue(text: string): Map<string, string[]> {
  const byStatus = new Map<string, string[]>();
  for (const line of text.split(/\r?\n/).slice(1)) {
    const cols = line.split(",");
    if (cols.length >= 5 && cols[0]) {
      byStatus.set(cols[4], [...(byStatus.get(cols[4]) ?? []), cols[0]]);
    }
  }
  return byStatus;
}

/** Rules in the list that neither engine checks (from COVERAGE measurement), for the status bar. */
export const NOT_CHECKED = [
  "1.1", "1.5", "2.8", "5.1", "5.6", "5.7", "6.3", "8.3", "8.5", "8.8", "8.15", "9.6", "9.7", "10.1", "10.2", "11.7",
  "12.3", "12.6", "14.3", "17.9", "17.11", "17.12", "17.13", "18.2", "18.9", "20.12", "21.2", "21.14", "21.17",
  "21.22", "21.23", "21.26", "22.1", "22.3", "22.12", "22.13", "22.14", "22.15", "22.16", "22.17", "22.19",
  "22.20", "23.4", "23.5", "23.6", "23.7",
];
