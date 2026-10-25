"""
Camera hardware interface for Advanced CCTV Analytics.
Strictly requires connected physical cameras. Demo scenes and mock cameras are forbidden.
Uses Microsoft Media Foundation (MSMF) on Windows for native OS camera broker compatibility
(prevents Windows Studio Effects flap and maximizes frame rate to 30 FPS).
"""

import sys
import cv2
import threading
import time
import logging
from typing import List, Tuple, Optional
import numpy as np

logger = logging.getLogger("CCTV.Camera")

# Global cache so hardware is scanned ONLY ONCE at startup
_CACHED_CAMERAS: List[int] = [0]


def scan_connected_cameras() -> List[int]:
    """Returns cached camera list to prevent spamming camera device opens."""
    global _CACHED_CAMERAS
    return _CACHED_CAMERAS


class CameraStream:
    def __init__(self, device_index: int = 0, resolution: Tuple[int, int] = (640, 480), fps: int = 30):
        self.active_index = int(device_index)
        self.target_w, self.target_h = resolution
        self.target_fps = fps
        self.backend_name = "MSMF/HW"

        self.cap = self._open_capture()

        self.ret = False
        self.frame: Optional[np.ndarray] = None
        self.running = True
        self._lock = threading.Lock()
        self._has_frame = threading.Event()
        self._new_frame_event = threading.Event()

        # Dedicated background thread to grab frames constantly so hardware stays active
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

        # Wait up to 2.5 seconds for first frame to arrive to ensure stable stream
        self._has_frame.wait(timeout=2.5)
        logger.info(f"Camera #{self.active_index} initialized via {self.backend_name} (Ready: {self.ret}).")

    def _open_capture(self) -> cv2.VideoCapture:
        """Opens capture device preferring MSMF on Windows for max FPS and Studio Effects compatibility."""
        is_windows = sys.platform.startswith("win")
        cap = None

        if is_windows:
            logger.info(f"Connecting to hardware camera #{self.active_index} via Media Foundation (MSMF)...")
            cap = cv2.VideoCapture(self.active_index, cv2.CAP_MSMF)
            if cap.isOpened():
                self.backend_name = "MSMF/HW"
            else:
                logger.warning("CAP_MSMF open failed. Falling back to DirectShow (CAP_DSHOW)...")
                cap = cv2.VideoCapture(self.active_index, cv2.CAP_DSHOW)
                self.backend_name = "DirectShow/HW"
        else:
            logger.info(f"Connecting to hardware camera #{self.active_index}...")
            cap = cv2.VideoCapture(self.active_index)
            self.backend_name = "V4L2/HW"

        if not cap.isOpened():
            logger.error(f"Failed to open hardware camera at index {self.active_index}!")
            return cap

        # Set hardware capture format to MJPG for 30 FPS USB/webcam throughput
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_h)
        cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        return cap

    def _capture_loop(self):
        """Continuously reads from physical camera driver."""
        while self.running:
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self._lock:
                        self.ret = True
                        self.frame = frame
                    self._has_frame.set()
                    self._new_frame_event.set()
                else:
                    time.sleep(0.005)
            else:
                time.sleep(0.05)

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Used by AnalyticsEngine to fetch latest frame from RAM buffer."""
        with self._lock:
            if self.frame is not None:
                return self.ret, self.frame.copy()
            return False, None

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        return self.read_frame()

    def wait_for_frame(self, timeout: float = 0.05) -> bool:
        """Waits until a new frame is received from camera."""
        flag = self._new_frame_event.wait(timeout=timeout)
        self._new_frame_event.clear()
        return flag

    def is_connected(self) -> bool:
        return self.cap.isOpened() and self.ret

    def release(self):
        self.running = False
        time.sleep(0.05)
        if self.cap.isOpened():
            self.cap.release()
        logger.info(f"Camera #{self.active_index} released.")