import { ChildProcess, spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  EnginePaths, Finding, Level, NOT_CHECKED, RuleInfo, bundledEngines, describe, levelOf, misraArgs, parseKsysCatalogue,
  parseMisra, parseRuleCsv, parseRuleEngine, parseRuleTexts, ruleEngineArgs, selectFindings,
} from "./engines";
import { DEFAULT_TEXT_OPTIONS, TextCheckOptions, checkText } from "./textchecks";

const C_FILE = /\.(c|h)$/i;
const NAME = "KooSys CC";
const HEADER_GLOB = "**/*.{h,H}";
const HEADER_EXCLUDE = "**/{node_modules,.git,.svn,.vscode-test,out,dist}/**";
const MAX_INCLUDE_DIRS = 500;

let diagnostics: vscode.DiagnosticCollection;
let output: vscode.OutputChannel;
let status: vscode.StatusBarItem;
let rules = new Map<string, RuleInfo>();
let ksysNotChecked = 0;
let engines: EnginePaths;
let enginesOk = false;
const running = new Map<string, ChildProcess[]>(); // file -> engine processes of the current check
const includeDirs = new Map<string, Promise<string[]>>(); // workspace folder -> header directories

/** Exposed for the integration test. */
export interface Api {
  check(doc: vscode.TextDocument): Promise<number>;
}

export function activate(context: vscode.ExtensionContext): Api {
  diagnostics = vscode.languages.createDiagnosticCollection("koosyscc");
  output = vscode.window.createOutputChannel(NAME);
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = "koosys.showCoverage";
  status.tooltip = "Rules that cannot be checked are listed in the coverage report";
  rules = parseRuleCsv(fs.readFileSync(context.asAbsolutePath("bundled/misra_rules.csv"), "utf8"));
  const catalogue = parseKsysCatalogue(fs.readFileSync(context.asAbsolutePath("bundled/koosys_rules.csv"), "utf8"));
  ksysNotChecked = (catalogue.get("not-checkable") ?? []).length;
  engines = bundledEngines(context.extensionPath);
  enginesOk = prepareEngines(engines);

  const watcher = vscode.workspace.createFileSystemWatcher(HEADER_GLOB, false, true, false);
  const forget = () => includeDirs.clear(); // a header appeared or vanished: rediscover on the next check
  context.subscriptions.push(
    diagnostics, output, status, watcher, watcher.onDidCreate(forget), watcher.onDidDelete(forget),
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

/** Engines ship inside the platform-specific package; restore executable bits a .vsix install may drop. */
function prepareEngines(e: EnginePaths): boolean {
  const missing = [e.misra, e.misraAddon, e.python, e.rules].filter((p) => !fs.existsSync(p));
  if (missing.length) {
    output.appendLine(`${NAME} engines missing (${missing.join(", ")}). Install the ${NAME} package built for this `
      + `operating system (win32-x64, linux-x64 or darwin-arm64).`);
    void vscode.window.showErrorMessage(`${NAME}: this package does not contain the checking engines for `
      + `${process.platform}-${process.arch}. Install the matching ${NAME} .vsix.`);
    return false;
  }
  if (process.platform !== "win32") {
    for (const p of [e.misra, e.python, e.rules]) {
      try {
        fs.chmodSync(p, 0o755);
      } catch (err) {
        output.appendLine(`cannot make ${p} executable: ${(err as Error).message}`);
      }
    }
  }
  return true;
}

function config(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration("koosys");
}

function expand(value: string, doc: vscode.TextDocument): string {
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri)?.uri.fsPath ?? path.dirname(doc.fileName);
  return value.replace(/\$\{workspaceFolder\}/g, folder);
}

/** Every workspace directory containing a header, so project includes resolve without configuration. */
function discoverIncludeDirs(doc: vscode.TextDocument): Promise<string[]> {
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (!folder) {
    return Promise.resolve([path.dirname(doc.fileName)]);
  }
  const key = folder.uri.fsPath;
  if (!includeDirs.has(key)) {
    includeDirs.set(key, (async () => {
      const headers = await vscode.workspace.findFiles(new vscode.RelativePattern(folder, HEADER_GLOB), HEADER_EXCLUDE, 20000);
      const dirs = [...new Set(headers.map((u) => path.dirname(u.fsPath)))].sort();
      if (dirs.length > MAX_INCLUDE_DIRS) {
        output.appendLine(`${dirs.length} header directories found; using the first ${MAX_INCLUDE_DIRS}. `
          + "Set koosys.includePaths to choose them.");
      }
      return dirs.slice(0, MAX_INCLUDE_DIRS);
    })());
  }
  return includeDirs.get(key)!;
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
    const env = { ...process.env, PYTHONUTF8: "1", PYTHONNOUSERSITE: "1" };
    const p = spawn(exe, args, { cwd: path.dirname(file), env, windowsHide: true });
    procs.push(p);
    p.stdout?.on("data", (d) => (stdout += d));
    p.stderr?.on("data", (d) => (stderr += d));
    p.on("error", (e) => resolve({ code: -1, stdout, stderr: `${path.basename(exe)}: ${e.message}`, cancelled: false }));
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
  status.text = `$(sync~spin) ${NAME}: checking…`;
  status.show();

  const jobs: Promise<Finding[]>[] = [Promise.resolve(runTextChecks(file, doc.getText(), cfg))];
  if (enginesOk) {
    const userIncludes = cfg.get<string[]>("includePaths", []).map((p) => expand(p, doc));
    const includes = [...new Set([...userIncludes, ...(cfg.get<boolean>("autoIncludePaths", true) ? await discoverIncludeDirs(doc) : [])])];
    const defines = cfg.get<string[]>("defines", []);
    const includesFile = path.join(context.globalStorageUri.fsPath, `includes-${Buffer.from(file).toString("hex").slice(-40)}.txt`);
    fs.mkdirSync(path.dirname(includesFile), { recursive: true });
    fs.writeFileSync(includesFile, includes.join("\n")); // a file, not -I flags: Windows limits command lines to 32k chars
    // build dir: the add-on's temporary dump files go here, never into the user's source folders (a
    // cancelled check would otherwise leave *.dump files behind); it also caches results of unchanged files
    const buildDir = path.join(context.globalStorageUri.fsPath, "misra-build");
    fs.mkdirSync(buildDir, { recursive: true });
    const args = misraArgs(file, [], defines, engines);
    args.splice(args.length - 1, 0, `--includes-file=${includesFile}`, `--cppcheck-build-dir=${buildDir}`);
    jobs.push(run(file, engines.misra, args, procs).then((r) => {
      if (r.code === -1) {
        output.appendLine(`MISRA engine could not start: ${r.stderr}`);
      } else if (/#error|preprocessorErrorDirective/.test(r.stderr)) {
        output.appendLine(`MISRA engine stopped at an #error in ${file}: a configuration header or define is missing `
          + "(koosys.defines, koosys.includePaths).");
      }
      return r.cancelled ? [] : parseMisra(r.stderr);
    }));
    jobs.push(run(file, engines.rules, ruleEngineArgs(file, context.asAbsolutePath("bundled/rules.yaml")), procs).then((r) => {
      if (r.code === -1) {
        output.appendLine(`rule engine could not start: ${r.stderr}`);
        return [];
      }
      const parsed = parseRuleEngine(r.stdout);
      parsed.errors.forEach((e) => output.appendLine(`rule engine: ${e}`)); // parse failures are shown, never silent
      parseTrouble = parsed.errors.length > 0;
      return r.cancelled ? [] : parsed.findings;
    }));
  }
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
  status.text = `${NAME}: ${found.length} issue${found.length === 1 ? "" : "s"} · `
    + `${NOT_CHECKED.length} MISRA + ${ksysNotChecked} KooSys rules not checked`
    + (parseTrouble ? " · $(warning) file only partly parsed" : "")
    + (enginesOk ? "" : " · $(error) engines missing");
  status.tooltip = parseTrouble
    ? "Parts of this file could not be parsed (often macros such as FUNC()/P2VAR()); rules in those parts were "
      + `not checked. See the ${NAME} output panel.`
    : "Rules that cannot be checked are listed in the coverage report";
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
    output.appendLine(`text checks failed on ${file}: ${(e as Error).message}`);
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
  d.source = NAME;
  d.code = f.rule.startsWith("KSYS-") ? f.rule : `MISRA ${f.rule}`;
  return d;
}
