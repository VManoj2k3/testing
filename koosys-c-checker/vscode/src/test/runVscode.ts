// Downloads VS Code and runs the integration suite in it. Engine paths come from
// KOOSYS_CPPCHECK / KOOSYS_SEMGREP (default: from PATH).
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { runTests } from "@vscode/test-electron";

async function main(): Promise<void> {
  const root = path.resolve(__dirname, "..", "..");
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "koosys-ws-"));
  fs.mkdirSync(path.join(ws, ".vscode"));
  fs.writeFileSync(path.join(ws, ".vscode", "settings.json"), JSON.stringify({
    "koosys.cppcheckPath": process.env.KOOSYS_CPPCHECK ?? "cppcheck",
    "koosys.semgrepPath": process.env.KOOSYS_SEMGREP ?? "semgrep",
  }, null, 1));
  await runTests({
    extensionDevelopmentPath: root,
    extensionTestsPath: path.join(__dirname, "suite", "index.js"),
    launchArgs: [ws, "--disable-extensions", "--disable-workspace-trust"],
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
