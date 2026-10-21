# KooSys CC: third-party components

KooSys CC bundles the following open-source programs, unmodified, as separate executables in
`engines/` inside the extension package. Their licences require this notice and the licence texts,
which are included in `engines/licenses/`. Keep this file with every copy of the package.

| KooSys CC component | Upstream project | Version | Licence | Source code |
|---|---|---|---|---|
| Rule engine (`engines/rules/koosyscc-rules`, renamed `semgrep-core`, and its shared libraries) | Semgrep Community Edition, © Semgrep, Inc. | 1.182.0 | LGPL-2.1 (`engines/licenses/rule-engine-LGPL-2.1.txt`) | https://github.com/semgrep/semgrep/tree/v1.182.0 |
| MISRA engine (`engines/misra/koosyscc-misra`, renamed `cppcheck`; `cfg/`, `addons/misra*.py`, `addons/cppcheckdata.py`) | Cppcheck, © Cppcheck team | 2.22.0 | GPL-3.0 (`engines/licenses/misra-engine-GPL-3.0.txt`) | https://github.com/danmar/cppcheck/tree/2.22.0 |
| Python runtime for the MISRA add-on (`engines/python`, reduced: GUI, tests and tooling removed) | CPython via python-build-standalone | 3.12.15 (build 20261013) | PSF License 2.0 (`engines/licenses/python-PSF.txt`) | https://github.com/astral-sh/python-build-standalone/releases/tag/20261013 |

The KooSys CC extension code, rule files and documentation are KooSys-internal. The engines are invoked
as separate processes and are not linked into the extension code.

Engine output was measured against the KooSys rule lists: see `COVERAGE.md`. For ISO 26262 tool
classification, the tools that produce findings are the programs listed above at these versions.
