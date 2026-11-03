# Testing Void Click and Void Vision

One command runs every test in this repository. It runs Void Click first, then Void Vision:

```
python run_tests.py
```

On Windows, use `py run_tests.py`. The script exits with code 0 only when every suite passes.

## Setup (once)

You need Python 3.8 or newer. Then install the packages:

```
pip install pynput pillow numpy
```

`pynput` is the only package Void Click needs. Void Vision also needs Pillow and NumPy. If a package is missing, the script skips that suite. It tells you exactly what to `pip install`.

## What it does

| Order | Suite       | Where the code is                 | Size        |
|-------|-------------|-----------------------------------|-------------|
| 1     | Void Click  | `Voidclick1.0.0.zip` (unpacked to a temp folder) | 196 checks |
| 2     | Void Vision | `VoidVision/tests/`               | 50 tests    |

Neither suite moves your real mouse or presses real keys. Input is replaced by stand-ins, so it's safe to run while you use the computer.

Void Click's source currently lives only inside its release zip. The script unpacks the newest `Voidclick*.zip` and runs `tests/test_core.py` from it. If an unpacked `Voidclick/` folder is added to the repo later, the script uses that folder instead.

## Options

```
python run_tests.py voidclick      # only Void Click
python run_tests.py voidvision     # only Void Vision
python run_tests.py -q             # quiet: only show output for a suite that fails
```

## Reading the result

The last lines are a summary:

```
  [PASS] Void Click   196 passed, 0 failed  (9.9s)
  [PASS] Void Vision  50 tests, all OK  (5.6s)

  All suites passed.
```

- `FAIL` means a test broke. The suite's full output is printed above the summary, with the failing check's name.
- `SKIP` means the suite couldn't run, for example because of a missing package. The reason is shown on the same line.
- Tracebacks that mention `boom` or `simulated input failure` are expected. Those tests deliberately make things crash to prove the app recovers. They count as passes.

## Linux and headless machines

pynput needs a display to load on Linux. Without `$DISPLAY`, the script reruns each suite under `xvfb-run` if it's installed (`apt install xvfb`). Windows and macOS need nothing extra.

## Asking another assistant to run them

Paste this:

> In the Void-Click repository, install the test dependencies with
> `pip install pynput pillow numpy`, then run `python run_tests.py` from the
> repository root. It runs the Void Click suite first and then the Void Vision
> suite. Report the summary block at the end. If anything shows FAIL, include
> that suite's failing check names and the output around them.

## Running a suite by hand

```
cd VoidVision
python tests/test_core.py
```

Void Click: unzip `Voidclick1.0.0.zip`, then run `py tests\test_core.py` inside the unzipped `Voidclick` folder.
