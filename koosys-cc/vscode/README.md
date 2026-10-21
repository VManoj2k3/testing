# KooSys CC (VS Code)

Checks `.c`/`.h` files when you save against:
- the KooSys MISRA rule list (`KooSys_MisraRules.pdf`, 200 rules, MISRA C:2023);
- the KooSys coding guidelines (KooSys v2.1 with the Quantum Leaps standard and AUTOSAR StandardTypes):
  naming, types, comments, documentation, function size, layout.

**Nothing else to install, no paths to set.** The checking engines are built into the package.
Everything runs on your machine: no code, metrics or telemetry leave the workstation.

**This is an early-warning tool, not a qualified MISRA checker.**
- MISRA: 153 of the 200 rules are detected on seeded test cases; 46 are not checked at all.
- KooSys guidelines: of the 49 items, 25 are checked, 9 map to MISRA rules and 15 can't be checked by any tool.

See "KooSys CC: Show Rule Coverage" or `COVERAGE.md`. Where the source documents contradict each
other, `GUIDELINE_DECISIONS.md` records what is enforced. A clean result does not mean the file is
MISRA-compliant. ISO 26262 evidence still needs the project's qualified checker.

## Install
There is one package per operating system, because the engines are native programs:

| Your computer | Package |
|---|---|
| Windows (64-bit) | `koosys-cc-win32-x64-<version>.vsix` |
| Linux (64-bit, glibc 2.35+: Ubuntu 22.04 or newer) | `koosys-cc-linux-x64-<version>.vsix` |
| macOS (Apple Silicon M1/M2/M3…) | `koosys-cc-darwin-arm64-<version>.vsix` |

To install, open VS Code → Extensions (`Ctrl+Shift+X`) → `…` menu → **Install from VSIX…**, then pick
the file. From a terminal: `code --install-extension koosys-cc-<platform>-<version>.vsix`.

If you had the earlier test version "KooSys C Checker" installed, uninstall it first.

## What you see
- Squiggles:
  - red for MISRA Mandatory and Required rules;
  - yellow for MISRA Advisory rules and KooSys warnings (naming, types, documentation);
  - blue Info hints for layout, comment style, function size and assertions.

  Findings appear in the Problems panel (`Ctrl+Shift+M`). The hover gives the rule (`MISRA 15.1`,
  `KSYS-NAME-02`).
- Status bar: `KooSys CC: N issues · 46 MISRA + 15 KooSys rules not checked`. It adds
  `file only partly parsed` when part of the file could not be parsed (often macros such as
  `FUNC()`/`P2VAR()`); rules aren't checked in those parts. Click it to open the coverage report.
- Output panel "KooSys CC": timing, engine messages, and parse failures. A file that could not be
  parsed is reported here, never shown as clean.
- Command palette: "KooSys CC: Check Current File".

Include paths are found automatically: every folder in the workspace that contains a header file is
used. Checks run in the background, and a newer save cancels the running one. On the FreeRTOS kernel,
the MISRA engine takes 3–25 s per file, the rule engine 0.2–1 s, and the text checks milliseconds.
Findings inside included headers are shown only when the header itself is checked.

## Settings (all optional)
| Setting | Default | Meaning |
|---|---|---|
| `koosys.runOnSave` | `true` | Check on save |
| `koosys.autoIncludePaths` | `true` | Use every workspace folder containing a header as an include path |
| `koosys.includePaths` | `[]` | Extra include folders (outside the workspace) |
| `koosys.defines` | `[]` | Preprocessor defines, only needed when a header stops with `#error` without them |
| `koosys.disabledRules` | `[]` | Rule ids not to report (project deviations), e.g. `["15.5", "KSYS-FUNC-02"]` |
| `koosys.wholeProgramRules` | `5.8 5.9 8.5 8.6 8.7` | Hidden in single-file checks, where they are wrong (8.7 would flag every public function) |
| `koosys.formatting` | `true` | Layout rules: tabs, more than 78 columns, CRLF, 4-space indentation (Info). Turn off for legacy code. |
| `koosys.maxLineLength` / `koosys.maxFunctionLines` | `78` / `60` | Limits for KSYS-FMT-02 and KSYS-FUNC-01 |
| `koosys.minAssertions`, `koosys.assertionMacros` | `2`, `assert`, `Q_ASSERT`… | KSYS-FUNC-02. Set to `0` to disable. |
| `koosys.requirementIdPattern` | — | Regex the doxygen comment of each function must contain, e.g. `SWRS-[A-Z]+-\\d+` |
| `koosys.moduleAbbreviation` | — | Required prefix for globals in this project (KSYS-NAME-03) |
| `koosys.checkDosFileNames` | `false` | DOS 8.3 file names (contradicts KooSys 4.1's own example) |
| `koosys.ruleTextsFile` | — | Optional CSV `rule,text` with the guideline wording for hovers (company text, not bundled) |

Windows: with git's `core.autocrlf=true`, working copies get CRLF endings and KSYS-FMT-03 fires on
every file. KooSys asks for LF, so set `core.autocrlf=input`, or turn the check off with
`koosys.formatting: false`.

## Third-party components
The engines are open-source programs bundled unmodified. Their licences require the notices in
`THIRD_PARTY_NOTICES.md` and the licence texts in `engines/licenses/`, both shipped in the package.

## Build (maintainers)
```
npm install
python scripts/fetch-engines.py --target linux-x64 --misra-build <engine build dir> --misra-src <engine source dir>
npm test                          # unit tests
npm run test:vscode               # end-to-end test in a downloaded VS Code (Linux needs xvfb-run)
npm run package:target -- linux-x64   # → koosys-cc-linux-x64-<version>.vsix
```
CI (`.github/workflows/koosys-cc.yml`) builds and tests all three platform packages and attaches them
to a GitHub release.
