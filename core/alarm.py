"""
Emergency Alarm System for Advanced CCTV Analytics.
Activates an audible hazard siren (using Windows winsound in a background thread)
and provides alarm state management.
"""

import time
import threading
import logging
import platform

logger = logging.getLogger("CCTV.Alarm")

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class EmergencyAlarm:
    """
    Manages audible and visual hazard alarms without blocking video processing.
    """

    def __init__(self, high_freq: int = 1600, low_freq: int = 950, beep_duration: float = 0.3):
        self.high_freq = high_freq
        self.low_freq = low_freq
        self.beep_duration = beep_duration
        self._is_active = False
        self._alarm_thread: threading.Thread = None
        self._lock = threading.Lock()
        self.last_triggered_hazard = "None"
        self.trigger_time = 0.0

    def trigger(self, hazard_type: str = "Fire"):
        """Activates the emergency alarm if not already ringing."""
        with self._lock:
            self.last_triggered_hazard = hazard_type
            self.trigger_time = time.time()
            if self._is_active:
                return

            self._is_active = True
            logger.warning(f"🚨 ALARM ACTIVATED! Hazard detected: {hazard_type}")
            self._alarm_thread = threading.Thread(target=self._siren_loop, daemon=True)
            self._alarm_thread.start()

    def silence(self):
        """Silences the active emergency alarm."""
        with self._lock:
            if self._is_active:
                logger.info("Alarm silenced by user/cooldown.")
                self._is_active = False

    def is_ringing(self) -> bool:
        """Returns True if the siren is currently ringing."""
        return self._is_active

    def _siren_loop(self):
        """Alternating two-tone siren loop executed in background."""
        while self._is_active:
            if HAS_WINSOUND and platform.system() == "Windows":
                try:
                    # High pitch burst
                    winsound.Beep(self.high_freq, int(self.beep_duration * 1000))
                    if not self._is_active:
                        break
                    time.sleep(0.05)
                    # Low pitch burst
                    winsound.Beep(self.low_freq, int(self.beep_duration * 1000))
                    time.sleep(0.05)
                except Exception as e:
                    logger.debug(f"Alarm sound error: {e}")
                    time.sleep(0.5)
            else:
                # Fallback for systems without winsound
                time.sleep(0.5)
