// Copies the shared rule files into the extension so the .vsix is self-contained.
const fs = require("fs");
const path = require("path");
const src = path.join(__dirname, "..", "..");
const dst = path.join(__dirname, "..", "bundled");
fs.rmSync(dst, { recursive: true, force: true });
fs.mkdirSync(path.join(dst, "semgrep"), { recursive: true });
for (const f of fs.readdirSync(path.join(src, "rules", "semgrep"))) {
  fs.copyFileSync(path.join(src, "rules", "semgrep", f), path.join(dst, "semgrep", f));
}
fs.copyFileSync(path.join(src, "rules", "misra_rules.csv"), path.join(dst, "misra_rules.csv"));
fs.copyFileSync(path.join(src, "rules", "koosys_rules.csv"), path.join(dst, "koosys_rules.csv"));
fs.copyFileSync(path.join(src, "COVERAGE.md"), path.join(dst, "COVERAGE.md"));
console.log("rules bundled into", dst);
