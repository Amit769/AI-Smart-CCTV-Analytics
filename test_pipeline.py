"""
End-to-End Pipeline Verification Script for Advanced CCTV Analytics.
Tests camera discovery, trained model loading, inference, alarm, locator,
evidence snapshotting, and SOS alert dispatching.
"""

import os
import sys
import time
from pathlib import Path

from config import load_config, get_project_root
from core.camera import scan_connected_cameras, CameraStream
from core.preprocessor import FramePreprocessor
from core.detector import HazardDetector
from core.alarm import EmergencyAlarm
from core.locator import CameraLocator
from core.alert_dispatcher import AlertDispatcher


def run_verification():
    print("=" * 70)
    print("RUNNING ADVANCED CCTV ANALYTICS SYSTEM VERIFICATION")
    print("=" * 70)

    root = get_project_root()
    cfg = load_config()

    # 1. Test Camera Connection
    print("\n[1/7] Testing Connected Hardware Cameras...")
    cams = scan_connected_cameras()
    print(f"      Connected physical cameras found: {cams}")
    assert len(cams) > 0, "No hardware cameras detected!"
    cam = CameraStream(device_index=cams[0])
    ret, frame = cam.read_frame()
    assert ret and frame is not None, "Failed to capture frame from hardware camera!"
    print(f"      Successfully captured frame from Camera #{cam.active_index}: {frame.shape}")

    # 2. Test Preprocessing
    print("\n[2/7] Testing Frame Preprocessor (OpenCV Resize & Denoise)...")
    preprocessor = FramePreprocessor(target_resolution=(640, 480), apply_denoise=True)
    clean_frame = preprocessor.preprocess(frame)
    assert clean_frame.shape[:2] == (480, 640), "Preprocessing resolution mismatch!"
    print(f"      Preprocessed frame shape: {clean_frame.shape}")

    # 3. Test Trained Model
    print("\n[3/7] Testing Trained Model Loading (models/hazard_best.pt)...")
    model_path = root / "models" / "hazard_best.pt"
    assert model_path.exists(), f"Trained weights not found at {model_path}!"
    print(f"      Model weights exist: {model_path.stat().st_size / 1024 / 1024:.2f} MB")
    detector = HazardDetector(model_path=model_path, conf_threshold=0.50, consecutive_required=3)
    ann_frame, confirmed = detector.detect_and_evaluate(clean_frame)
    print("      Inference executed cleanly without errors!")

    # 4. Test Locator & Google Maps Pinpointing
    print("\n[4/7] Testing Camera Locator & Google Maps Pin...")
    locator = CameraLocator(default_lat=28.6139, default_lon=77.2090, use_auto=True)
    loc = locator.get_current_location()
    print(f"      Location: {loc.location_name}")
    print(f"      Coordinates: {loc.latitude}, {loc.longitude}")
    print(f"      Google Maps Link: {loc.maps_url}")
    assert "https://maps.google.com/?q=" in loc.maps_url, "Invalid Google Maps URL format!"

    # 5. Test Evidence Snapshot
    print("\n[5/7] Testing Evidence Snapshot Capture...")
    dispatcher = AlertDispatcher(config=cfg, project_root=root)
    snap_path = dispatcher.save_evidence_snapshot(
        frame=clean_frame,
        hazard_type="TEST_FIRE",
        confidence=0.95,
        camera_name=f"Hardware Cam #{cam.active_index}",
        location=loc
    )
    assert snap_path.exists(), "Snapshot file was not saved!"
    print(f"      Snapshot successfully saved: {snap_path.name} ({snap_path.stat().st_size} bytes)")

    # 6. Test SOS Emergency Dispatch
    print("\n[6/7] Testing SOS Emergency Notification Dispatch...")
    dispatcher.dispatch_sos(
        hazard_type="TEST_FIRE",
        confidence=0.95,
        camera_name=f"Hardware Cam #{cam.active_index}",
        location=loc,
        snapshot_path=snap_path
    )
    time.sleep(1.0)  # wait for async dispatch thread
    incidents = dispatcher.get_recent_incidents()
    assert len(incidents) > 0, "Incident was not recorded in incident log!"
    latest = incidents[0]
    print(f"      Dispatched incident recorded: {latest['hazard_type']} to {latest['sos_number']}")
    print(f"      Maps link in dispatch: {latest['maps_url']}")

    # 7. Test Emergency Siren Alarm
    print("\n[7/7] Testing Emergency Siren Alarm...")
    alarm = EmergencyAlarm()
    alarm.trigger(hazard_type="FIRE")
    assert alarm.is_ringing(), "Alarm is not in ringing state!"
    time.sleep(0.5)
    alarm.silence()
    assert not alarm.is_ringing(), "Alarm did not silence properly!"
    print("      Alarm trigger and silence tested successfully!")

    cam.release()
    print("\n" + "=" * 70)
    print(" ALL 7 PIPELINE VERIFICATION TESTS PASSED SUCCESSFULLY! ")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_verification()
