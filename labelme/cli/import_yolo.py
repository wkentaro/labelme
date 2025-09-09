#!/usr/bin/env python

import argparse
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("yolo_dir", help="Directory containing YOLO dataset")
    parser.add_argument("-o", "--output", help="Output directory")
    args = parser.parse_args()

    yolo_dir = args.yolo_dir
    
    if args.output is None:
        output_dir = "labelme_dataset"
    else:
        output_dir = args.output
    
    if not os.path.exists(yolo_dir):
        print(f"Error: Directory does not exist: {yolo_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)

    try:
        from yolo2labelme import yolo2labelme
        
        yolo2labelme(
            data=yolo_dir,
            out=output_dir,
            skip=False
        )
        
        print(f"Imported YOLO dataset to: {output_dir}")
        
    except Exception as e:
        print(f"Error during import: {e}")


if __name__ == "__main__":
    main()