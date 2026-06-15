import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

REQUIRED_FONTS = [
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
]


def check_fonts() -> None:
    """
    Verify required fonts exist. Called lazily at first image generation,
    not on every launch. Exits with a clear message if fonts are missing.
    """
    missing = [f for f in REQUIRED_FONTS if not (FONTS_DIR / f).exists()]
    if missing:
        print(f"\n[error] Missing font files in {FONTS_DIR}:")
        for f in missing:
            print(f"  - {f}")
        print("\nRe-run the Transcrire installer to restore missing assets.")
        sys.exit(1)
