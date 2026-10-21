import { strict as assert } from "assert";
import { test } from "node:test";
import * as path from "path";
import {
  Finding, NOT_CHECKED, cppcheckArgs, describe, parseCppcheck, parseRuleCsv, parseRuleTexts, parseSemgrep,
  samePath, selectFindings,
} from "../engines";

const file = path.resolve("/work/src/motor.c");

test("parseCppcheck keeps MISRA-numbered findings only", () => {
  const stderr = [
    `${file}\t12\t5\t15.1\tmisra violation (use --rule-texts=<file> to get proper output)`,
    `${file}\t20\t3\tconstVariable\tVariable 'x' can be declared as const`,
    `${file}\t30\t1\t9.1\tUninitialized variable: u`,
    "Checking motor.c ...",
  ].join("\n");
  const f = parseCppcheck(stderr);
  assert.equal(f.length, 2);
  assert.deepEqual([f[0].rule, f[0].line, f[0].column, f[0].detail], ["15.1", 12, 5, ""]);
  assert.equal(f[1].detail, "Uninitialized variable: u");
});

test("parseSemgrep reads MISRA metadata and surfaces errors", () => {
  const json = JSON.stringify({
    results: [
      { path: file, start: { line: 4, col: 1 }, end: { line: 4, col: 20 }, extra: { message: "m", metadata: { misra: "17.1" } } },
      { path: file, start: { line: 5, col: 1 }, end: { line: 5, col: 2 }, extra: { message: "other", metadata: {} } },
    ],
    errors: [{ message: "Syntax error at line 9" }],
  });
  const r = parseSemgrep(json);
  assert.equal(r.findings.length, 1);
  assert.equal(r.findings[0].rule, "17.1");
  assert.deepEqual(r.errors, ["Syntax error at line 9"]);
  assert.equal(parseSemgrep("not json").errors.length, 1);
});

test("selectFindings drops other files, hidden rules and cross-engine duplicates", () => {
  const mk = (rule: string, line: number, f = file, engine: Finding["engine"] = "cppcheck"): Finding =>
    ({ rule, file: f, line, column: 1, endLine: line, endColumn: 2, engine, detail: "" });
  const sel = selectFindings(
    [mk("15.1", 9), mk("15.1", 9, file, "semgrep"), mk("8.7", 3), mk("20.2", 1, "/work/include/FreeRTOS.h"), mk("17.1", 2)],
    file, new Set(["8.7"]));
  assert.deepEqual(sel.map((s) => `${s.rule}@${s.line}`), ["17.1@2", "15.1@9"]);
});

test("samePath ignores case on Windows only", () => {
  assert.equal(samePath("C:\\Src\\A.c", "c:\\src\\a.c", "win32"), true);
  assert.equal(samePath("/src/A.c", "/src/a.c", "linux"), false);
});

test("rule csv, texts and descriptions", () => {
  const rules = parseRuleCsv("rule,category,latest_amendment\n15.1,Advisory,no\n9.7,Mandatory,yes\n");
  assert.equal(rules.get("9.7")?.latestAmendment, true);
  const texts = parseRuleTexts('15.1,"The goto statement should not be used, ever"\nnot a rule,x\n');
  assert.equal(texts.get("15.1"), "The goto statement should not be used, ever");
  const f: Finding = { rule: "15.1", file, line: 1, column: 1, endLine: 1, endColumn: 2, engine: "cppcheck", detail: "" };
  assert.equal(describe(f, rules.get("15.1"), texts.get("15.1")),
    "MISRA C:2023 Rule 15.1 (Advisory): The goto statement should not be used, ever");
  assert.match(describe(f, undefined, undefined), /see the KooSys MISRA rule list/);
});

test("cppcheck args carry includes, defines and the tab template", () => {
  const a = cppcheckArgs("x.c", ["/inc"], ["A=1"]);
  assert.ok(a.includes("-I/inc") && a.includes("-DA=1") && a.includes("--addon=misra"));
  assert.ok(a.some((s) => s.startsWith("--template=") && s.includes("\\t")));
  assert.equal(new Set(NOT_CHECKED).size, NOT_CHECKED.length);
});
