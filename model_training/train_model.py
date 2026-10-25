"""
Model Training Script for Advanced CCTV Hazard Analytics.
Trains YOLOv8 on the prepared CCTV hazard dataset (fire, smoke, falls, anomalies).
Exports the trained weights to models/hazard_best.pt.
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrainHazardModel")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_YAML_PATH = PROJECT_ROOT / "model_training" / "datasets" / "hazard_dataset" / "data.yaml"
MODELS_DIR = PROJECT_ROOT / "models"
DEST_MODEL_PATH = MODELS_DIR / "hazard_best.pt"


def train_hazard_model(epochs: int = 5, imgsz: int = 416, batch_size: int = 16):
    """
    Trains YOLOv8 on the CCTV hazard dataset and exports the resulting model.
    """
    if not DATA_YAML_PATH.exists():
        raise FileNotFoundError(
            f"Dataset configuration not found at {DATA_YAML_PATH}! "
            "Please run download_kaggle_dataset.py first."
        )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print(" ADVANCED CCTV HAZARD ANALYTICS: MODEL TRAINING ")
    print(f" Dataset config: {DATA_YAML_PATH}")
    print(f" Epochs: {epochs} | Image size: {imgsz} | Batch size: {batch_size}")
    print("=" * 75)

    # Initialize YOLOv8 Nano model (fast and accurate for edge/CCTV)
    logger.info("Initializing YOLOv8n base model...")
    model = YOLO("yolov8n.pt")

    logger.info("Beginning model training on CCTV hazard dataset...")
    results = model.train(
        data=str(DATA_YAML_PATH),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch_size,
        workers=2,
        name="cctv_hazard_run",
        project=str(PROJECT_ROOT / "model_training" / "runs"),
        exist_ok=True,
        verbose=True,
        plots=True
    )

    # Locate the best trained weights
    run_dir = Path(results.save_dir) if hasattr(results, "save_dir") else PROJECT_ROOT / "model_training" / "runs" / "cctv_hazard_run"
    best_weights = run_dir / "weights" / "best.pt"
    last_weights = run_dir / "weights" / "last.pt"

    trained_weights_to_copy = best_weights if best_weights.exists() else last_weights

    if trained_weights_to_copy.exists():
        shutil.copy2(trained_weights_to_copy, DEST_MODEL_PATH)
        logger.info(f"Successfully copied trained weights to: {DEST_MODEL_PATH}")
    else:
        logger.warning(f"Weights file not found at {best_weights}, saving current model...")
        model.save(str(DEST_MODEL_PATH))

    # Run validation
    logger.info("Evaluating trained model on validation set...")
    val_results = model.val()
    
    print("\n" + "=" * 75)
    print(" MODEL TRAINING COMPLETE ")
    print(f" Saved Model: {DEST_MODEL_PATH}")
    if hasattr(val_results, "box"):
        print(f" Validation mAP50: {val_results.box.map50:.4f}")
        print(f" Validation mAP50-95: {val_results.box.map:.4f}")
    print("=" * 75 + "\n")

    return DEST_MODEL_PATH


if __name__ == "__main__":
    epochs_to_run = 5
    if len(sys.argv) > 1:
        try:
            epochs_to_run = int(sys.argv[1])
        except ValueError:
            pass
    train_hazard_model(epochs=epochs_to_run)
