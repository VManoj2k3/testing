"""Assemble the bundled engines for one platform into vscode/engines/ (packaged into the .vsix).

  engines/rules/koosyscc-rules[.exe] (+ its libs)    pattern rule engine (Semgrep CE core, LGPL-2.1)
  engines/misra/koosyscc-misra[.exe], cfg/, addons/  MISRA engine (cppcheck + MISRA addon, GPL-3.0)
  engines/python/                                    Python runtime for the MISRA addon (PSF licence)
  engines/licenses/                                  upstream licence texts (required by the licences)

Usage: python fetch-engines.py --target linux-x64|win32-x64|darwin-arm64 --misra-build <cppcheck build dir>
       --misra-src <cppcheck source dir>
Versions are pinned below; the third-party notice in THIRD_PARTY_NOTICES.md must match them.
"""
import argparse, io, json, shutil, stat, subprocess, tarfile, zipfile
from pathlib import Path

RULE_ENGINE_VERSION = "1.182.0"
PYTHON_RELEASE, PYTHON_VERSION = "20261013", "3.12.15"
TARGETS = {
    "linux-x64": {"wheel": "manylinux_2_34_x86_64", "python": "x86_64-unknown-linux-gnu", "exe": ""},
    "win32-x64": {"wheel": "win_amd64", "python": "x86_64-pc-windows-msvc", "exe": ".exe"},
    "darwin-arm64": {"wheel": "macosx_11_0_arm64", "python": "aarch64-apple-darwin", "exe": ""},
}
OUT = Path(__file__).resolve().parent.parent / "engines"


def fetch(url):
    # curl is on every CI runner (Windows included) and honours proxy settings reliably
    print("download", url, flush=True)
    return subprocess.run(["curl", "-fsSL", "--retry", "3", url], check=True, capture_output=True).stdout


def make_executable(p):
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def rule_engine(t):
    meta = json.loads(fetch(f"https://pypi.org/pypi/semgrep/{RULE_ENGINE_VERSION}/json"))
    url = next(u["url"] for u in meta["urls"] if u["filename"].endswith(f"-{t['wheel']}.whl"))
    dest = OUT / "rules"
    with zipfile.ZipFile(io.BytesIO(fetch(url))) as z:
        for name in z.namelist():
            # binaries live under <pkg>.data/purelib/semgrep/bin/ (engine + its shared libraries)
            i = name.find("semgrep/bin/")
            if i >= 0 and not name.endswith(("/", ".py")):
                rel = Path(name[i + len("semgrep/bin/"):])
                if rel.name in ("semgrep-core", "semgrep-core.exe"):
                    rel = rel.with_name("koosyscc-rules" + t["exe"])
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                make_executable(target)
    # the wheel carries no licence file; take it from the upstream source at the same version
    (OUT / "licenses").mkdir(parents=True, exist_ok=True)
    (OUT / "licenses" / "rule-engine-LGPL-2.1.txt").write_bytes(
        fetch(f"https://raw.githubusercontent.com/semgrep/semgrep/v{RULE_ENGINE_VERSION}/LICENSE"))
    assert (dest / ("koosyscc-rules" + t["exe"])).exists(), "rule engine binary missing from the wheel"


def misra_engine(t, build, src):
    dest = OUT / "misra"
    exe = next(p for p in Path(build).rglob("cppcheck" + t["exe"]) if p.is_file() and p.parent.name in ("bin", "Release"))
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, dest / ("koosyscc-misra" + t["exe"]))
    make_executable(dest / ("koosyscc-misra" + t["exe"]))
    shutil.copytree(Path(src) / "cfg", dest / "cfg", dirs_exist_ok=True)
    (dest / "addons").mkdir(exist_ok=True)
    for f in (Path(src) / "addons").glob("*.py"):
        if f.name.startswith(("misra", "cppcheckdata")):
            shutil.copy2(f, dest / "addons" / f.name)
    (OUT / "licenses").mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(src) / "COPYING", OUT / "licenses" / "misra-engine-GPL-3.0.txt")


def python_runtime(t):
    name = f"cpython-{PYTHON_VERSION}+{PYTHON_RELEASE}-{t['python']}-install_only_stripped.tar.gz"
    data = fetch(f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_RELEASE}/{name}")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(OUT, filter="tar") if hasattr(tarfile, "data_filter") else tar.extractall(OUT)
    (OUT / "python").exists() or (_ for _ in ()).throw(RuntimeError("python/ missing from runtime archive"))
    lic = OUT / "python" / ("LICENSE.txt" if t["exe"] else "lib/python3.12/LICENSE.txt")
    if lic.exists():
        shutil.copy2(lic, OUT / "licenses" / "python-PSF.txt")
    prune_python(OUT / "python", linux=t["python"].endswith("linux-gnu"))


# Parts of the runtime the MISRA addon never uses (GUI, tests, tooling, headers): ~30 MB smaller package.
PRUNE_DIRS = {"test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data",
              "include", "share", "site-packages", "tcl", "tcl8", "tcl9", "tk8", "tk9", "Tools"}
PRUNE_FILES = ("libtcl", "libtk", "libtcl9tk", "tcl9", "tk9", "tcl8", "tk8", "idle", "pip", "2to3", "pydoc")


def prune_python(root, linux):
    for p in sorted(root.rglob("*"), key=lambda x: -len(x.parts)):
        if p.is_symlink():  # .vsix installs do not reliably keep symlinks; the extension calls python3.12 directly
            p.unlink()
            continue
        if not p.exists():
            continue
        if linux and p.is_file() and p.name.startswith("libpython"):
            p.unlink()  # the Linux interpreter is statically linked; this is a second 33 MB copy
            continue
        if p.is_dir() and p.name in ("pkgconfig",) or p.is_dir() and p.name.startswith(("itcl", "thread")) and p.parent.name == "lib":
            shutil.rmtree(p)
            continue
        if p.is_dir() and (p.name in PRUNE_DIRS or p.name.startswith(("tcl", "tk"))) and p != root:
            shutil.rmtree(p)
        elif p.is_file() and p.name.lower().startswith(PRUNE_FILES):
            p.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=TARGETS)
    ap.add_argument("--misra-build", required=True)
    ap.add_argument("--misra-src", required=True)
    a = ap.parse_args()
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    t = TARGETS[a.target]
    rule_engine(t)
    misra_engine(t, a.misra_build, a.misra_src)
    python_runtime(t)
    (OUT / "target.json").write_text(json.dumps({"target": a.target, "ruleEngine": RULE_ENGINE_VERSION,
                                                 "python": PYTHON_VERSION}))
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"engines for {a.target}: {size:.0f} MB in {OUT}")


if __name__ == "__main__":
    main()
