// Runs inside VS Code: a violating file gets diagnostics on save, and they clear once fixed.
import { strict as assert } from "assert";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

const BAD = [
  "#include <stdint.h>",
  "#include <stdarg.h>",
  "int32_t demo(int32_t a)",
  "{",
  "    if (a > 0)",
  "    {",
  "        goto done;",
  "    }",
  "    a = a + 1;",
  "done:",
  "    return a;",
  "}",
  "",
].join("\n");

function codes(uri: vscode.Uri): string[] {
  return vscode.languages.getDiagnostics(uri).map((d) => String(d.code));
}

async function waitFor(pred: () => boolean, ms: number): Promise<void> {
  const end = Date.now() + ms;
  while (!pred()) {
    if (Date.now() > end) {
      throw new Error("timed out waiting for diagnostics");
    }
    await new Promise((r) => setTimeout(r, 200));
  }
}

export async function run(): Promise<void> {
  const ws = vscode.workspace.workspaceFolders![0].uri.fsPath;
  const file = path.join(ws, "demo.c");
  fs.writeFileSync(file, BAD);
  const doc = await vscode.workspace.openTextDocument(file);
  const editor = await vscode.window.showTextDocument(doc);
  const ext = vscode.extensions.getExtension("koosys.koosys-c-checker")!;
  await ext.activate();

  // 1. Saving a violating file reports goto (15.1, cppcheck) and <stdarg.h> (17.1, Semgrep).
  await editor.edit((e) => e.insert(new vscode.Position(BAD.split("\n").length - 1, 0), "\n"));
  await doc.save();
  await waitFor(() => codes(doc.uri).includes("MISRA 15.1") && codes(doc.uri).includes("MISRA 17.1"), 120000);
  const d = vscode.languages.getDiagnostics(doc.uri).find((x) => x.code === "MISRA 15.1")!;
  assert.equal(d.range.start.line, 6);
  assert.match(d.message, /Rule 15\.1 \(Advisory\)/);
  assert.ok(!codes(doc.uri).includes("MISRA 8.7"), "whole-program rule 8.7 must be hidden on save");
  // KooSys guidelines: 'demo' is not Module_Function style (warning); no assertions is Info level.
  const all = vscode.languages.getDiagnostics(doc.uri);
  assert.equal(all.find((x) => x.code === "KSYS-NAME-02")?.severity, vscode.DiagnosticSeverity.Warning);
  assert.equal(all.find((x) => x.code === "KSYS-FUNC-02")?.severity, vscode.DiagnosticSeverity.Information);

  // 2. Fixing the code and saving clears those diagnostics.
  const fixed = BAD.replace("#include <stdarg.h>\n", "")
    .replace("    if (a > 0)\n    {\n        goto done;\n    }\n    a = a + 1;\ndone:\n", "    if (a <= 0)\n    {\n        a = a + 1;\n    }\n");
  await editor.edit((e) => e.replace(new vscode.Range(0, 0, doc.lineCount, 0), fixed));
  await doc.save();
  await waitFor(() => !codes(doc.uri).includes("MISRA 15.1") && !codes(doc.uri).includes("MISRA 17.1"), 120000);
  console.log("integration: diagnostics after fix:", codes(doc.uri));
}
