#!/usr/bin/env python3
"""Export LabelMe annotations to YOLO format."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from loguru import logger


def main():
    """Main entry point for YOLO export."""
    parser = argparse.ArgumentParser(
        description="Export LabelMe JSON files to YOLO format"
    )
    parser.add_argument(
        "json_dir",
        help="Directory containing LabelMe JSON files"
    )
    parser.add_argument(
        "-o", "--output",
        default="yolo_dataset",
        help="Output directory for YOLO dataset (default: yolo_dataset)"
    )
    parser.add_argument(
        "--mode",
        choices=["detection", "segmentation"],
        default="detection",
        help="Export mode: detection (bbox) or segmentation (polygon)"
    )
    parser.add_argument(
        "--val-size",
        type=float,
        default=0.2,
        help="Validation set proportion (default: 0.2)"
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.0,
        help="Test set proportion (default: 0.0)"
    )
    parser.add_argument(
        "--labels",
        nargs="*",
        help="Specific labels to include (optional)"
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not Path(args.json_dir).exists():
        logger.error(f"Input directory does not exist: {args.json_dir}")
        return 1
    
    # Build labelme2yolo command
    cmd = [
        "labelme2yolo",
        "--json_dir", args.json_dir,
        "--val_size", str(args.val_size),
        "--test_size", str(args.test_size),
    ]
    
    # Set output format
    if args.mode == "segmentation":
        cmd.extend(["--output_format", "polygon"])
    else:
        cmd.extend(["--output_format", "bbox"])
    
    # Add labels if specified
    if args.labels:
        cmd.extend(args.labels)
    
    logger.info(f"Exporting to YOLO format: {' '.join(cmd)}")
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    # Change to output directory and run conversion
    original_cwd = os.getcwd()
    try:
        os.chdir(args.output)
        result = subprocess.run(cmd, text=True)
        
        if result.returncode == 0:
            logger.info(f"Export completed successfully to: {Path(args.output).absolute()}")
            return 0
        else:
            logger.error("Export failed")
            return 1
            
    except KeyboardInterrupt:
        logger.info("Export cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Export error: {e}")
        return 1
    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    sys.exit(main())