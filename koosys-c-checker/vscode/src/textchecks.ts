// KooSys rules that need exact brace scope or the raw text (layout, file names, comments, function
// size). Pure TypeScript: runs in milliseconds, no external process. No vscode imports.
import * as path from "path";
import { Finding, Level } from "./engines";

export interface TextCheckOptions {
  formatting: boolean;
  maxLineLength: number;
  maxFunctionLines: number;
  minAssertions: number;
  assertionMacros: string[];
  requirementIdPattern: string; // empty = requirement IDs in doxygen blocks are not checked
  moduleAbbreviation: string; // empty = any lowercase module prefix ("abc_")
  checkDosFileNames: boolean;
}

export const DEFAULT_TEXT_OPTIONS: TextCheckOptions = {
  formatting: true,
  maxLineLength: 78,
  maxFunctionLines: 60,
  minAssertions: 2,
  assertionMacros: ["assert", "Q_ASSERT", "Q_REQUIRE", "Q_ENSURE", "Q_INVARIANT", "Q_ALLEGE"],
  requirementIdPattern: "",
  moduleAbbreviation: "",
  checkDosFileNames: false,
};

interface Comment {
  start: number; // offset
  end: number; // offset after the comment
  text: string;
}

/** Code with comments, string/char literals and preprocessor lines blanked (offsets and newlines kept). */
export function scan(src: string): { code: string; comments: Comment[] } {
  const out = src.split("");
  const comments: Comment[] = [];
  const blank = (from: number, to: number) => {
    for (let k = from; k < to; k++) {
      if (out[k] !== "\n") {
        out[k] = " ";
      }
    }
  };
  let i = 0;
  let lineStart = true;
  while (i < src.length) {
    const c = src[i];
    if (lineStart && /[ \t]/.test(c)) {
      i++;
      continue;
    }
    if (lineStart && c === "#") { // preprocessor line, including backslash continuations
      let j = i;
      while (j < src.length && !(src[j] === "\n" && src[j - 1] !== "\\")) {
        j++;
      }
      blank(i, j);
      i = j;
      continue;
    }
    lineStart = c === "\n";
    if (c === "/" && src[i + 1] === "/") {
      let j = i;
      while (j < src.length && src[j] !== "\n") {
        j++;
      }
      comments.push({ start: i, end: j, text: src.slice(i, j) });
      blank(i, j);
      i = j;
    } else if (c === "/" && src[i + 1] === "*") {
      const j = src.indexOf("*/", i + 2);
      const end = j < 0 ? src.length : j + 2;
      comments.push({ start: i, end, text: src.slice(i, end) });
      blank(i, end);
      i = end;
    } else if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < src.length && src[j] !== c && src[j] !== "\n") {
        j += src[j] === "\\" ? 2 : 1;
      }
      blank(i + 1, j);
      i = j + 1;
    } else {
      i++;
    }
  }
  return { code: out.join(""), comments };
}

/** Offset -> 1-based line, by binary search over line starts (files can have 10k+ lines). */
function lineIndex(src: string): (offset: number) => number {
  const starts = [0];
  for (let k = 0; k < src.length; k++) {
    if (src[k] === "\n") {
      starts.push(k + 1);
    }
  }
  return (offset: number) => {
    let lo = 0;
    let hi = starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid] <= offset) {
        lo = mid;
      } else {
        hi = mid - 1;
      }
    }
    return lo + 1;
  };
}

function finding(file: string, rule: string, level: Level, line: number, column: number, detail: string): Finding {
  return { rule, file, line, column, endLine: line, endColumn: column + 1, engine: "koosys", detail, level };
}

interface FunctionDef {
  name: string;
  headerStart: number; // offset of the first header character
  bodyStart: number; // offset of '{'
  bodyEnd: number; // offset of matching '}'
}

interface Statement {
  start: number;
  end: number; // offset of ';'
  text: string; // code text with brace contents removed
  hadBraces: boolean;
  preBrace: string; // text before the first '{'
}

/** Walks depth-0 code: function definitions and file-scope statements. */
function structure(code: string): { functions: FunctionDef[]; statements: Statement[] } {
  const functions: FunctionDef[] = [];
  const statements: Statement[] = [];
  let stmtStart = -1;
  let flat = "";
  let preBrace = "";
  let hadBraces = false;
  let i = 0;
  while (i < code.length) {
    const c = code[i];
    if (stmtStart < 0 && /\S/.test(c)) {
      stmtStart = i;
      flat = "";
      preBrace = "";
      hadBraces = false;
    }
    if (c === "{") {
      let depth = 1;
      let j = i + 1;
      while (j < code.length && depth > 0) {
        if (code[j] === "{") depth++;
        else if (code[j] === "}") depth--;
        j++;
      }
      const head = flat.trim();
      const fn = /([A-Za-z_]\w*)\s*\([^;{}]*\)\s*$/.exec(head);
      if (!hadBraces && fn && !/^(typedef|struct|enum|union)\b/.test(head) && !head.includes("=")) {
        functions.push({ name: fn[1], headerStart: stmtStart, bodyStart: i, bodyEnd: j - 1 });
        stmtStart = -1;
      } else {
        if (!hadBraces) {
          preBrace = flat;
        }
        hadBraces = true;
        flat += " {} ";
      }
      i = j;
      continue;
    }
    if (c === ";" && stmtStart >= 0) {
      statements.push({ start: stmtStart, end: i, text: flat.trim(), hadBraces, preBrace: hadBraces ? preBrace : flat });
      stmtStart = -1;
    } else if (stmtStart >= 0) {
      flat += c;
    }
    i++;
  }
  return { functions, statements };
}

function variableName(stmt: Statement): string | undefined {
  const t = stmt.text;
  if (/^(typedef|extern)\b/.test(t) || /^(struct|enum|union)\b[^=]*\{\}\s*$/.test(t)) {
    return undefined;
  }
  if (stmt.hadBraces && !stmt.preBrace.includes("=")) {
    return undefined; // struct/enum/union definition
  }
  const decl = stmt.preBrace.split("=")[0];
  if (/\(/.test(decl)) {
    return undefined; // prototype or function pointer
  }
  const m = /([A-Za-z_]\w*)\s*(\[[^\]]*\]\s*)*$/.exec(decl.split(",")[0].trim());
  return m && !/^(void|int|char|long|short|unsigned|signed|float|double)$/.test(m[1]) ? m[1] : undefined;
}

export function checkText(file: string, src: string, opt: TextCheckOptions = DEFAULT_TEXT_OPTIONS): Finding[] {
  const out: Finding[] = [];
  const base = path.basename(file);
  const isHeader = /\.h$/i.test(base);
  const lines = src.split("\n");
  const lineOf = lineIndex(src);
  const { code, comments } = scan(src);
  const codeLines = code.split("\n");
  const { functions, statements } = structure(code);

  // FILE: lowercase names (KooSys 4.1/4.8), optional DOS 8.3 (QL 2)
  if (!/^[a-z0-9_]+\.[ch]$/.test(base)) {
    out.push(finding(file, "KSYS-FILE-01", "info", 1, 1, `file name '${base}' should be lowercase with underscores (module_name.c)`));
  }
  if (opt.checkDosFileNames && !/^[^.]{1,8}\.[^.]{1,3}$/.test(base)) {
    out.push(finding(file, "KSYS-FILE-02", "info", 1, 1, `file name '${base}' does not fit the DOS 8.3 convention`));
  }

  // FMT: layout (KooSys 4.8 / QL 2, 3.2), Info level
  if (opt.formatting) {
    let prevEnds = true;
    lines.forEach((raw, idx) => {
      const n = idx + 1;
      const line = raw.replace(/\r$/, "");
      if (raw.endsWith("\r") && n === 1) {
        out.push(finding(file, "KSYS-FMT-03", "info", 1, 1, "CRLF line endings; use Unix LF"));
      }
      const tab = line.indexOf("\t");
      if (tab >= 0) {
        out.push(finding(file, "KSYS-FMT-01", "info", n, tab + 1, "tab character; indent with 4 spaces"));
      }
      if (line.length > opt.maxLineLength) {
        out.push(finding(file, "KSYS-FMT-02", "info", n, opt.maxLineLength + 1, `line longer than ${opt.maxLineLength} columns`));
      }
      const codeLine = codeLines[idx]?.replace(/\r$/, "") ?? "";
      const indent = /^ */.exec(line)![0].length;
      if (codeLine.trim() && prevEnds && indent % 4 !== 0) {
        out.push(finding(file, "KSYS-FMT-04", "info", n, 1, "indentation is not a multiple of 4 spaces"));
      }
      if (codeLine.trim()) {
        prevEnds = /[;{}]\s*$/.test(codeLine) || /^\s*(case\b.*|default\s*):\s*$/.test(codeLine);
      }
    });
  }

  // DOC-01: header comment with purpose/author/date (KooSys 4.2)
  // the header is the run of comments the file starts with (only whitespace between them)
  const firstCode = src.search(/\S/);
  const header: string[] = [];
  for (let k = 0; k < comments.length; k++) {
    const c = comments[k];
    const startsRun = k === 0 && c.start === firstCode;
    const continuesRun = k > 0 && header.length === k && !/\S/.test(src.slice(comments[k - 1].end, c.start));
    if (!startsRun && !continuesRun) {
      break;
    }
    header.push(c.text);
  }
  const headerText = header.join("\n");
  if (!headerText || !/author/i.test(headerText) || !/date/i.test(headerText)) {
    out.push(finding(file, "KSYS-DOC-01", "warning", 1, 1,
      "file must start with a header comment stating the module purpose, author and date"));
  }

  // per function: DOC-02 doxygen block, FUNC-01 size, FUNC-02 assertions
  const assertRe = new RegExp(`\\b(${opt.assertionMacros.map((m) => m.replace(/\W/g, "")).join("|")})\\s*\\(`, "g");
  for (const f of functions) {
    const line = lineOf(f.headerStart);
    const col = f.headerStart - src.lastIndexOf("\n", f.headerStart - 1);
    const before = comments.filter((c) => c.end <= f.headerStart && !/\S/.test(code.slice(c.end, f.headerStart)));
    const doc = before.length ? before[before.length - 1] : undefined;
    const isDoxygen = doc && /^(\/\*\*|\/\/\/|\/\/!)/.test(doc.text);
    if (!isDoxygen) {
      out.push(finding(file, "KSYS-DOC-02", "warning", line, col, `function '${f.name}' needs a doxygen comment (name, purpose, parameters, SWRS requirement ID)`));
    } else if (opt.requirementIdPattern && !new RegExp(opt.requirementIdPattern).test(doc!.text)) {
      out.push(finding(file, "KSYS-DOC-02", "warning", line, col, `doxygen comment of '${f.name}' has no requirement ID matching ${opt.requirementIdPattern}`));
    }
    const bodyLines = lineOf(f.bodyEnd) - lineOf(f.bodyStart) + 1;
    if (bodyLines > opt.maxFunctionLines) {
      out.push(finding(file, "KSYS-FUNC-01", "info", line, col, `function '${f.name}' is ${bodyLines} lines; keep functions under ${opt.maxFunctionLines} lines (one page)`));
    }
    const asserts = (code.slice(f.bodyStart, f.bodyEnd).match(assertRe) ?? []).length;
    if (opt.minAssertions > 0 && asserts < opt.minAssertions) {
      out.push(finding(file, "KSYS-FUNC-02", "info", line, col, `function '${f.name}' has ${asserts} assertion(s); KooSys asks for at least ${opt.minAssertions}`));
    }
  }

  // file-scope variables: NAME-03 module prefix (KooSys 4.3), HDR-01 no definitions in headers (AUTOSAR SRS_BSW_00308)
  const prefix = opt.moduleAbbreviation
    ? new RegExp(`^${opt.moduleAbbreviation.replace(/\W/g, "")}_[a-z0-9_]+$`)
    : /^[a-z][a-z0-9]*_[a-z0-9_]+$/;
  for (const s of statements) {
    const name = variableName(s);
    if (!name || /^static\b/.test(s.text) || /\bstatic\b/.test(s.preBrace)) {
      continue; // static file-scope variables: KSYS-NAME-07 (Semgrep)
    }
    const offset = s.start + Math.max(0, code.slice(s.start, s.end).indexOf(name));
    const line = lineOf(offset);
    const col = offset - src.lastIndexOf("\n", offset - 1);
    if (!prefix.test(name)) {
      out.push(finding(file, "KSYS-NAME-03", "warning", line, col,
        `global variable '${name}' needs the module prefix (${opt.moduleAbbreviation || "module_name"}_variable)`));
    }
    if (isHeader) {
      out.push(finding(file, "KSYS-HDR-01", "warning", line, col, `'${name}' is defined in a header; define it in the .c file and declare it extern here`));
    }
  }
  return out;
}
