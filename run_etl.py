"""
run_etl.py
──────────
Script untuk menjalankan ETL secara manual dari command line.
Berguna untuk testing awal dan backfill data.

Cara pakai:
  python run_etl.py --mode all       # full ETL
  python run_etl.py --mode extract   # extract saja
  python run_etl.py --mode transform # transform saja
"""

import argparse
import sys
from utils.logger import get_logger

logger = get_logger("run_etl_manual")


def main():
    parser = argparse.ArgumentParser(description="Jalankan ETL secara manual")
    parser.add_argument(
        "--mode",
        choices=["all", "extract", "transform"],
        default="all",
        help="Mode ETL yang dijalankan (default: all)",
    )
    args = parser.parse_args()

    logger.info(f"Menjalankan ETL mode: {args.mode}")

    try:
        if args.mode in ("all", "extract"):
            from etl.extractor import run_extract
            result = run_extract()
            logger.info(f"Extract selesai: {result}")

        if args.mode in ("all", "transform"):
            from etl.transformer import run_transform
            result = run_transform()
            logger.info(f"Transform selesai: {result}")

        logger.info("✅ ETL selesai sukses!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ ETL gagal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
