# Rule coverage: KooSys MISRA list (200 rules) and KooSys coding guidelines

Measured 2026-10-21 with cppcheck 2.22.0 (free MISRA addon + core checks, `--report-type=misra-c-2023`,
matching KooSys guideline v2.1, which moved to MISRA C:2023; the 2012 mode gave identical results)
and Semgrep CE 1.182.0 with `rules/semgrep/misra_gaps.yaml`. Regenerate with:

    python tests/score.py --cppcheck <cppcheck> --semgrep <semgrep> --md COVERAGE_table.md

## How to read this
- Each rule has one or two seeded violations in `tests/misra/` (marked `// EXPECT <rule>`).
  "detected" = the engine flagged that rule within 2 lines of the marker.
- **One seeded example is not a proof of reliability.** It shows the check exists and fires on a
  typical case. Missed variants, and false alarms on real code, are not measured by this table.
- `(+N)` = the engine also reported that rule on N unmarked lines. Most are genuine (fixtures
  break other rules incidentally); they are not counted as false alarms without a manual review.
- 1.1 and 1.4 have no fixture: 1.1 is the compiler's job (syntax/constraints/translation limits),
  1.4 is flagged by cppcheck as a side effect elsewhere (it reports C11 keywords as emergent features).

## Summary

| | Detected (either engine) | Missed by both | No fixture |
|---|---|---|---|
| Mandatory (23) | 16 | 7 | 0 |
| Required (137) | 103 | 32 | 2 |
| Advisory (40) | 34 | 6 | 0 |
| **Total (200)** | **153** | **45** | **2** |

- cppcheck alone: 133. Semgrep adds 20 that cppcheck's free addon does not check
  (mostly the latest-amendment C11 rules: atomics, threads, `_Generic`, alignment, `_Noreturn`).
- **Missed by both (45):** 1.5 2.8 5.1 5.6 5.7 6.3 8.3 8.5 8.8 8.15 9.6 9.7 10.1 10.2 11.7 12.3 12.6
  14.3 17.9 17.11 17.12 17.13 18.2 18.9 20.12 21.2 21.14 21.17 21.22 21.23 21.26 22.1 22.3
  22.12–22.17 22.19 22.20 23.4–23.7. These need type information, data flow or cross-file
  analysis, or are C11 thread/atomic rules only commercial checkers cover. The extension lists
  them as **"not checked"**, never as passing.

## False alarms on compliant code (`tests/clean/`)
- Semgrep: 0.
- cppcheck: 8.7 on every external function (single-file check cannot see other callers, so it is
  noise on save; only meaningful in a whole-project scan) and 1.4 on `_Generic` (policy question:
  MISRA Amendment 2 lists `_Generic` as an emergent feature).

## Real code: FreeRTOS kernel (7 files, 17k lines, template FreeRTOSConfig.h)

| File | Lines | cppcheck time | Findings in the file itself | Findings in included headers | Semgrep time | Semgrep findings |
|---|---|---|---|---|---|---|
| croutine.c | 407 | 3.8 s | 3 | 381 | 1.9 s | 0 |
| event_groups.c | 887 | 7.0 s | 31 | 414 | 1.9 s | 0 |
| list.c | 248 | 3.3 s | 6 | 345 | 1.8 s | 0 |
| queue.c | 3400 | 12.7 s | 91 | 417 | 1.8 s | 0 |
| stream_buffer.c | 1757 | 8.5 s | 73 | 402 | 1.8 s | 0 |
| tasks.c | 8967 | 25.5 s | 142 | 381 | 1.8 s | 0 |
| timers.c | 1345 | 7.0 s | 49 | 404 | 1.9 s | 0 |

(4 CPU Linux container.) Consequences for the extension: checks run in the background with
cancellation (not "<100 ms"), and only findings located in the checked file are shown.
Without the project's include paths and config headers cppcheck stops at the first `#error`
(seen on FreeRTOS), so include paths/defines are an extension setting.
The MISRA gap rules are text (regex) rules, so they don't depend on Semgrep's C parser. The
KooSys guideline rules do: on FreeRTOS, Semgrep **could not parse `tasks.c` at all** and parsed
`croutine.c` and `timers.c` only partly, because of macros such as `PRIVILEGED_DATA static List_t …`.
Expect the same on AUTOSAR code that uses `FUNC()` or `P2VAR()` macros. The extension shows
"file only partly parsed" in the status bar when this happens.

## MISRA directives
The KooSys MISRA list contains only the rules, not the directives (Dir 1.1–5.3), and the free cppcheck
addon does not check directives. A full MISRA C:2023 compliance claim also needs the directives:
review, or the project's qualified checker.

## KooSys coding guidelines (KooSys v2.1, Quantum Leaps, AUTOSAR StandardTypes)

The catalogue is `rules/koosys_rules.csv` (49 items). Contradictions and how they were resolved are in
`GUIDELINE_DECISIONS.md`.

| Status | Items |
|---|---|
| Checked by Semgrep or the built-in text checks | 25 (24 on by default; 8.3 file names off) |
| Already covered by a MISRA rule (goto, single exit, braces, recursion, malloc, return values, pointer arithmetic, scope, explicit types) | 9 |
| Not checkable (English comments, intent, error handling, ISO 26262 process…) | 15 |

Fixtures (`tests/koosys/`): **all 24 enabled rules detected**, and **0 findings** on the compliant
module `tests/koosys/clean/` (CI fails otherwise).

False alarms found in review and fixed (2026-10-21). `tests/koosys/regressions.c` marks each case with
`NOEXPECT`, and CI fails if one comes back:

| Rule | Was flagged (correct code) | Fix |
|---|---|---|
| KSYS-TYPE-01 | bit-fields `unsigned int flag : 1;`, which MISRA 6.1 requires | bit-fields exempt |
| KSYS-NAME-08 | `string_utils_count`, `memory_pool_size` (reserved `str…`/`mem…` prefixes) | library prefixes only for underscore-free names such as `strcount` |
| KSYS-NAME-04 | lowercase identifiers inside enum initialiser expressions | only enumerator names are checked |
| KSYS-DOC-01 | German header fields `Autor:` / `Datum:` | both languages accepted |

FreeRTOS kernel (7 files, 17k lines; it follows its own style, so high counts are expected and are
not false alarms). Text checks took 0.19 s for all 7 files, Semgrep 6.7 s.

| Rule | Findings | Rule | Findings |
|---|---|---|---|
| FMT-02 line > 78 | 2518 | NAME-03 global prefix | 38 |
| CMT-01 block comment | 948 | NAME-04 macro case | 38 |
| NAME-01 variable case | 276 | NAME-06 length > 31 | 25 |
| DOC-02 no doxygen | 275 | NAME-07 static without l_ | 24 |
| FUNC-02 < 2 assertions | 275 | PTR-01 uninitialised pointer | 22 |
| PRE-01 preprocessor | 151 | NAME-05 typedef case | 13 |
| NAME-02 function case | 145 | DOC-01 header comment | 7 |
| FUNC-01 > 60 lines | 64 | LOOP-01 unbounded loop | 4 |

What this means for adoption: on existing code the layout and comment rules produce thousands of Info
hints. Start with `koosys.formatting: false` on legacy modules, or with a clang-format pass.

## Per-rule table (MISRA)
| Rule | Category | Latest amendment | cppcheck | semgrep | Status |
|---|---|---|---|---|---|
| 1.1 | Required | yes | no fixture | no fixture | no fixture |
| 1.2 | Advisory | no | 0/1 | 1/1 | detected |
| 1.3 | Required | yes | 1/1 (+7) | 0/1 | detected |
| 1.4 | Required | yes | no fixture | no fixture | no fixture |
| 1.5 | Required | yes | 0/1 | 0/1 | missed |
| 2.1 | Required | no | 1/1 | 0/1 | detected |
| 2.2 | Required | no | 1/1 (+6) | 0/1 | detected |
| 2.3 | Advisory | no | 1/1 (+1) | 0/1 | detected |
| 2.4 | Advisory | no | 1/1 (+3) | 0/1 | detected |
| 2.5 | Advisory | no | 1/1 (+6) | 0/1 | detected |
| 2.6 | Advisory | no | 1/1 | 0/1 | detected |
| 2.7 | Advisory | no | 1/1 | 0/1 | detected |
| 2.8 | Advisory | yes | 0/1 | 0/1 | missed |
| 3.1 | Required | no | 1/1 | 0/1 | detected |
| 3.2 | Required | no | 0/1 | 1/1 | detected |
| 4.1 | Required | no | 1/1 | 0/1 | detected |
| 4.2 | Advisory | no | 1/1 | 0/1 | detected |
| 5.1 | Required | no | 0/1 | 0/1 | missed |
| 5.2 | Required | no | 1/1 | 0/1 | detected |
| 5.3 | Required | no | 1/1 | 0/1 | detected |
| 5.4 | Required | no | 1/1 | 0/1 | detected |
| 5.5 | Required | no | 1/1 | 0/1 | detected |
| 5.6 | Required | no | 0/1 | 0/1 | missed |
| 5.7 | Required | no | 0/1 | 0/1 | missed |
| 5.8 | Required | no | 1/1 (+1) | 0/1 | detected |
| 5.9 | Advisory | no | 1/1 (+1) | 0/1 | detected |
| 6.1 | Required | no | 1/1 | 0/1 | detected |
| 6.2 | Required | no | 1/1 | 0/1 | detected |
| 6.3 | Required | yes | 0/1 | 0/1 | missed |
| 7.1 | Required | no | 1/1 | 0/1 | detected |
| 7.2 | Required | no | 1/1 | 0/1 | detected |
| 7.3 | Required | no | 1/1 (+2) | 0/1 | detected |
| 7.4 | Required | no | 1/1 (+1) | 0/1 | detected |
| 7.5 | Mandatory | yes | 0/1 | 1/1 | detected |
| 7.6 | Required | yes | 0/1 | 1/1 | detected |
| 8.1 | Required | no | 0/1 | 1/1 | detected |
| 8.2 | Required | no | 2/2 (+1) | 0/2 | detected |
| 8.3 | Required | no | 0/1 | 0/1 | missed |
| 8.4 | Required | no | 1/1 (+65) | 0/1 | detected |
| 8.5 | Required | no | 0/1 (+2) | 0/1 | missed |
| 8.6 | Required | no | 1/1 (+1) | 0/1 | detected |
| 8.7 | Advisory | no | 1/1 (+4) | 0/1 | detected |
| 8.8 | Required | no | 0/1 | 0/1 | missed |
| 8.9 | Advisory | no | 1/1 | 0/1 | detected |
| 8.10 | Required | no | 1/1 | 0/1 | detected |
| 8.11 | Advisory | no | 1/1 | 0/1 | detected |
| 8.12 | Required | no | 1/1 | 0/1 | detected |
| 8.13 | Advisory | no | 1/1 (+3) | 0/1 | detected |
| 8.14 | Required | no | 1/1 | 0/1 | detected |
| 8.15 | Required | yes | 0/1 | 0/1 | missed |
| 8.16 | Advisory | yes | 0/1 | 1/1 | detected |
| 8.17 | Advisory | yes | 0/1 | 1/1 | detected |
| 9.1 | Mandatory | no | 1/1 (+5) | 0/1 | detected |
| 9.2 | Required | no | 1/1 (+1) | 0/1 | detected |
| 9.3 | Required | no | 1/1 | 0/1 | detected |
| 9.4 | Required | no | 1/1 | 0/1 | detected |
| 9.5 | Required | no | 1/1 | 0/1 | detected |
| 9.6 | Required | yes | 0/1 | 0/1 | missed |
| 9.7 | Mandatory | yes | 0/1 | 0/1 | missed |
| 10.1 | Required | no | 0/1 | 0/1 | missed |
| 10.2 | Required | no | 0/1 | 0/1 | missed |
| 10.3 | Required | no | 1/1 | 0/1 | detected |
| 10.4 | Required | no | 1/1 (+2) | 0/1 | detected |
| 10.5 | Advisory | no | 1/1 | 0/1 | detected |
| 10.6 | Required | no | 1/1 (+1) | 0/1 | detected |
| 10.7 | Required | no | 1/1 | 0/1 | detected |
| 10.8 | Required | no | 1/1 (+1) | 0/1 | detected |
| 11.1 | Required | no | 1/1 (+1) | 0/1 | detected |
| 11.2 | Required | no | 1/1 | 0/1 | detected |
| 11.3 | Required | no | 1/1 | 0/1 | detected |
| 11.4 | Advisory | no | 1/1 (+1) | 0/1 | detected |
| 11.5 | Advisory | no | 1/1 (+2) | 0/1 | detected |
| 11.6 | Required | no | 1/1 (+1) | 0/1 | detected |
| 11.7 | Required | no | 0/1 | 0/1 | missed |
| 11.8 | Required | no | 1/1 | 0/1 | detected |
| 11.9 | Required | no | 1/1 | 0/1 | detected |
| 11.10 | Required | yes | 0/1 | 1/1 | detected |
| 12.1 | Advisory | no | 1/1 | 0/1 | detected |
| 12.2 | Required | no | 1/1 | 0/1 | detected |
| 12.3 | Advisory | no | 0/1 (+1) | 0/1 | missed |
| 12.4 | Advisory | no | 1/1 | 0/1 | detected |
| 12.5 | Mandatory | no | 1/1 | 0/1 | detected |
| 12.6 | Required | yes | 0/1 | 0/1 | missed |
| 13.1 | Required | no | 1/1 | 0/1 | detected |
| 13.2 | Required | no | 1/1 | 0/1 | detected |
| 13.3 | Advisory | no | 1/1 (+1) | 0/1 | detected |
| 13.4 | Advisory | no | 1/1 | 0/1 | detected |
| 13.5 | Required | no | 1/1 | 0/1 | detected |
| 13.6 | Required | yes | 1/1 | 0/1 | detected |
| 14.1 | Required | no | 1/1 | 0/1 | detected |
| 14.2 | Required | no | 1/1 | 0/1 | detected |
| 14.3 | Required | no | 0/1 (+1) | 0/1 | missed |
| 14.4 | Required | no | 1/1 (+1) | 0/1 | detected |
| 15.1 | Advisory | no | 1/1 (+2) | 0/1 | detected |
| 15.2 | Required | no | 1/1 | 0/1 | detected |
| 15.3 | Required | no | 1/1 | 0/1 | detected |
| 15.4 | Advisory | no | 1/1 | 0/1 | detected |
| 15.5 | Advisory | no | 1/1 (+1) | 0/1 | detected |
| 15.6 | Required | no | 1/1 | 0/1 | detected |
| 15.7 | Required | no | 1/1 | 0/1 | detected |
| 16.1 | Required | no | 1/1 | 0/1 | detected |
| 16.2 | Required | no | 1/1 | 0/1 | detected |
| 16.3 | Required | no | 1/1 (+7) | 0/1 | detected |
| 16.4 | Required | no | 1/1 | 0/1 | detected |
| 16.5 | Required | no | 1/1 | 0/1 | detected |
| 16.6 | Required | no | 1/1 | 0/1 | detected |
| 16.7 | Required | no | 1/1 | 0/1 | detected |
| 17.1 | Required | no | 0/1 | 1/1 | detected |
| 17.2 | Required | no | 2/2 | 0/2 | detected |
| 17.3 | Mandatory | no | 1/1 | 0/1 | detected |
| 17.4 | Mandatory | no | 1/1 | 0/1 | detected |
| 17.5 | Required | yes | 1/1 | 0/1 | detected |
| 17.6 | Mandatory | no | 1/1 | 0/1 | detected |
| 17.7 | Required | no | 1/1 (+3) | 0/1 | detected |
| 17.8 | Advisory | no | 1/1 (+17) | 0/1 | detected |
| 17.9 | Mandatory | yes | 0/1 | 0/1 | missed |
| 17.10 | Required | yes | 0/1 | 1/1 | detected |
| 17.11 | Advisory | yes | 0/1 | 0/1 | missed |
| 17.12 | Advisory | yes | 0/1 | 0/1 | missed |
| 17.13 | Required | yes | 0/1 | 0/1 | missed |
| 18.1 | Required | no | 1/1 | 0/1 | detected |
| 18.2 | Required | no | 0/1 | 0/1 | missed |
| 18.3 | Required | no | 1/1 | 0/1 | detected |
| 18.4 | Advisory | no | 1/1 | 0/1 | detected |
| 18.5 | Advisory | no | 1/1 | 0/1 | detected |
| 18.6 | Required | no | 1/1 | 0/1 | detected |
| 18.7 | Required | no | 1/1 | 0/1 | detected |
| 18.8 | Required | no | 1/1 | 0/1 | detected |
| 18.9 | Required | yes | 0/1 | 0/1 | missed |
| 18.10 | Mandatory | yes | 0/1 | 1/1 | detected |
| 19.1 | Mandatory | no | 1/1 | 0/1 | detected |
| 19.2 | Advisory | no | 1/1 (+1) | 0/1 | detected |
| 20.1 | Advisory | no | 1/1 | 0/1 | detected |
| 20.2 | Required | no | 1/1 | 0/1 | detected |
| 20.3 | Required | no | 1/1 | 0/1 | detected |
| 20.4 | Required | no | 1/1 | 0/1 | detected |
| 20.5 | Advisory | no | 1/1 (+1) | 0/1 | detected |
| 20.6 | Required | no | 1/1 | 0/1 | detected |
| 20.7 | Required | no | 1/1 | 0/1 | detected |
| 20.8 | Required | no | 1/1 | 0/1 | detected |
| 20.9 | Required | no | 1/1 | 0/1 | detected |
| 20.10 | Advisory | no | 1/1 (+2) | 0/1 | detected |
| 20.11 | Required | no | 1/1 | 0/1 | detected |
| 20.12 | Required | no | 0/1 | 0/1 | missed |
| 20.13 | Required | no | 1/1 | 0/1 | detected |
| 20.14 | Required | no | 1/1 | 0/1 | detected |
| 21.1 | Required | no | 1/1 | 0/1 | detected |
| 21.2 | Required | no | 0/1 | 0/1 | missed |
| 21.3 | Required | no | 1/1 (+2) | 0/1 | detected |
| 21.4 | Required | no | 1/1 | 0/1 | detected |
| 21.5 | Required | no | 1/1 | 0/1 | detected |
| 21.6 | Required | no | 1/1 (+8) | 0/1 | detected |
| 21.7 | Required | no | 1/1 | 0/1 | detected |
| 21.8 | Required | no | 1/1 (+2) | 0/1 | detected |
| 21.9 | Required | no | 1/1 | 0/1 | detected |
| 21.10 | Required | no | 1/1 | 0/1 | detected |
| 21.11 | Advisory | yes | 1/1 | 0/1 | detected |
| 21.12 | Required | yes | 0/1 | 1/1 | detected |
| 21.13 | Mandatory | no | 1/1 | 0/1 | detected |
| 21.14 | Required | no | 0/1 | 0/1 | missed |
| 21.15 | Required | no | 1/1 | 0/1 | detected |
| 21.16 | Required | no | 1/1 (+1) | 0/1 | detected |
| 21.17 | Mandatory | no | 0/1 | 0/1 | missed |
| 21.18 | Mandatory | no | 1/1 | 0/1 | detected |
| 21.19 | Mandatory | no | 1/1 | 0/1 | detected |
| 21.20 | Mandatory | no | 1/1 | 0/1 | detected |
| 21.21 | Required | yes | 1/1 | 0/1 | detected |
| 21.22 | Mandatory | yes | 0/1 | 0/1 | missed |
| 21.23 | Required | yes | 0/1 | 0/1 | missed |
| 21.24 | Required | yes | 0/1 | 1/1 | detected |
| 21.25 | Required | yes | 0/1 | 1/1 | detected |
| 21.26 | Required | yes | 0/1 | 0/1 | missed |
| 22.1 | Required | no | 0/1 (+1) | 0/1 | missed |
| 22.2 | Mandatory | no | 1/1 | 0/1 | detected |
| 22.3 | Required | no | 0/1 | 0/1 | missed |
| 22.4 | Mandatory | no | 1/1 | 0/1 | detected |
| 22.5 | Mandatory | no | 1/1 | 0/1 | detected |
| 22.6 | Mandatory | no | 1/1 | 0/1 | detected |
| 22.7 | Required | no | 1/1 | 0/1 | detected |
| 22.8 | Required | no | 1/1 | 0/1 | detected |
| 22.9 | Required | no | 1/1 (+1) | 0/1 | detected |
| 22.10 | Required | no | 1/1 | 0/1 | detected |
| 22.11 | Required | yes | 0/1 | 1/1 | detected |
| 22.12 | Mandatory | yes | 0/1 | 0/1 | missed |
| 22.13 | Required | yes | 0/1 | 0/1 | missed |
| 22.14 | Mandatory | yes | 0/1 | 0/1 | missed |
| 22.15 | Required | yes | 0/1 | 0/1 | missed |
| 22.16 | Required | yes | 0/1 | 0/1 | missed |
| 22.17 | Required | yes | 0/1 | 0/1 | missed |
| 22.18 | Required | yes | 0/1 | 1/1 | detected |
| 22.19 | Required | yes | 0/1 | 0/1 | missed |
| 22.20 | Mandatory | yes | 0/1 | 0/1 | missed |
| 23.1 | Advisory | yes | 0/1 | 1/1 (+4) | detected |
| 23.2 | Required | yes | 0/1 | 1/1 | detected |
| 23.3 | Advisory | yes | 0/1 | 1/1 | detected |
| 23.4 | Required | yes | 0/1 | 0/1 | missed |
| 23.5 | Advisory | yes | 0/1 | 0/1 | missed |
| 23.6 | Required | yes | 0/1 | 0/1 | missed |
| 23.7 | Advisory | yes | 0/1 | 0/1 | missed |
| 23.8 | Required | yes | 0/1 | 1/1 | detected |
