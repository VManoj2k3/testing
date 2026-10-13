"""Seeded-bug test for the "Code Bug Finder" agent.

Each case has one known bug (or none) and keywords; a case counts as found when any keyword appears in the
answer. Keyword matching can be fooled, so answers are printed for a manual check as well.

Usage: LF_URL=... LF_PASSWORD=... LF_TPL_DIR=... python bugfinder_cases.py <flow_id>
"""
import sys, time
import lf_drive as d

CASES = [
    ("off-by-one", "python", """def last_n(items, n):
    out = []
    for i in range(len(items) - n, len(items) + 1):
        out.append(items[i])
    return out""", ["off-by-one", "indexerror", "out of range", "len(items) + 1", "+ 1"]),
    ("none-deref", "python", """def user_email(db, user_id):
    user = db.get(user_id)   # returns None when not found
    return user.email.lower()""", ["none", "null", "attributeerror", "not found"]),
    ("sql-injection", "python", """def find_user(cur, name):
    cur.execute("SELECT * FROM users WHERE name = '" + name + "'")
    return cur.fetchone()""", ["injection", "parameter", "placeholder"]),
    ("file-leak", "python", """def count_lines(path):
    f = open(path)
    return len(f.readlines())""", ["close", "leak", "with open", "context manager"]),
    ("mutable-default", "python", """def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags""", ["mutable default", "shared", "default argument", "tags=none", "tags = none"]),
    ("missing-await", "javascript", """async function loadUser(id) {
  const res = fetch(`/api/users/${id}`);
  return res.json();
}""", ["await", "promise"]),
    ("buffer-overflow", "c", """void greet(const char *name) {
    char buf[16];
    strcpy(buf, "Hello, ");
    strcat(buf, name);
    puts(buf);
}""", ["overflow", "strncat", "snprintf", "bounds"]),
    ("int-division", "python", """def average(values):
    total = 0
    for v in values:
        total += v
    return total / len(values)""", ["zero", "empty", "zerodivision"]),
    ("clean-1", "python", """def safe_div(a, b):
    if b == 0:
        raise ValueError("b must not be zero")
    return a / b""", None),
    ("clean-2", "python", """def read_config(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()""", None),
]


def main(flow_id):
    tok = d.login()
    found = fp = 0
    rows = []
    for name, lang, code, keys in CASES:
        t = time.time()
        text = d.run_stream(tok, flow_id, f"Find the bugs in this {lang} code:\n```{lang}\n{code}\n```") or ""
        secs = time.time() - t
        low = text.lower()
        clean_ok = "no bugs found" in low
        if keys is None:
            ok = clean_ok
            fp += not ok
        else:
            ok = any(k in low for k in keys) and not clean_ok
            found += ok
        rows.append((name, "PASS" if ok else "FAIL", round(secs)))
        print("-" * 60)
    print("\nRESULTS")
    for r in rows:
        print(f"  {r[0]:<16} {r[1]}  {r[2]}s")
    seeded = sum(1 for c in CASES if c[3] is not None)
    print(f"bugs found {found}/{seeded}; false alarms on clean code {fp}/{len(CASES) - seeded}")


if __name__ == "__main__":
    main(sys.argv[1])
