"""Score engines against the MISRA fixtures.

Each fixture line ending in `// EXPECT <rule>` must be flagged with that rule (within TOL lines).
Findings for a rule on lines not marked with that rule are counted as "other" (fixtures
violate other rules incidentally, so these need a human look before being called false alarms).

Usage: python score.py [--cppcheck PATH] [--semgrep PATH] [--rules DIR] [--json OUT] [--md OUT] [--min-detected N]
"""
import argparse, csv, json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "misra"
RULES_CSV = HERE.parent / "rules" / "misra_rules.csv"
EXPECT = re.compile(r"EXPECT ([0-9]+\.[0-9]+)")
GROUPS = [["ctu_a.c", "ctu_b.c"]]
TOL = 2  # tools sometimes report the opening line of a construct instead of the marked one  # analysed together (cross-file rules)


def expectations():
    exp = defaultdict(set)  # rule -> {(file, line)}
    for f in sorted(FIX.iterdir()):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            for rule in EXPECT.findall(line):
                exp[rule].add((f.name, n))
    return exp


def units():
    grouped = {name for g in GROUPS for name in g}
    singles = [[f.name] for f in sorted(FIX.glob("*.c")) if f.name not in grouped]
    return singles + GROUPS


def run_cppcheck(exe):
    found = set()
    for unit in units():
        cmd = [exe, "--std=c11", "--addon=misra", "--enable=style,warning,portability",
               "--report-type=misra-c-2012", "--template={file}:{line}:{id}", "-q", "-I", str(FIX),
               *[str(FIX / u) for u in unit]]
        out = subprocess.run(cmd, capture_output=True, text=True).stderr
        for line in out.splitlines():
            m = re.match(r"(.+?):(\d+):(\d+\.\d+)$", line.strip())
            if m:
                found.add((m.group(3), Path(m.group(1)).name, int(m.group(2))))
    return found


def run_semgrep(exe, rules_dir):
    out = subprocess.run([exe, "scan", "--json", "--metrics=off", "--disable-version-check", "--quiet",
                          "--config", str(rules_dir),
                          # explicit files: a directory target named tests/ is skipped by Semgrep's default ignore list
                          *[str(f) for f in sorted(FIX.iterdir())]], capture_output=True, text=True).stdout
    found = set()
    for r in json.loads(out or "{}").get("results", []):
        rule = (r.get("extra", {}).get("metadata") or {}).get("misra")
        if rule:
            found.add((str(rule), Path(r["path"]).name, r["start"]["line"]))
    return found


def score(found, exp):
    res = {}
    for rule, sites in exp.items():
        hits = {(f, l) for (r, f, l) in found if r == rule}
        near = lambda s, h: s[0] == h[0] and abs(s[1] - h[1]) <= TOL
        det = {s for s in sites if any(near(s, h) for h in hits)}
        other = {h for h in hits if not any(near(s, h) for s in sites)}
        res[rule] = {"detected": len(det), "expected": len(sites), "other": len(other)}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cppcheck")
    ap.add_argument("--semgrep")
    ap.add_argument("--rules", default=str(HERE.parent / "rules" / "semgrep"))
    ap.add_argument("--json")
    ap.add_argument("--md")
    ap.add_argument("--min-detected", type=int, default=0, help="exit 1 if fewer rules are detected (CI regression gate)")
    a = ap.parse_args()
    exp = expectations()
    engines = {}
    if a.cppcheck:
        engines["cppcheck"] = score(run_cppcheck(a.cppcheck), exp)
    if a.semgrep:
        engines["semgrep"] = score(run_semgrep(a.semgrep, a.rules), exp)
    rows = list(csv.DictReader(open(RULES_CSV)))
    table, totals = [], defaultdict(int)
    for row in rows:
        r = row["rule"]
        cells = {}
        for name, res in engines.items():
            s = res.get(r)
            cells[name] = "no fixture" if s is None else f"{s['detected']}/{s['expected']}" + (f" (+{s['other']})" if s["other"] else "")
        hit = any(res.get(r, {}).get("detected", 0) > 0 for res in engines.values())
        full = any(res.get(r, {}).get("detected", 0) == res.get(r, {}).get("expected", -1) for res in engines.values())
        status = "no fixture" if r not in exp else ("detected" if full else "partial" if hit else "missed")
        totals[status] += 1
        table.append({**row, **cells, "status": status})
    if a.json:
        Path(a.json).write_text(json.dumps(table, indent=1))
    if a.md:
        names = list(engines)
        lines = ["| Rule | Category | Latest amendment | " + " | ".join(names) + " | Status |",
                 "|---|---|---|" + "---|" * len(names) + "---|"]
        for t in table:
            lines.append(f"| {t['rule']} | {t['category']} | {t['latest_amendment']} | "
                         + " | ".join(t[n] for n in names) + f" | {t['status']} |")
        Path(a.md).write_text("\n".join(lines) + "\n")
    print(dict(totals), file=sys.stderr)
    if totals["detected"] < a.min_detected:
        sys.exit(f"coverage regression: {totals['detected']} rules detected, expected at least {a.min_detected}")


if __name__ == "__main__":
    main()
