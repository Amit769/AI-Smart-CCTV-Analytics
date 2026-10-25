"""
Frame Preprocessing Pipeline for Advanced CCTV Analytics.
Implements OpenCV resizing and denoising as specified in the system flowchart.
"""

import cv2
import numpy as np
from typing import Tuple


class FramePreprocessor:
    """
    Handles frame extraction, resizing, and noise reduction (OpenCV resize, denoise).
    """

    def __init__(self, target_resolution: Tuple[int, int] = (640, 480), apply_denoise: bool = True):
        self.target_resolution = target_resolution
        self.apply_denoise = apply_denoise

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies resizing and noise reduction to a raw camera frame.
        """
        if frame is None or frame.size == 0:
            return frame

        # 1. Resize to standardized target resolution for consistent AI inference
        h, w = frame.shape[:2]
        if (w, h) != self.target_resolution:
            resized = cv2.resize(frame, self.target_resolution, interpolation=cv2.INTER_LINEAR)
        else:
            resized = frame.copy()

        # 2. Denoise frame if enabled (fast Gaussian smoothing preserving edges)
        if self.apply_denoise:
            # Gaussian blur with gentle kernel (3x3) removes sensor noise without sacrificing detection sharpness
            denoised = cv2.GaussianBlur(resized, (3, 3), 0)
            return denoised

        return resized
