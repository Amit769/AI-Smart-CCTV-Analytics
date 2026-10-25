"""
Kaggle and CCTV Hazard Dataset Downloader & Formatter for Advanced CCTV Analytics.
Supports:
1. Kaggle API downloading for hazard datasets (e.g. 'sayedgamal99/smoke-fire-detection-yolo').
2. Direct verified open CCTV fire & smoke hazard dataset fetcher and YOLOv8 format converter.
3. Automatically sets up images/train, images/val, labels/train, labels/val, and data.yaml.
"""

import os
import sys
import argparse
import urllib.request
import zipfile
import io
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = PROJECT_ROOT / "model_training" / "datasets"
TARGET_DATASET_DIR = DATASETS_DIR / "hazard_dataset"

FIRENET_ZIP_URL = "https://github.com/OlafenwaMoses/FireNET/releases/download/v1.0/fire-dataset.zip"


def convert_voc_to_yolo(xml_path: Path, img_width: int, img_height: int, class_mapping: dict = None) -> list:
    """Converts a Pascal VOC XML file to YOLO bounding box lines."""
    if class_mapping is None:
        class_mapping = {"fire": 0, "smoke": 1}

    yolo_lines = []
    if not xml_path.exists():
        return yolo_lines

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # If size not passed or 0, attempt to read from xml
        if img_width <= 0 or img_height <= 0:
            size = root.find("size")
            if size is not None:
                img_width = max(1, int(size.find("width").text))
                img_height = max(1, int(size.find("height").text))

        for obj in root.findall("object"):
            name = obj.find("name").text.lower().strip()
            class_id = class_mapping.get(name, 0)  # default to class 0 (fire)

            bndbox = obj.find("bndbox")
            if bndbox is None:
                continue

            xmin = float(bndbox.find("xmin").text)
            ymin = float(bndbox.find("ymin").text)
            xmax = float(bndbox.find("xmax").text)
            ymax = float(bndbox.find("ymax").text)

            # Normalize coordinates and clamp between 0.0 and 1.0
            x_center = max(0.0, min(1.0, ((xmin + xmax) / 2.0) / img_width))
            y_center = max(0.0, min(1.0, ((ymin + ymax) / 2.0) / img_height))
            width = max(0.0, min(1.0, (xmax - xmin) / img_width))
            height = max(0.0, min(1.0, (ymax - ymin) / img_height))

            if width > 0.001 and height > 0.001:
                yolo_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
    except Exception as e:
        print(f"Warning parsing {xml_path.name}: {e}")

    return yolo_lines


def download_and_prepare_verified_hazard_dataset():
    """Downloads the verified CCTV fire/hazard dataset and formats into standard YOLO directory."""
    print("=" * 70)
    print("Preparing CCTV Hazard Dataset for YOLOv8 Training...")
    print(f"Target dataset directory: {TARGET_DATASET_DIR}")
    print("=" * 70)

    TARGET_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (TARGET_DATASET_DIR / "images" / "train").mkdir(parents=True, exist_ok=True)
    (TARGET_DATASET_DIR / "images" / "val").mkdir(parents=True, exist_ok=True)
    (TARGET_DATASET_DIR / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (TARGET_DATASET_DIR / "labels" / "val").mkdir(parents=True, exist_ok=True)

    # Check if already downloaded and formatted
    existing_train_imgs = list((TARGET_DATASET_DIR / "images" / "train").glob("*.jpg"))
    if len(existing_train_imgs) >= 100:
        print(f"Dataset already exists with {len(existing_train_imgs)} training images.")
        write_data_yaml()
        return

    print(f"Downloading CCTV fire hazard archive from: {FIRENET_ZIP_URL}...")
    temp_zip = DATASETS_DIR / "temp_fire_dataset.zip"
    try:
        req = urllib.request.Request(FIRENET_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(temp_zip, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)
        print("Download complete! Extracting and converting annotations to YOLO format...")

        temp_extract = DATASETS_DIR / "raw_extracted"
        temp_extract.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(temp_zip, "r") as zf:
            zf.extractall(temp_extract)

        # Process train and validation splits
        for split_raw, split_target in [("train", "train"), ("validation", "val")]:
            img_dir = temp_extract / "fire-dataset" / split_raw / "images"
            ann_dir = temp_extract / "fire-dataset" / split_raw / "annotations"

            if not img_dir.exists():
                print(f"Warning: {img_dir} does not exist, skipping...")
                continue

            dest_img_dir = TARGET_DATASET_DIR / "images" / split_target
            dest_lbl_dir = TARGET_DATASET_DIR / "labels" / split_target

            count = 0
            for img_file in img_dir.glob("*.jpg"):
                stem = img_file.stem
                xml_file = ann_dir / f"{stem}.xml"

                # Read image dimensions
                import cv2
                img = cv2.imread(str(img_file))
                if img is None:
                    continue
                h, w = img.shape[:2]

                yolo_boxes = convert_voc_to_yolo(xml_file, w, h)

                # Copy image
                shutil.copy2(img_file, dest_img_dir / img_file.name)

                # Write YOLO label file
                lbl_file = dest_lbl_dir / f"{stem}.txt"
                with open(lbl_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(yolo_boxes) + "\n")

                count += 1

            print(f"Processed {count} images and labels for split '{split_target}'.")

        # Cleanup temporary files
        if temp_zip.exists():
            temp_zip.unlink()
        if temp_extract.exists():
            shutil.rmtree(temp_extract, ignore_errors=True)

        write_data_yaml()
        print("\nDataset successfully prepared and ready for training!")

    except Exception as e:
        print(f"Error downloading/extracting dataset: {e}")
        raise


def write_data_yaml():
    """Generates the data.yaml file required by Ultralytics YOLO."""
    yaml_content = f"""# CCTV Hazard Detection Dataset Configuration
path: {TARGET_DATASET_DIR.as_posix()}
train: images/train
val: images/val

names:
  0: fire
  1: smoke
  2: fall
  3: intrusion
"""
    yaml_path = TARGET_DATASET_DIR / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"Created YOLO configuration at: {yaml_path}")
    return yaml_path


def download_from_kaggle(dataset_identifier: str):
    """Downloads a dataset directly from Kaggle using kaggle python SDK."""
    print(f"Attempting to download Kaggle dataset: {dataset_identifier}...")
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        print("Kaggle API authenticated successfully!")
        target_path = DATASETS_DIR / dataset_identifier.replace("/", "_")
        target_path.mkdir(parents=True, exist_ok=True)
        api.dataset_download_files(dataset_identifier, path=str(target_path), unzip=True)
        print(f"Kaggle dataset downloaded and unzipped to: {target_path}")
    except Exception as e:
        print(f"\n[Notice] Kaggle API authentication was not found or failed: {e}")
        print("To use Kaggle directly:")
        print("1. Go to https://www.kaggle.com/settings -> Click 'Generate New Token'.")
        print("2. Place kaggle.json in ~/.kaggle/ or set environment variables:")
        print("   $env:KAGGLE_USERNAME='your_username'")
        print("   $env:KAGGLE_KEY='your_api_key'")
        print("\nFalling back to verified CCTV fire and hazard benchmark dataset...")
        download_and_prepare_verified_hazard_dataset()


def main():
    parser = argparse.ArgumentParser(description="Download and prepare hazard datasets for CCTV analytics.")
    parser.add_argument("--kaggle-dataset", type=str, default="", help="Kaggle dataset identifier (e.g. sayedgamal99/smoke-fire-detection-yolo)")
    args = parser.parse_args()

    if args.kaggle_dataset:
        download_from_kaggle(args.kaggle_dataset)
    else:
        download_and_prepare_verified_hazard_dataset()


if __name__ == "__main__":
    main()
