"""
Multi-frame Hazard & Anomaly Detector for Advanced CCTV Analytics.
Loads trained YOLOv8 model, validates consecutive frame persistence (>= 5 frames),
and enforces 60s cooldown to prevent false alarms.
Supports asynchronous inference decoupling for high-framerate 25-30 FPS streaming.
"""

import time
import logging
import threading
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import cv2
from ultralytics import YOLO

logger = logging.getLogger("CCTV.Detector")


@dataclass
class DetectionResult:
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    is_hazard: bool


@dataclass
class ConfirmedHazardEvent:
    hazard_type: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    consecutive_frames: int
    timestamp: float


class HazardDetector:
    """
    Performs AI inference, multi-frame confidence tracking, and cooldown logic.
    Thread-safe to allow decoupled asynchronous execution from the video rendering pipeline.
    """

    def __init__(self, model_path: Path, conf_threshold: float = 0.70,
                 consecutive_required: int = 5, cooldown_seconds: float = 60.0):
        self.model_path = Path(model_path)
        self.conf_threshold = conf_threshold
        self.consecutive_required = consecutive_required
        self.cooldown_seconds = cooldown_seconds

        self._lock = threading.Lock()
        self.cached_boxes: List[Tuple[str, float, np.ndarray]] = []

        self.consecutive_counts: Dict[str, int] = {
            "fire": 0,
            "smoke": 0,
            "fall": 0,
            "intrusion": 0,
            "unusual_hazard": 0
        }
        self.last_alert_time: Dict[str, float] = {
            "fire": 0.0,
            "smoke": 0.0,
            "fall": 0.0,
            "intrusion": 0.0,
            "unusual_hazard": 0.0
        }

        self.model = self._load_model()

    def _load_model(self) -> YOLO:
        """Loads YOLO model from weights file. Prefers hazard_best.pt for native PyTorch CPU performance."""
        target_path = self.model_path

        # If OpenVINO path or directory was passed, prefer PyTorch .pt for speed & stability
        if target_path.is_dir() or "openvino" in str(target_path).lower():
            pt_candidate = target_path.parent / "hazard_best.pt"
            if pt_candidate.exists():
                logger.info(f"OpenVINO directory detected; selecting high-speed PyTorch weights: {pt_candidate}")
                target_path = pt_candidate

        if target_path.exists():
            logger.info(f"Loading custom trained hazard model: {target_path}")
            return YOLO(str(target_path))
        else:
            logger.warning(
                f"Model file {target_path} not found. Initializing base YOLOv8n detector."
            )
            return YOLO("yolov8n.pt")

    def reload_model(self, new_model_path: Optional[Path] = None):
        """Reloads model if weights were newly trained."""
        if new_model_path:
            self.model_path = Path(new_model_path)
        if self.model_path.exists():
            logger.info(f"Reloading model from: {self.model_path}")
            with self._lock:
                self.model = YOLO(str(self.model_path))

    def evaluate_frame(self, frame: np.ndarray) -> List[ConfirmedHazardEvent]:
        """
        Runs YOLO model inference on input frame, tracks persistence, and returns confirmed hazards.
        Safe to call from background AI worker thread without blocking video rendering.
        """
        confirmed_events: List[ConfirmedHazardEvent] = []
        if self.model is None or frame is None:
            return confirmed_events

        try:
            results = self.model(
                frame,
                verbose=False,
                imgsz=256,
                conf=self.conf_threshold
            )
        except Exception as e:
            logger.error(f"Inference error in HazardDetector: {e}")
            return confirmed_events

        new_cached_boxes: List[Tuple[str, float, np.ndarray]] = []
        current_frame_hazards: Dict[str, List[DetectionResult]] = {
            "fire": [], "smoke": [], "fall": [], "intrusion": [], "unusual_hazard": []
        }

        if results and len(results) > 0 and results[0].boxes is not None:
            names = self.model.names if hasattr(self.model, "names") else {}
            for box in results[0].boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                class_name_raw = names.get(cls_id, f"class_{cls_id}").lower()

                hazard_type = None
                if "fire" in class_name_raw:
                    hazard_type = "fire"
                elif "smoke" in class_name_raw:
                    hazard_type = "smoke"
                elif "fall" in class_name_raw:
                    hazard_type = "fall"
                elif "intrusion" in class_name_raw:
                    hazard_type = "intrusion"
                elif class_name_raw == "person":
                    bw = xyxy[2] - xyxy[0]
                    bh = xyxy[3] - xyxy[1]
                    if bh > 0 and (bw / bh) > 1.35:
                        hazard_type = "fall"

                if hazard_type and conf >= self.conf_threshold:
                    new_cached_boxes.append((hazard_type, conf, xyxy))
                    det = DetectionResult(
                        class_name=hazard_type,
                        confidence=conf,
                        bbox=(xyxy[0], xyxy[1], xyxy[2], xyxy[3]),
                        is_hazard=True
                    )
                    current_frame_hazards[hazard_type].append(det)

        now = time.time()
        with self._lock:
            self.cached_boxes = new_cached_boxes

            # Multi-frame verification & cooldown check
            for h_type in self.consecutive_counts.keys():
                detections = current_frame_hazards.get(h_type, [])
                if len(detections) > 0:
                    self.consecutive_counts[h_type] += 1
                    best_det = max(detections, key=lambda d: d.confidence)

                    if self.consecutive_counts[h_type] >= self.consecutive_required:
                        time_since_last = now - self.last_alert_time[h_type]
                        if time_since_last >= self.cooldown_seconds:
                            confirmed_events.append(
                                ConfirmedHazardEvent(
                                    hazard_type=h_type,
                                    confidence=best_det.confidence,
                                    bbox=best_det.bbox,
                                    consecutive_frames=self.consecutive_counts[h_type],
                                    timestamp=now
                                )
                            )
                            self.last_alert_time[h_type] = now
                else:
                    if self.consecutive_counts[h_type] > 0:
                        self.consecutive_counts[h_type] = max(0, self.consecutive_counts[h_type] - 1)

        return confirmed_events

    def annotate_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Overlays bounding boxes and HUD onto frame from cached detections.
        Executes in under 1 millisecond for smooth 30 FPS rendering.
        """
        annotated_frame = frame.copy()
        with self._lock:
            boxes = list(self.cached_boxes)
            f_count = self.consecutive_counts.get("fire", 0)
            s_count = self.consecutive_counts.get("smoke", 0)
            fall_count = self.consecutive_counts.get("fall", 0)

        for hazard_type, conf, xyxy in boxes:
            x1, y1, x2, y2 = xyxy
            color = (0, 140, 255) if hazard_type == "fire" else (
                (180, 180, 180) if hazard_type == "smoke" else (
                    (0, 0, 255) if hazard_type == "fall" else (100, 255, 100)
                )
            )
            label = f"{hazard_type}: {conf:.2f}"
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated_frame, label, (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        self._draw_hud(annotated_frame, f_count, s_count, fall_count)
        return annotated_frame

    def detect_and_evaluate(self, frame: np.ndarray) -> Tuple[np.ndarray, List[ConfirmedHazardEvent]]:
        """Synchronous all-in-one detection & annotation method for tests and offline processing."""
        confirmed = self.evaluate_frame(frame)
        annotated = self.annotate_frame(frame)
        return annotated, confirmed

    def _draw_hud(self, frame: np.ndarray, f_count: int, s_count: int, fall_count: int):
        """Draws current consecutive frame tracking state on the frame."""
        hud_bg_w = 260
        hud_bg_h = 75
        cv2.rectangle(frame, (8, 8), (8 + hud_bg_w, 8 + hud_bg_h), (15, 15, 15), -1)
        cv2.rectangle(frame, (8, 8), (8 + hud_bg_w, 8 + hud_bg_h), (60, 60, 60), 1)

        cv2.putText(frame, "CCTV AI MONITOR", (16, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 200), 1)

        f_status = f"Fire: {f_count}/{self.consecutive_required}"
        s_status = f"Smoke: {s_count}/{self.consecutive_required}"
        fall_status = f"Fall: {fall_count}/{self.consecutive_required}"

        cv2.putText(frame, f_status, (16, 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 165, 255) if f_count > 0 else (180, 180, 180), 1)
        cv2.putText(frame, s_status, (130, 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (200, 200, 200) if s_count > 0 else (180, 180, 180), 1)
        cv2.putText(frame, fall_status, (16, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 255) if fall_count > 0 else (180, 180, 180), 1)
