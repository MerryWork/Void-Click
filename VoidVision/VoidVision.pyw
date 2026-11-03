"""Double-click launcher: runs Void Vision from this folder without installing.

Windows opens .pyw files with pythonw.exe, so no console window appears.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from voidvision.run import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
