#!/usr/bin/env python3

import os
import re
import argparse
from pathlib import Path
from collections import defaultdict

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp",
    ".tif", ".tiff", ".exr", ".bmp", ".tga"
}


def human_size(num_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)

    for unit in units:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{size:.2f} PB"


def get_folder_size(folder):
    total = 0

    for root, _, files in os.walk(folder):
        for file in files:
            path = Path(root) / file
            try:
                total += path.stat().st_size
            except OSError:
                pass

    return total


def extract_frame_number(filename):
    """
    Detects frame numbers like:
    frame_0001.png
    shot01.0104.exr
    render-000245.jpg
    """
    stem = Path(filename).stem
    matches = re.findall(r"(\d+)", stem)

    if not matches:
        return None

    # Usually the last number in the filename is the frame number
    return int(matches[-1])


def looks_like_sequence(files):
    frame_numbers = []

    for file in files:
        num = extract_frame_number(file.name)
        if num is not None:
            frame_numbers.append(num)

    if len(frame_numbers) < 5:
        return False, None, None

    frame_numbers = sorted(set(frame_numbers))

    start = frame_numbers[0]
    end = frame_numbers[-1]

    expected_count = end - start + 1
    actual_count = len(frame_numbers)

    # Allow missing frames but still identify as likely sequence
    continuity_ratio = actual_count / expected_count if expected_count > 0 else 0

    if continuity_ratio >= 0.7:
        return True, start, end

    return False, start, end


def scan_folders(root_folder, min_images=50):
    root_folder = Path(root_folder).expanduser().resolve()

    results = []

    for current_root, _, files in os.walk(root_folder):
        current_folder = Path(current_root)

        image_files = [
            current_folder / file
            for file in files
            if Path(file).suffix.lower() in IMAGE_EXTENSIONS
        ]

        if len(image_files) >= min_images:
            folder_size = get_folder_size(current_folder)

            extensions = sorted(
                set(file.suffix.lower() for file in image_files)
            )

            is_sequence, start_frame, end_frame = looks_like_sequence(image_files)

            results.append({
                "folder": current_folder,
                "image_count": len(image_files),
                "folder_size": folder_size,
                "extensions": extensions,
                "is_sequence": is_sequence,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "samples": [file.name for file in image_files[:5]]
            })

    results.sort(key=lambda x: x["folder_size"], reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Find folders containing many images or possible image sequences."
    )

    parser.add_argument(
        "folder",
        help="Root folder to scan"
    )

    parser.add_argument(
        "--min-images",
        type=int,
        default=50,
        help="Minimum number of images in a folder to report. Default: 50"
    )

    args = parser.parse_args()

    results = scan_folders(args.folder, args.min_images)

    if not results:
        print("No folders found with enough image files.")
        return

    print("\nPossible image sequence folders:\n")

    for item in results:
        print("=" * 80)
        print(f"Folder       : {item['folder']}")
        print(f"Images       : {item['image_count']}")
        print(f"Folder size  : {human_size(item['folder_size'])}")
        print(f"Extensions   : {', '.join(item['extensions'])}")

        if item["is_sequence"]:
            print("Sequence     : YES")
            print(f"Frame range  : {item['start_frame']} - {item['end_frame']}")
        else:
            print("Sequence     : POSSIBLE / MANY IMAGES")

        print("Samples      :")
        for sample in item["samples"]:
            print(f"  - {sample}")

    print("=" * 80)


if __name__ == "__main__":
    main()