"""Runnable entry point for ``python -m vibecodekit_mql5.rri``.

Delegates to ``main()`` defined in the package ``__init__`` (the Step 2
template opener).
"""

from __future__ import annotations

import sys

from . import main


if __name__ == "__main__":
    sys.exit(main())
