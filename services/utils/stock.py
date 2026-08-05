"""Stock scanning utilities."""

from pathlib import Path
from typing import Dict, List

from services.utils.paths import drive_root, VIDEO_EXTS, NON_PRODUCT_DIRS


def scan_stock(root: Path | None = None) -> Dict[str, int]:
    """{product_folder: count of raw video files}. One definition, everywhere."""
    root = Path(root) if root else drive_root()
    stock: Dict[str, int] = {}
    if not root.exists():
        return stock
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in NON_PRODUCT_DIRS:
            continue
        try:
            stock[entry.name] = sum(
                1 for f in entry.iterdir()
                if f.is_file() and f.suffix.lower() in VIDEO_EXTS
            )
        except OSError:
            continue
    return stock


def get_stock_counts() -> Dict[str, int]:
    """Get current stock levels."""
    return scan_stock()


def check_low_stock(threshold: int = 5) -> List[str]:
    """Get list of products with low stock."""
    stock_counts = scan_stock()
    return [p for p, count in stock_counts.items() if count < threshold]