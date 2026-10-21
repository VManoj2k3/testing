"""Score the bundled KooSys CC engines against the MISRA fixtures (tests/misra) and the KooSys guideline
fixtures (tests/koosys), using exactly the binaries that ship in the .vsix (vscode/engines/).

Each fixture line ending in `// EXPECT <rule>` must be flagged with that rule (within TOL lines).
Findings for a rule on unmarked lines are counted as "other" (fixtures break other rules incidentally,
so they need a human look before being called false alarms). `NOEXPECT <rule>` lines are fixed false
alarms: any finding there fails the run. Files in tests/koosys/clean must produce no KooSys findings.

Usage: python score.py [--engines vscode/engines] [--md OUT] [--json OUT] [--min-detected N]
                       [--min-ksys N] [--ksys-md OUT]
"""
import argparse, csv, json, os, re, subprocess, sys, tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIX = HERE / "misra"
KFIX = HERE / "koosys"
RULES_CSV = ROOT / "rules" / "misra_rules.csv"
KSYS_CSV = ROOT / "rules" / "koosys_rules.csv"
RULES_YAML = ROOT / "vscode" / "bundled" / "rules.yaml"  # produced by `npm run bundle-rules`
TEXTCHECKS = ["node", str(ROOT / "vscode" / "out" / "cli.js")]  # produced by `npm run compile`
EXPECT = re.compile(r"EXPECT ([0-9]+\.[0-9]+)")
KSYS_EXPECT = re.compile(r"(?<!NO)EXPECT (KSYS-[A-Z]+-[0-9]+)")
KSYS_NOEXPECT = re.compile(r"NOEXPECT (KSYS-[A-Z]+-[0-9]+)")
GROUPS = [["ctu_a.c", "ctu_b.c"]]  # analysed together (cross-file rules)
TOL = 2  # engines sometimes report the opening line of a construct instead of the marked one


class Engines:
    def __init__(self, root):
        root = Path(root)
        exe = ".exe" if os.name == "nt" else ""
        self.misra = root / "misra" / f"koosyscc-misra{exe}"
        self.addon = root / "misra" / "addons" / "misra.py"
        self.python = root / "python" / ("python.exe" if os.name == "nt" else "bin/python3.12")
        self.rules = root / "rules" / f"koosyscc-rules{exe}"
        for p in (self.misra, self.addon, self.python, self.rules):
            if not p.exists():
                sys.exit(f"missing bundled engine {p}: run vscode/scripts/fetch-engines.py first")


def expectations():
    exp = defaultdict(set)  # rule -> {(file, line)}
    for f in fixture_files(FIX):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            for rule in EXPECT.findall(line):
                exp[rule].add((f.name, n))
    return exp


def units():
    grouped = {name for g in GROUPS for name in g}
    singles = [[f.name] for f in sorted(FIX.glob("*.c")) if f.name not in grouped]
    return singles + GROUPS


def fixture_files(folder):
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in (".c", ".h"))


def run_misra(eng):
    found = set()
    build = tempfile.mkdtemp(prefix="koosyscc-build-")  # keeps add-on dump files out of the fixtures
    for unit in units():
        cmd = [str(eng.misra), f"--addon={eng.addon}", f"--addon-python={eng.python}", "--std=c11",
               f"--cppcheck-build-dir={build}",
               "--enable=style,warning,portability", "--report-type=misra-c-2023",
               "--template={file}:{line}:{id}", "-q", "-I", str(FIX), *[str(FIX / u) for u in unit]]
        out = subprocess.run(cmd, capture_output=True, text=True).stderr
        for line in out.splitlines():
            m = re.match(r"(.+?):(\d+):(\d+\.\d+)$", line.strip())
            if m:
                found.add((m.group(3), Path(m.group(1)).name, int(m.group(2))))
    return found


def run_rules(eng, files, key):
    """Rule engine, one file per call (as the extension runs it); key = metadata field to collect."""
    found = set()
    for f in files:
        out = subprocess.run([str(eng.rules), "-rules", str(RULES_YAML), "-lang", "c", "-json", str(f)],
                             capture_output=True, text=True).stdout
        data = json.loads(out[out.find("{"):] or "{}")
        for r in data.get("results", []):
            rule = (r.get("extra", {}).get("metadata") or {}).get(key)
            if rule:
                found.add((str(rule), Path(r["path"]).name, r["start"]["line"]))
    return found


def run_koosys(eng, files):
    found = run_rules(eng, files, "koosys")
    out = subprocess.run([*TEXTCHECKS, *map(str, files)], capture_output=True, text=True).stdout
    for f in json.loads(out or "[]"):
        found.add((f["rule"], Path(f["file"]).name, f["line"]))
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


def score_koosys(eng, md):
    fixtures = fixture_files(KFIX)
    exp, noexp = defaultdict(set), set()
    for f in fixtures:
        for n, line in enumerate(f.read_text().splitlines(), 1):
            for rule in KSYS_EXPECT.findall(line):
                exp[rule].add((f.name, n))
            for rule in KSYS_NOEXPECT.findall(line):
                noexp.add((rule, f.name, n))
    found = run_koosys(eng, fixtures)
    res = score(found, exp)
    regressions = sorted(noexp & found)
    clean = sorted(run_koosys(eng, fixture_files(KFIX / "clean")))
    rows = [r for r in csv.DictReader(open(KSYS_CSV)) if r["engine"] in ("rules", "text")]
    detected = 0
    lines = ["| Rule | Source | Level | Engine | Fixture | Status |", "|---|---|---|---|---|---|"]
    for r in rows:
        s_ = res.get(r["id"])
        cell = "no fixture" if s_ is None else f"{s_['detected']}/{s_['expected']}" + (f" (+{s_['other']})" if s_["other"] else "")
        detected += s_ is not None and s_["detected"] == s_["expected"]
        lines.append(f"| {r['id']} | {r['source']} | {r['level']} | {r['engine']} | {cell} | {r['status']} |")
    if md:
        Path(md).write_text("\n".join(lines) + "\n")
    print(f"koosys: {detected}/{len(rows)} tool-checked rules detected on fixtures; "
          f"{len(clean)} finding(s) on compliant code {clean[:5]}; "
          f"{len(regressions)}/{len(noexp)} known false alarms back {regressions}", file=sys.stderr)
    return detected, clean + regressions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default=str(ROOT / "vscode" / "engines"))
    ap.add_argument("--json")
    ap.add_argument("--md")
    ap.add_argument("--min-detected", type=int, default=0, help="exit 1 if fewer MISRA rules are detected")
    ap.add_argument("--min-ksys", type=int, default=0, help="exit 1 if fewer KooSys rules are detected")
    ap.add_argument("--ksys-md")
    a = ap.parse_args()
    eng = Engines(a.engines)
    exp = expectations()
    engines = {"misra": score(run_misra(eng), exp),
               "rules": score(run_rules(eng, fixture_files(FIX), "misra"), exp)}
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
        lines = ["| Rule | Category | Latest amendment | MISRA engine | Rule engine | Status |", "|---|---|---|---|---|---|"]
        for t in table:
            lines.append(f"| {t['rule']} | {t['category']} | {t['latest_amendment']} | {t['misra']} | {t['rules']} | {t['status']} |")
        Path(a.md).write_text("\n".join(lines) + "\n")
    print(dict(totals), file=sys.stderr)
    detected, bad = score_koosys(eng, a.ksys_md)
    if totals["detected"] < a.min_detected:
        sys.exit(f"MISRA coverage regression: {totals['detected']} rules detected, expected at least {a.min_detected}")
    if detected < a.min_ksys:
        sys.exit(f"KooSys coverage regression: {detected} rules detected, expected at least {a.min_ksys}")
    if bad:
        sys.exit(f"KooSys findings on compliant code or NOEXPECT lines: {bad}")


if __name__ == "__main__":
    main()
