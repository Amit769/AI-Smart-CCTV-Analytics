"""
Advanced CCTV Analytics - Main Application Entrypoint.
Provides both Web Command Center Dashboard and Headless/Desktop CCTV Monitoring modes.
"""

import sys
import argparse
import logging
import webbrowser
import cv2
from pathlib import Path

from config import load_config, get_project_root
from core.camera import scan_connected_cameras
from core.analytics_engine import AnalyticsEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CCTV.Main")


def print_banner(cfg, connected_cams):
    loc_cfg = cfg.get("location", {})
    sos_cfg = cfg.get("sos_alert", {})
    det_cfg = cfg.get("detection", {})

    print("=" * 75)
    print("      ADVANCED CCTV ANALYTICS - HAZARD & SOS COMMAND CENTER")
    print("=" * 75)
    print(f" [✓] Connected Hardware Cameras Found : {connected_cams}")
    print(f" [✓] Active Hardware Device Index     : {cfg.get('camera', {}).get('device_index', 0)}")
    print(f" [✓] Trained AI Hazard Model Path     : {det_cfg.get('model_path')}")
    print(f" [✓] Hazard Confirmation Threshold    : {det_cfg.get('consecutive_frames_required', 5)} consecutive frames")
    print(f" [✓] Minimum AI Confidence Required   : {det_cfg.get('confidence_threshold', 0.70) * 100:.0f}%")
    print(f" [✓] Alert Cooldown Suppression       : {det_cfg.get('cooldown_seconds', 60)} seconds")
    print(f" [✓] Location Pinpoint Coordinates    : {loc_cfg.get('default_latitude')}, {loc_cfg.get('default_longitude')}")
    print(f" [✓] SOS Emergency Dispatch Contact   : {sos_cfg.get('sos_phone_number')}")
    print("=" * 75 + "\n")


def run_window_mode(engine: AnalyticsEngine):
    """Runs CCTV monitoring with OpenCV desktop window."""
    print("Press 'q' in the video window to quit, or 's' to silence alarm.")
    engine.start()

    window_title = "Advanced CCTV Analytics - Live Feed"
    cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)

    try:
        while engine.is_running:
            with engine._frame_lock:
                frame = engine.latest_processed_frame

            if frame is not None:
                cv2.imshow(window_title, frame)

            key = cv2.waitKey(15) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                engine.alarm.silence()
                print("Alarm silenced.")
    finally:
        cv2.destroyAllWindows()
        engine.stop()


def main():
    parser = argparse.ArgumentParser(description="Advanced CCTV Analytics System")
    parser.add_argument("--dashboard", action="store_true", default=True,
                        help="Launch web dashboard interface (default: True)")
    parser.add_argument("--headless", action="store_true",
                        help="Run headless without web server or GUI")
    parser.add_argument("--window", action="store_true",
                        help="Run with desktop OpenCV display window")
    parser.add_argument("--port", type=int, default=8000,
                        help="Web dashboard port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not auto-open browser")
    args = parser.parse_args()

    project_root = get_project_root()
    cfg = load_config()

    # 1. Enforce connected cameras rule
    connected = scan_connected_cameras()
    if not connected:
        print("\n[CRITICAL ERROR] No physical cameras detected on the system!")
        print("Per project specifications, mock or demo scenes are strictly prohibited.")
        print("Please plug in a physical webcam or connect an IP CCTV camera and try again.\n")
        sys.exit(1)

    print_banner(cfg, connected)

    # 2. Check trained model
    model_file = project_root / cfg.get("detection", {}).get("model_path", "models/hazard_best.pt")
    if not model_file.exists():
        print(f"[Notice] Trained model {model_file} not found yet. Running base detector.")

    if args.headless:
        print("Starting in HEADLESS monitoring mode. Press Ctrl+C to terminate.")
        engine = AnalyticsEngine(config=cfg, project_root=project_root)
        engine.start()
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            engine.stop()
            print("\nMonitoring stopped.")

    elif args.window:
        engine = AnalyticsEngine(config=cfg, project_root=project_root)
        run_window_mode(engine)

    else:
        # Default: Launch Web Dashboard
        import uvicorn
        dashboard_url = f"http://127.0.0.1:{args.port}"
        print(f"Starting CCTV Command Center Web Dashboard at: {dashboard_url}")

        if not args.no_browser:
            import threading
            threading.Timer(1.5, lambda: webbrowser.open(dashboard_url)).start()

        uvicorn.run("web_app:app", host="127.0.0.1", port=args.port, reload=False)


if __name__ == "__main__":
    main()
