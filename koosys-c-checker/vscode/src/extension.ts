import { ChildProcess, spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  Finding, Level, NOT_CHECKED, RuleInfo, cppcheckArgs, describe, levelOf, parseCppcheck, parseKsysCatalogue,
  parseRuleCsv, parseRuleTexts, parseSemgrep, selectFindings, semgrepArgs,
} from "./engines";
import { DEFAULT_TEXT_OPTIONS, TextCheckOptions, checkText } from "./textchecks";

const C_FILE = /\.(c|h)$/i;

let diagnostics: vscode.DiagnosticCollection;
let output: vscode.OutputChannel;
let status: vscode.StatusBarItem;
let rules = new Map<string, RuleInfo>();
let ksysNotChecked = 0;
const running = new Map<string, ChildProcess[]>(); // file -> engine processes of the current check

/** Exposed for the integration test. */
export interface Api {
  check(doc: vscode.TextDocument): Promise<number>;
}

export function activate(context: vscode.ExtensionContext): Api {
  diagnostics = vscode.languages.createDiagnosticCollection("koosys");
  output = vscode.window.createOutputChannel("KooSys C Checker");
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = "koosys.showCoverage";
  status.tooltip = "MISRA rules neither engine can check are listed in the coverage report";
  rules = parseRuleCsv(fs.readFileSync(context.asAbsolutePath("bundled/misra_rules.csv"), "utf8"));
  const catalogue = parseKsysCatalogue(fs.readFileSync(context.asAbsolutePath("bundled/koosys_rules.csv"), "utf8"));
  ksysNotChecked = (catalogue.get("not-checkable") ?? []).length;

  context.subscriptions.push(
    diagnostics, output, status,
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (C_FILE.test(doc.fileName) && config().get<boolean>("runOnSave", true)) {
        void check(context, doc);
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => diagnostics.delete(doc.uri)),
    vscode.commands.registerCommand("koosys.checkFile", () => {
      const doc = vscode.window.activeTextEditor?.document;
      if (doc && C_FILE.test(doc.fileName)) {
        void check(context, doc);
      }
    }),
    vscode.commands.registerCommand("koosys.showCoverage", async () => {
      const uri = vscode.Uri.file(context.asAbsolutePath("bundled/COVERAGE.md"));
      await vscode.commands.executeCommand("markdown.showPreview", uri);
    }),
  );
  return { check: (doc) => check(context, doc) };
}

export function deactivate(): void {
  for (const procs of running.values()) {
    procs.forEach((p) => p.kill());
  }
}

function config(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration("koosys");
}

function expand(value: string, doc: vscode.TextDocument): string {
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri)?.uri.fsPath ?? path.dirname(doc.fileName);
  return value.replace(/\$\{workspaceFolder\}/g, folder);
}

interface RunResult {
  code: number | null;
  stdout: string;
  stderr: string;
  cancelled: boolean;
}

function run(file: string, exe: string, args: string[], procs: ChildProcess[]): Promise<RunResult> {
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    const env = { ...process.env, SEMGREP_SEND_METRICS: "off", SEMGREP_ENABLE_VERSION_CHECK: "0", PYTHONUTF8: "1" };
    const p = spawn(exe, args, { cwd: path.dirname(file), env, windowsHide: true });
    procs.push(p);
    p.stdout?.on("data", (d) => (stdout += d));
    p.stderr?.on("data", (d) => (stderr += d));
    p.on("error", (e) => resolve({ code: -1, stdout, stderr: `${exe}: ${e.message}`, cancelled: false }));
    p.on("close", (code, signal) => resolve({ code, stdout, stderr, cancelled: signal !== null }));
  });
}

async function check(context: vscode.ExtensionContext, doc: vscode.TextDocument): Promise<number> {
  const file = doc.fileName;
  running.get(file)?.forEach((p) => p.kill()); // a newer save supersedes the running check
  const procs: ChildProcess[] = [];
  running.set(file, procs);
  let parseTrouble = false;
  const cfg = config();
  const started = Date.now();
  status.text = "$(sync~spin) KooSys: checking…";
  status.show();

  const cppExe = cfg.get<string>("cppcheckPath", "cppcheck");
  const sgExe = cfg.get<string>("semgrepPath", "semgrep");
  const includes = cfg.get<string[]>("includePaths", []).map((p) => expand(p, doc));
  const defines = cfg.get<string[]>("defines", []);
  const jobs: Promise<Finding[]>[] = [
    run(file, cppExe, cppcheckArgs(file, includes, defines), procs).then((r) => {
      if (r.code === -1) {
        output.appendLine(`cppcheck not runnable: ${r.stderr} (set koosys.cppcheckPath)`);
      } else if (/#error|preprocessorErrorDirective/.test(r.stderr)) {
        output.appendLine(`cppcheck hit an #error in ${file}: add the project's include paths/defines (koosys.includePaths, koosys.defines).`);
      }
      return r.cancelled ? [] : parseCppcheck(r.stderr);
    }),
  ];
  if (sgExe) {
    const rulesDir = context.asAbsolutePath("bundled/semgrep");
    jobs.push(run(file, sgExe, semgrepArgs(file, rulesDir), procs).then((r) => {
      if (r.code === -1) {
        output.appendLine(`semgrep not runnable: ${r.stderr} (set koosys.semgrepPath, or empty to disable)`);
        return [];
      }
      const parsed = parseSemgrep(r.stdout);
      parsed.errors.forEach((e) => output.appendLine(`semgrep: ${e}`)); // parse failures are shown, never silent
      parseTrouble = parsed.errors.length > 0;
      return r.cancelled ? [] : parsed.findings;
    }));
  }
  jobs.push(Promise.resolve(runTextChecks(file, doc.getText(), cfg)));
  const all = (await Promise.all(jobs)).flat();
  if (running.get(file) !== procs) {
    return -1; // superseded by a newer check
  }
  running.delete(file);

  const hidden = new Set([...cfg.get<string[]>("disabledRules", []), ...cfg.get<string[]>("wholeProgramRules", [])]);
  const texts = loadTexts(cfg.get<string>("ruleTextsFile", ""), doc);
  const found = selectFindings(all, file, hidden);
  diagnostics.set(doc.uri, found.map((f) => toDiagnostic(f, texts)));
  const secs = ((Date.now() - started) / 1000).toFixed(1);
  status.text = `KooSys: ${found.length} issue${found.length === 1 ? "" : "s"} · `
    + `${NOT_CHECKED.length} MISRA + ${ksysNotChecked} KooSys rules not checked`
    + (parseTrouble ? " · $(warning) file only partly parsed" : "");
  status.tooltip = parseTrouble
    ? "Semgrep could not parse parts of this file (often macros such as FUNC()/P2VAR()); rules in those parts were not checked. See the KooSys output panel."
    : "MISRA rules neither engine can check are listed in the coverage report";
  output.appendLine(`${path.basename(file)}: ${found.length} findings in ${secs}s`);
  return found.length;
}

function runTextChecks(file: string, text: string, cfg: vscode.WorkspaceConfiguration): Finding[] {
  const d = DEFAULT_TEXT_OPTIONS;
  const opt: TextCheckOptions = {
    formatting: cfg.get("formatting", d.formatting),
    maxLineLength: cfg.get("maxLineLength", d.maxLineLength),
    maxFunctionLines: cfg.get("maxFunctionLines", d.maxFunctionLines),
    minAssertions: cfg.get("minAssertions", d.minAssertions),
    assertionMacros: cfg.get("assertionMacros", d.assertionMacros),
    requirementIdPattern: cfg.get("requirementIdPattern", d.requirementIdPattern),
    moduleAbbreviation: cfg.get("moduleAbbreviation", d.moduleAbbreviation),
    checkDosFileNames: cfg.get("checkDosFileNames", d.checkDosFileNames),
  };
  try {
    return checkText(file, text, opt);
  } catch (e) {
    output.appendLine(`KooSys text checks failed on ${file}: ${(e as Error).message}`);
    return [];
  }
}

const SEVERITY: Record<Level, vscode.DiagnosticSeverity> = {
  error: vscode.DiagnosticSeverity.Error,
  warning: vscode.DiagnosticSeverity.Warning,
  info: vscode.DiagnosticSeverity.Information,
};

function loadTexts(file: string, doc: vscode.TextDocument): Map<string, string> {
  if (!file) {
    return new Map();
  }
  try {
    return parseRuleTexts(fs.readFileSync(expand(file, doc), "utf8"));
  } catch (e) {
    output.appendLine(`koosys.ruleTextsFile unreadable: ${(e as Error).message}`);
    return new Map();
  }
}

function toDiagnostic(f: Finding, texts: Map<string, string>): vscode.Diagnostic {
  const info = rules.get(f.rule);
  const range = new vscode.Range(f.line - 1, f.column - 1, f.endLine - 1, Math.max(f.endColumn - 1, f.column));
  const d = new vscode.Diagnostic(range, describe(f, info, texts.get(f.rule)), SEVERITY[levelOf(f, info)]);
  d.source = `KooSys (${f.engine})`;
  d.code = f.rule.startsWith("KSYS-") ? f.rule : `MISRA ${f.rule}`;
  return d;
}
