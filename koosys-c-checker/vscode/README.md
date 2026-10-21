# KooSys C Checker (VS Code)

Checks `.c`/`.h` files when you save against:
- the KooSys MISRA rule list (`KooSys_MisraRules.pdf`, 200 rules);
- the KooSys coding guidelines (KooSys v2.1 with the Quantum Leaps standard and AUTOSAR StandardTypes):
  naming, types, comments, documentation, function size, layout.

Everything runs on your machine: cppcheck (MISRA addon), Semgrep with bundled rules, and built-in
TypeScript text checks.
No code, metrics or telemetry leave the workstation. Semgrep runs with metrics and the version check off.

**This is an early-warning tool, not a qualified MISRA checker.** It detects 153 of the 200 rules
on seeded test cases, and 46 are not checked at all. Of the 49 KooSys guideline items, 25 are
checked, 9 map to MISRA rules and 15 can't be checked by a tool. See "KooSys: Show Rule Coverage" or
`COVERAGE.md`. Where the source documents contradict each other, `GUIDELINE_DECISIONS.md` records
what is enforced. A clean result does not mean the file is MISRA-compliant. ISO 26262 evidence still
needs the project's qualified checker.

## What you see
- Squiggles:
  - red for MISRA Mandatory and Required rules;
  - yellow for MISRA Advisory rules and KooSys warnings (naming, types, documentation);
  - blue Info hints for layout, comment style, function size and assertions.

  Findings appear in the Problems panel (`Ctrl+Shift+M`). The hover gives the rule (`MISRA 15.1`,
  `KSYS-NAME-02`) and which engine found it.
- Status bar: `KooSys: N issues · 46 MISRA + 15 KooSys rules not checked`. It adds
  `file only partly parsed` when Semgrep couldn't parse part of the file (often macros such as
  `FUNC()`/`P2VAR()`); rules aren't checked in those parts. Click it to open the coverage report.
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
| `koosys.formatting` | `true` | Layout rules: tabs, more than 78 columns, CRLF, 4-space indentation (Info). Turn off for legacy code. |
| `koosys.maxLineLength` / `koosys.maxFunctionLines` | `78` / `60` | Limits for KSYS-FMT-02 and KSYS-FUNC-01 |
| `koosys.minAssertions`, `koosys.assertionMacros` | `2`, `assert`, `Q_ASSERT`… | KSYS-FUNC-02. Set to `0` to disable. |
| `koosys.requirementIdPattern` | — | Regex the doxygen comment of each function must contain, e.g. `SWRS-[A-Z]+-\\d+` |
| `koosys.moduleAbbreviation` | — | Required prefix for globals in this project (KSYS-NAME-03) |
| `koosys.checkDosFileNames` | `false` | DOS 8.3 file names (contradicts KooSys 4.1's own example) |

Windows: with git's `core.autocrlf=true`, working copies get CRLF endings and KSYS-FMT-03 fires on
every file. KooSys asks for LF, so set `core.autocrlf=input`, or turn the check off with
`koosys.formatting: false`.

## Build
```
npm install
npm test                 # unit tests (no VS Code needed)
npm run test:vscode      # downloads VS Code and runs the end-to-end test (Linux needs xvfb-run)
npm run package          # → koosys-c-checker-<version>.vsix
```
