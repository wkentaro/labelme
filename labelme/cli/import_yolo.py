#!/usr/bin/env python3
"""Import YOLO format annotations to LabelMe JSON."""

import argparse
import os
import sys
from pathlib import Path

from loguru import logger


def main():
    """Main entry point for YOLO import."""
    parser = argparse.ArgumentParser(
        description="Import YOLO format annotations to LabelMe JSON"
    )
    parser.add_argument(
        "yolo_dir",
        help="Directory containing YOLO dataset"
    )
    parser.add_argument(
        "-o", "--output",
        default="labelme_dataset",
        help="Output directory for LabelMe JSON files (default: labelme_dataset)"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Don't skip files that already exist"
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not Path(args.yolo_dir).exists():
        logger.error(f"Input directory does not exist: {args.yolo_dir}")
        return 1
    
    # Check for yolo2labelme availability
    try:
        from yolo2labelme import yolo2labelme
    except ImportError:
        logger.error("yolo2labelme not available. Install with: pip install yolo2labelme")
        return 1
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    logger.info(f"Importing YOLO dataset from: {args.yolo_dir}")
    logger.info(f"Output directory: {Path(args.output).absolute()}")
    
    try:
        # Call yolo2labelme function
        yolo2labelme(
            data=str(args.yolo_dir),
            out=str(args.output),
            skip=not args.no_skip
        )
        
        logger.info("Import completed successfully")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Import cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Import error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())