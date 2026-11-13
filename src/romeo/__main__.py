"""Allow `python -m romeo …` (used by the Windows autostart entry)."""

from romeo.cli import main

raise SystemExit(main())
