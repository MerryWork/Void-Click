"""Run every test suite in this repository, Void Click first, then Void Vision.

    python run_tests.py                 # both
    python run_tests.py voidclick       # just one
    python run_tests.py voidvision

On Windows, use `py run_tests.py`. Exits 0 only when every suite passes, so
it can gate a commit or a CI job.

Void Click's source currently lives only inside its release zip
(Voidclick*.zip), so the script unpacks the newest zip into a temporary folder
and runs the tests from there. If an unpacked Voidclick/ folder is ever added
to the repo, that is used instead.

Neither suite moves the real mouse or presses real keys. pynput still has to
load, which on Linux needs an X display: without one, the script reruns the
suite under xvfb-run when that is installed.
"""

import argparse
import glob
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
NEEDS = {
    "voidclick": ["pynput"],
    "voidvision": ["pynput", "PIL", "numpy"],
}
PIP_NAMES = {"PIL": "pillow"}


def banner(text):
    print("\n" + "=" * 64 + f"\n  {text}\n" + "=" * 64, flush=True)


def missing_modules(names):
    return [n for n in names if importlib.util.find_spec(n) is None]


def needs_virtual_display():
    return sys.platform.startswith("linux") and not os.environ.get("DISPLAY")


def run(cmd, cwd):
    """Run a test command, wrapping it in xvfb-run on headless Linux."""
    if needs_virtual_display():
        xvfb = shutil.which("xvfb-run")
        if xvfb is None:
            return None, "no X display and xvfb-run is not installed (apt install xvfb)"
        cmd = [xvfb, "-a"] + cmd
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)
    return proc, None


def extract_zip(path, dest):
    """Unpack a release zip. Its entries use Windows backslashes, which
    zipfile on macOS/Linux would otherwise turn into odd flat filenames."""
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            target = os.path.normpath(os.path.join(dest, name))
            if not target.startswith(os.path.abspath(dest)):
                continue  # refuse paths that escape the folder
            if name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def find_voidclick(tmp):
    for folder in ("Voidclick", "VoidClick"):
        if os.path.exists(os.path.join(ROOT, folder, "tests", "test_core.py")):
            return os.path.join(ROOT, folder), f"{folder}/"
    zips = sorted(glob.glob(os.path.join(ROOT, "Voidclick*.zip")),
                  key=lambda p: [int(x) for x in re.findall(r"\d+", os.path.basename(p))] or [0])
    if not zips:
        return None, None
    extract_zip(zips[-1], tmp)
    for dirpath, _dirs, files in os.walk(tmp):
        if "test_core.py" in files and os.path.basename(dirpath) == "tests":
            return os.path.dirname(dirpath), os.path.basename(zips[-1])
    return None, None


def suite_voidclick():
    tmp = tempfile.mkdtemp(prefix="voidclick-tests-")
    try:
        project, source = find_voidclick(tmp)
        if project is None:
            return "error", "no Voidclick*.zip or Voidclick/ folder found", ""
        print(f"  source: {source}", flush=True)
        proc, err = run([sys.executable, os.path.join("tests", "test_core.py")], project)
        if err:
            return "skipped", err, ""
        out = proc.stdout
        m = re.search(r"(\d+) passed, (\d+) failed", out)
        if m:
            passed, failed = int(m.group(1)), int(m.group(2))
            detail = f"{passed} passed, {failed} failed"
            ok = failed == 0 and proc.returncode == 0
        else:
            detail = f"exit code {proc.returncode}, no summary line"
            ok = False
        return ("passed" if ok else "failed"), detail, out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def suite_voidvision():
    project = os.path.join(ROOT, "VoidVision")
    if not os.path.isdir(project):
        return "error", "VoidVision/ folder not found", ""
    proc, err = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], project)
    if err:
        return "skipped", err, ""
    out = proc.stdout
    ran = re.search(r"Ran (\d+) tests?", out)
    total = int(ran.group(1)) if ran else 0
    bad = re.search(r"FAILED \((.*)\)", out)
    detail = f"{total} tests, " + (bad.group(1) if bad else "all OK")
    return ("passed" if proc.returncode == 0 else "failed"), detail, out


SUITES = {"voidclick": ("Void Click", suite_voidclick),
          "voidvision": ("Void Vision", suite_voidvision)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("suites", nargs="*", metavar="suite",
                    help="voidclick and/or voidvision (default: both, Void Click first)")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="only print each suite's output when it fails")
    args = ap.parse_args(argv)
    chosen = [s.lower().replace(" ", "").replace("_", "") for s in args.suites] or list(SUITES)
    unknown = [s for s in chosen if s not in SUITES]
    if unknown:
        ap.error(f"unknown suite {unknown[0]!r} - choose from {', '.join(SUITES)}")

    results = []
    for key in chosen:
        name, fn = SUITES[key]
        banner(name)
        missing = missing_modules(NEEDS[key])
        if missing:
            pkgs = " ".join(PIP_NAMES.get(m, m) for m in missing)
            results.append((name, "skipped", f"missing {', '.join(missing)} - pip install {pkgs}", 0))
            print(f"  skipped: pip install {pkgs}")
            continue
        start = time.monotonic()
        status, detail, output = fn()
        elapsed = time.monotonic() - start
        if output and (not args.quiet or status != "passed"):
            print(output.rstrip())
        results.append((name, status, detail, elapsed))

    banner("Summary")
    marks = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "error": "ERR "}
    for name, status, detail, elapsed in results:
        timing = f"  ({elapsed:.1f}s)" if elapsed else ""
        print(f"  [{marks[status]}] {name:<12} {detail}{timing}")
    all_ok = all(status == "passed" for _, status, _, _ in results)
    print("\n  All suites passed." if all_ok else "\n  Not everything passed - see above.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
