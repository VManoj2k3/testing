// Copies the shared rule files into the extension so the .vsix is self-contained. The pattern rule
// files are merged into one bundled/rules.yaml, because the rule engine takes a single rules file.
const fs = require("fs");
const path = require("path");
const src = path.join(__dirname, "..", "..");
const dst = path.join(__dirname, "..", "bundled");
fs.rmSync(dst, { recursive: true, force: true });
fs.mkdirSync(dst, { recursive: true });
const patternDir = path.join(src, "rules", "patterns");
const bodies = fs.readdirSync(patternDir).filter((f) => f.endsWith(".yaml")).sort().map((f) => {
  const text = fs.readFileSync(path.join(patternDir, f), "utf8");
  const i = text.search(/^rules:\s*$/m);
  if (i < 0) {
    throw new Error(`${f}: no top-level "rules:" key`);
  }
  return `  # ---- ${f}\n` + text.slice(i).replace(/^rules:\s*\n/, "");
});
fs.writeFileSync(path.join(dst, "rules.yaml"), "rules:\n" + bodies.join("\n"));
for (const f of ["misra_rules.csv", "koosys_rules.csv"]) {
  fs.copyFileSync(path.join(src, "rules", f), path.join(dst, f));
}
fs.copyFileSync(path.join(src, "COVERAGE.md"), path.join(dst, "COVERAGE.md"));
fs.copyFileSync(path.join(src, "THIRD_PARTY_NOTICES.md"), path.join(dst, "THIRD_PARTY_NOTICES.md"));
console.log("rules bundled into", dst);
