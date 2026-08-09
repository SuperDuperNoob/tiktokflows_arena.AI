"""AI Growth CLI - thin wrapper for services.infrastructure.ai_adapter.AIAdapter"""

import argparse
import logging
import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

from services.infrastructure.ai_adapter import AIAdapter

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Growth engine. Free unless --ai.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Analyse only, write nothing (never calls AI)")
    ap.add_argument("--ai", action="store_true",
                    help="Allow ONE paid AI call per day (used by /growth)")
    ap.add_argument("--no-ai", action="store_true",
                    help="Explicitly disable AI (default)")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    adapter = AIAdapter()
    dry_run = args.dry_run
    force_ai = args.ai and not args.no_ai and not dry_run

    if args.ai and dry_run:
        print("[growth] --dry-run ignores --ai (nothing is persisted, so the "
              "call could not be cached)")

    result = adapter.generate_growth_report(days=args.days,
                                            dry_run=dry_run,
                                            force_ai=force_ai)

    if not dry_run:
        print(f"[growth] Report generated: cached={result.get('_cached', False)}, "
              f"fallback={result.get('_fallback', False)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())