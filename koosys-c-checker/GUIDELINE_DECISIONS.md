# Where the KooSys documents contradict each other, and what the checker enforces

Sources:
- `KooSys_CodingGuidelines` v2.1 (2024-09-23);
- the Quantum Leaps "C/C++ Coding Standard" Rev. J (QL), which KooSys §4 says to follow;
- AUTOSAR "Specification of Standard Types" (CP R21-11).

KooSys §4.3 merges its own naming rules with QL's §5.2, so it contradicts itself. The decisions below
were taken on 2026-10-21 so the checker can enforce one consistent set. **They should be confirmed by
the document owner (Freigabe: A. Koos) and written back into the guideline**, otherwise developers
will be checked against rules the document doesn't clearly state.

| Topic | Side A | Side B | Enforced |
|---|---|---|---|
| Integer types | AUTOSAR SRS_BSW_00304: use AUTOSAR types (`uint8`, `sint16`, `boolean`) instead of native C types | QL §4: use `<stdint.h>` (`uint8_t`); "inventing different aliases is forbidden" | **Either is accepted.** Only raw C types (`int`, `long`, `unsigned char`…) are flagged (KSYS-TYPE-01). |
| Comment style | KooSys §4.2: "Use single line comments" | QL §3.3: "never use C++ comments (//) in C" | **KooSys:** `//` only. `/** */` doxygen blocks are allowed (KSYS-CMT-01, Info). |
| Variable names | KooSys §4.3 bullet 1: lowercase with underscores (`my_variable`) | KooSys §4.3 (copied from QL): multi-word identifiers in camelCase (`fooBarTar`, not `foo_bar_tar`) | **First KooSys bullets:** `my_variable` (KSYS-NAME-01). |
| Function names | KooSys §4.3: `Module_Function` (uppercase words, underscores) | KooSys §4.3 (from QL): "ordinary C functions start with a lower-case letter" | **`Module_Function`** (KSYS-NAME-02). |
| Typedef names | KooSys §4.3: lowercase + postfix, `my_new_type_t` | KooSys §4.3 (from QL): type names start upper-case, `struct Foo` | **`lower_snake_t`** (KSYS-NAME-05). |
| Constants | KooSys §4.3: `MAX_SPEED` (upper case) | KooSys §4.3: "Constants … should be in camelcase" (QL itself says upper case) | **UPPER_CASE** (KSYS-NAME-04). |
| DOS 8.3 file names | KooSys §4.8 / QL §2: limit to 8.3 | KooSys §4.1's own example `module_name.c` is 11 characters | **Off by default** (KSYS-FILE-02, setting `koosys.checkDosFileNames`). |

## Correction to the original extension idea
The pitch named `l_`, `g_` and `p_` prefixes. None of the documents has `g_` or `p_`:
- globals take the **module prefix** (`module_name_variable`);
- `l_` is for **module-local variables declared `static` at file scope** (QL §3.4.5), not for function locals.

The checker follows the documents: KSYS-NAME-03 and KSYS-NAME-07.

## Rules that are guidance, not checkable
15 items can't be checked by any tool here. Examples are "comments in English", "comments describe
intention", "handle errors gracefully", and the ISO 26262 process items in §4.9.2. They are listed in
`rules/koosys_rules.csv` with status `not-checkable` and counted in the status bar. They still need
code review.
