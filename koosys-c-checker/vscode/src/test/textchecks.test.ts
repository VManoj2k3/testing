import { strict as assert } from "assert";
import { test } from "node:test";
import { parseSemgrep } from "../engines";
import { DEFAULT_TEXT_OPTIONS, checkText, scan } from "../textchecks";

const HEADER = "// File: m.c\n// Purpose: test\n// Author: a\n// Date: 2026-10-21\n";
const rules = (src: string, file = "mod_a.c", opt = DEFAULT_TEXT_OPTIONS) =>
  checkText(file, src, opt).map((f) => `${f.rule}@${f.line}`);

test("scan blanks comments, strings and preprocessor lines but keeps offsets", () => {
  const src = 'int a; // x\n#define X(a) \\\n  (a)\nchar *s = "{";\n';
  const { code, comments } = scan(src);
  assert.equal(code.length, src.length);
  assert.equal(comments.length, 1);
  assert.ok(!code.includes("define") && !code.includes("{"));
});

test("header comment needs author and date", () => {
  assert.ok(rules("#include <x.h>\n").includes("KSYS-DOC-01@1"));
  assert.ok(!rules(HEADER).includes("KSYS-DOC-01@1"));
  assert.ok(rules("// Purpose only\n").includes("KSYS-DOC-01@1"));
});

test("doxygen, size and assertions per function", () => {
  const body = Array.from({ length: 70 }, () => "    x++;").join("\n");
  const src = HEADER + "void A_B(void)\n{\n    assert(1);\n}\n/** @brief C_D */\nvoid C_D(void)\n{\n" + body + "\n}\n";
  const r = rules(src);
  assert.ok(r.includes("KSYS-DOC-02@5"));
  assert.ok(!r.includes("KSYS-DOC-02@10"));
  assert.ok(r.includes("KSYS-FUNC-01@10"));
  assert.ok(r.includes("KSYS-FUNC-02@5") && r.includes("KSYS-FUNC-02@10"));
  const req = { ...DEFAULT_TEXT_OPTIONS, requirementIdPattern: "SWRS-\\d+" };
  assert.ok(rules(HEADER + "/** @brief no id */\nvoid E_F(void)\n{\n}\n", "mod_a.c", req).includes("KSYS-DOC-02@6"));
  assert.ok(!rules(HEADER + "/** @req SWRS-12 */\nvoid E_F(void)\n{\n}\n", "mod_a.c", req).includes("KSYS-DOC-02@6"));
});

test("file-scope variables: module prefix, header definitions; struct members and prototypes ignored", () => {
  const src = HEADER + [
    "uint32_t speed;",
    "uint32_t mod_speed;",
    "static uint32_t l_x;",
    "extern uint32_t other_y;",
    "uint32_t Mod_Get(void);",
    "typedef struct { uint8_t a; uint8_t b; } mod_pair_t;",
    "const uint8_t mod_tab[3] = { 1U, 2U, 3U };",
    "uint8_t table[2] = { 0U };",
  ].join("\n") + "\n";
  assert.deepEqual(rules(src).filter((r) => r.startsWith("KSYS-NAME-03")), ["KSYS-NAME-03@5", "KSYS-NAME-03@12"]);
  assert.deepEqual(rules(src, "mod_a.h").filter((r) => r.startsWith("KSYS-HDR-01")),
    ["KSYS-HDR-01@5", "KSYS-HDR-01@6", "KSYS-HDR-01@11", "KSYS-HDR-01@12"]);
  const abbr = { ...DEFAULT_TEXT_OPTIONS, moduleAbbreviation: "spd" };
  assert.ok(rules(HEADER + "uint32_t mod_speed;\n", "mod_a.c", abbr).includes("KSYS-NAME-03@5"));
  assert.ok(!rules(HEADER + "uint32_t spd_speed;\n", "mod_a.c", abbr).includes("KSYS-NAME-03@5"));
});

test("layout rules and file names", () => {
  const src = HEADER + "void A_B(void)\n{\n\tx = 1;\n   y = 2;\n    call(a,\n         b);\n    z = " + "1 + ".repeat(20) + "1;\n}\n";
  const r = rules(src);
  assert.ok(r.includes("KSYS-FMT-01@7"));
  assert.ok(r.includes("KSYS-FMT-04@8"));
  assert.ok(!r.includes("KSYS-FMT-04@10"), "continuation lines are not indentation errors");
  assert.ok(r.includes("KSYS-FMT-02@11"));
  assert.ok(rules(HEADER.replace(/\n/g, "\r\n")).includes("KSYS-FMT-03@1"));
  assert.ok(rules(HEADER, "Bad_Name.c").includes("KSYS-FILE-01@1"));
  assert.ok(!rules(HEADER, "module_name.c").includes("KSYS-FILE-02@1"), "8.3 check is off by default");
  assert.equal(rules(src, "mod_a.c", { ...DEFAULT_TEXT_OPTIONS, formatting: false }).filter((x) => x.startsWith("KSYS-FMT")).length, 0);
});

test("Semgrep KooSys findings carry their level", () => {
  const r = parseSemgrep(JSON.stringify({
    results: [{ path: "a.c", start: { line: 3, col: 1 }, end: { line: 3, col: 9 },
      extra: { message: "KSYS-CMT-01 (KooSys 4.2): use //", metadata: { koosys: "KSYS-CMT-01", level: "info" } } }],
  }));
  assert.deepEqual([r.findings[0].rule, r.findings[0].level], ["KSYS-CMT-01", "info"]);
});
