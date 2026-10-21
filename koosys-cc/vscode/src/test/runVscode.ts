// Downloads VS Code and runs the integration suite in it, with no settings at all: the extension must
// work from its bundled engines (vscode/engines, assembled by scripts/fetch-engines.py).
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { runTests } from "@vscode/test-electron";

async function main(): Promise<void> {
  const root = path.resolve(__dirname, "..", "..");
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "koosys-ws-"));
  // a project header in a sub folder, found through automatic include paths
  fs.mkdirSync(path.join(ws, "inc"));
  fs.writeFileSync(path.join(ws, "inc", "demo_cfg.h"), "#define DEMO_LIMIT 10\n");
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
