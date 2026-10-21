# KooSys C Checker (VS Code)

Checks `.c`/`.h` files against the KooSys MISRA rule list (`KooSys_MisraRules.pdf`, 200 rules) when you
save. Everything runs on your machine: cppcheck (MISRA addon) and Semgrep with bundled rules.
No code, metrics or telemetry leave the workstation. Semgrep runs with metrics and the version check off.

**This is an early-warning tool, not a qualified MISRA checker.** It detects 153 of the 200 rules
on seeded test cases. 46 rules are not checked at all. See "KooSys: Show Rule Coverage", or
`COVERAGE.md`. A clean result does not mean the file is MISRA-compliant. ISO 26262 evidence still
needs the project's qualified checker.

## What you see
- Squiggles: red for Mandatory and Required rules, yellow for Advisory. Findings appear in the
  Problems panel (`Ctrl+Shift+M`). Hover text gives the rule number, its category, and which engine found it.
- Status bar: `KooSys: N issues · 46 rules not checked`. Click it to open the coverage report.
- Output panel "KooSys C Checker": timing, engine errors, and Semgrep parse failures. A file that
  could not be parsed is reported here, never shown as clean.
- Command palette: "KooSys: Check Current File".

Checks take seconds, not milliseconds. On the FreeRTOS kernel, cppcheck needs 3–25 s per file and
Semgrep about 2 s. They run in the background, and a newer save cancels the running check.
Findings inside included headers are shown only when the header itself is checked.

## Install

1. **Engines** (once per machine):

   | OS | cppcheck (2.22 or later; the MISRA addon is included) | Semgrep |
   |---|---|---|
   | Windows | Installer from cppcheck.sourceforge.io; add its folder to PATH | `pipx install semgrep` (Python 3.10+; native Windows support is beta) |
   | Linux | Distribution packages are often older than 2.22: build from source or use your package source | `pipx install semgrep` |
   | macOS | `brew install cppcheck` | `brew install semgrep` or `pipx install semgrep` |

   The addon needs Python 3 on PATH, because cppcheck runs `misra.py` with it.
2. **Extension:** VS Code → Extensions → `…` → *Install from VSIX…* → `koosys-c-checker-<version>.vsix`.
   Or from a terminal: `code --install-extension koosys-c-checker-<version>.vsix`.
3. **Per project**, in `.vscode/settings.json`:
   ```json
   {
     "koosys.includePaths": ["${workspaceFolder}/include", "${workspaceFolder}/config"],
     "koosys.defines": ["CPU_FREQ=8000000"]
   }
   ```
   Without the project's include paths and config headers, cppcheck stops at the first `#error`
   and reports almost nothing. The output panel tells you when that happens.

## Settings
| Setting | Default | Meaning |
|---|---|---|
| `koosys.runOnSave` | `true` | Check on save |
| `koosys.cppcheckPath` / `koosys.semgrepPath` | `cppcheck` / `semgrep` | Executables. Set Semgrep to empty to disable it. |
| `koosys.includePaths`, `koosys.defines` | `[]` | Passed to cppcheck as `-I` and `-D` |
| `koosys.disabledRules` | `[]` | Rule numbers not to report (project deviations) |
| `koosys.wholeProgramRules` | `5.8 5.9 8.5 8.6 8.7` | Hidden in single-file checks, where they are wrong (8.7 would flag every public function) |
| `koosys.ruleTextsFile` | — | Optional CSV `rule,text` with the guideline wording for hovers. Not bundled, because the text belongs to the company document. |

## Build
```
npm install
npm test                 # unit tests (no VS Code needed)
npm run test:vscode      # downloads VS Code and runs the end-to-end test (Linux needs xvfb-run)
npm run package          # → koosys-c-checker-<version>.vsix
```
