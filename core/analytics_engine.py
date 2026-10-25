"""
Unified CCTV Analytics Engine.
Orchestrates Camera Stream, Frame Preprocessing, Asynchronous YOLO Hazard Detection,
Emergency Siren Alarm, Location Pinpointing, Evidence Snapshotting, and SOS Dispatch.
Decoupled multi-threaded pipeline ensures high framerate (20-30 FPS) live streaming.
"""

import cv2
import time
import logging
import threading
from collections import deque
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from core.camera import CameraStream, scan_connected_cameras
from core.preprocessor import FramePreprocessor
from core.detector import HazardDetector, ConfirmedHazardEvent
from core.alarm import EmergencyAlarm
from core.locator import CameraLocator, LocationInfo
from core.alert_dispatcher import AlertDispatcher

logger = logging.getLogger("CCTV.Engine")


class AnalyticsEngine:
    """
    Core CCTV Analytics Engine running high-framerate video rendering and decoupled AI monitoring.
    """

    def __init__(self, config: Dict[str, Any], project_root: Path):
        self.config = config
        self.project_root = project_root

        # 1. Initialize Camera (Media Foundation on Windows)
        cam_cfg = config.get("camera", {})
        res = tuple(cam_cfg.get("resolution", [640, 480]))
        self.camera = CameraStream(
            device_index=cam_cfg.get("device_index", 0),
            resolution=res,
            fps=cam_cfg.get("fps", 30)
        )

        # 2. Initialize Preprocessor
        self.preprocessor = FramePreprocessor(
            target_resolution=res,
            apply_denoise=cam_cfg.get("denoise", False)
        )

        # 3. Initialize Detector
        det_cfg = config.get("detection", {})
        model_path = project_root / det_cfg.get("model_path", "models/hazard_best.pt")
        self.detector = HazardDetector(
            model_path=model_path,
            conf_threshold=det_cfg.get("confidence_threshold", 0.70),
            consecutive_required=det_cfg.get("consecutive_frames_required", 5),
            cooldown_seconds=det_cfg.get("cooldown_seconds", 60.0)
        )

        # 4. Initialize Alarm
        alarm_cfg = config.get("alarm", {})
        self.alarm = EmergencyAlarm(
            high_freq=alarm_cfg.get("siren_frequency_high", 1600),
            low_freq=alarm_cfg.get("siren_frequency_low", 950),
            beep_duration=alarm_cfg.get("beep_duration_ms", 350) / 1000.0
        )

        # 5. Initialize Locator
        loc_cfg = config.get("location", {})
        self.locator = CameraLocator(
            default_lat=loc_cfg.get("default_latitude", 28.6139),
            default_lon=loc_cfg.get("default_longitude", 77.2090),
            location_name=loc_cfg.get("location_name", "Gate 2 - Main Perimeter"),
            use_auto=loc_cfg.get("use_auto_geolocation", True)
        )

        # 6. Initialize Alert Dispatcher
        self.dispatcher = AlertDispatcher(config=config, project_root=project_root)

        # Runtime State
        self.is_running = False
        self.current_fps = 0.0
        self._fps_history = deque(maxlen=60)
        self.latest_raw_frame = None
        self.latest_processed_frame = None
        self.latest_jpeg = None
        self.last_confirmed_event: Optional[ConfirmedHazardEvent] = None
        self.last_snapshot_path: Optional[str] = None

        self._frame_lock = threading.Lock()
        self._ai_input_frame = None
        self._ai_input_lock = threading.Lock()
        self._new_frame_event = threading.Event()

        self._render_thread: Optional[threading.Thread] = None
        self._ai_thread: Optional[threading.Thread] = None

    def start(self):
        """Starts background rendering and asynchronous AI detection threads."""
        if self.is_running:
            return
        self.is_running = True

        # Render loop: grabs camera frames, draws detections & HUD at full hardware framerate
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()

        # Decoupled AI loop: performs YOLO inference asynchronously without blocking video stream
        self._ai_thread = threading.Thread(target=self._ai_worker_loop, daemon=True)
        self._ai_thread.start()

        logger.info("CCTV Analytics Engine started successfully (High-FPS Decoupled Mode).")

    def stop(self):
        """Stops background analytics loops and releases camera hardware."""
        self.is_running = False
        if self._render_thread and self._render_thread.is_alive():
            self._render_thread.join(timeout=1.5)
        if self._ai_thread and self._ai_thread.is_alive():
            self._ai_thread.join(timeout=1.5)
        self.alarm.silence()
        self.camera.release()
        logger.info("CCTV Analytics Engine stopped.")

    def _render_loop(self):
        """
        High-speed rendering loop running at physical camera speed (20-30 FPS).
        Annotates frames with latest detections and generates web MJPEG buffer.
        """
        while self.is_running:
            ret, frame = self.camera.read_frame()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # 1. Preprocess
            preprocessed_frame = self.preprocessor.preprocess(frame)

            # Pass latest preprocessed frame to AI background worker
            with self._ai_input_lock:
                self._ai_input_frame = preprocessed_frame

            # 2. Fast Annotation from cached detection boxes (< 1ms)
            annotated_frame = self.detector.annotate_frame(preprocessed_frame)

            # 3. Calculate 1.0-second Sliding Window FPS (Smooth & Accurate)
            now = time.time()
            self._fps_history.append(now)
            while self._fps_history and self._fps_history[0] < now - 1.0:
                self._fps_history.popleft()
            self.current_fps = round(float(len(self._fps_history)), 1)

            # Draw system FPS badge on top right of the frame
            cv2.putText(annotated_frame, f"FPS: {self.current_fps}", (annotated_frame.shape[1] - 110, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # 4. Encode frame to JPEG for live web streaming
            ret_enc, jpeg_buffer = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])

            with self._frame_lock:
                self.latest_raw_frame = frame
                self.latest_processed_frame = annotated_frame
                if ret_enc:
                    self.latest_jpeg = jpeg_buffer.tobytes()

            self._new_frame_event.set()

            # Wait for next physical camera frame with short timeout
            self.camera.wait_for_frame(timeout=0.035)

    def _ai_worker_loop(self):
        """
        Asynchronous AI Hazard Detection loop. Runs inference on latest frame
        without blocking the rendering stream.
        """
        while self.is_running:
            frame_to_eval = None
            with self._ai_input_lock:
                if self._ai_input_frame is not None:
                    frame_to_eval = self._ai_input_frame

            if frame_to_eval is not None:
                confirmed_hazards = self.detector.evaluate_frame(frame_to_eval)
                if confirmed_hazards:
                    for hazard in confirmed_hazards:
                        self._handle_hazard_confirmed(hazard, frame_to_eval)
                # Short pause between inferences
                time.sleep(0.005)
            else:
                time.sleep(0.02)

    def _handle_hazard_confirmed(self, hazard: ConfirmedHazardEvent, frame: Any):
        """Triggers alarm, saves snapshot, retrieves location, and dispatches SOS alert."""
        self.last_confirmed_event = hazard
        cam_name = self.config.get("camera", {}).get("camera_name", f"Camera #{self.camera.active_index}")

        # 1. Activate Emergency Siren
        if self.config.get("alarm", {}).get("sound_enabled", True):
            self.alarm.trigger(hazard_type=hazard.hazard_type.capitalize())

        # 2. Get Live Location & Google Maps Link
        location: LocationInfo = self.locator.get_current_location()

        # 3. Save Timestamped Evidence Snapshot
        snapshot_path = self.dispatcher.save_evidence_snapshot(
            frame=frame,
            hazard_type=hazard.hazard_type,
            confidence=hazard.confidence,
            camera_name=cam_name,
            location=location
        )
        self.last_snapshot_path = str(snapshot_path)

        # 4. Send SOS Alert to Emergency Phone Number
        self.dispatcher.dispatch_sos(
            hazard_type=hazard.hazard_type,
            confidence=hazard.confidence,
            camera_name=cam_name,
            location=location,
            snapshot_path=snapshot_path
        )

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Thread-safe retrieval of latest processed JPEG for web stream."""
        with self._frame_lock:
            return self.latest_jpeg

    def wait_for_new_jpeg(self, timeout: float = 0.04) -> Optional[bytes]:
        """Waits for a newly rendered JPEG frame to deliver smooth streaming to clients."""
        self._new_frame_event.wait(timeout=timeout)
        self._new_frame_event.clear()
        with self._frame_lock:
            return self.latest_jpeg

    def get_system_status(self) -> Dict[str, Any]:
        """Returns comprehensive real-time telemetry of the CCTV analytics system."""
        loc = self.locator.get_current_location()
        with self.detector._lock:
            consecutive_counts = dict(self.detector.consecutive_counts)

        return {
            "camera_connected": self.camera.is_connected(),
            "active_camera_index": self.camera.active_index,
            "connected_cameras_list": scan_connected_cameras(),
            "backend": self.camera.backend_name,
            "fps": self.current_fps,
            "alarm_active": self.alarm.is_ringing(),
            "last_hazard": self.alarm.last_triggered_hazard,
            "consecutive_counts": consecutive_counts,
            "consecutive_required": self.detector.consecutive_required,
            "confidence_threshold": self.detector.conf_threshold,
            "cooldown_seconds": self.detector.cooldown_seconds,
            "location": {
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "location_name": loc.location_name,
                "maps_url": loc.maps_url
            },
            "sos_phone_number": self.config.get("sos_alert", {}).get("sos_phone_number", "+1234567890"),
            "last_snapshot": self.last_snapshot_path
        }
