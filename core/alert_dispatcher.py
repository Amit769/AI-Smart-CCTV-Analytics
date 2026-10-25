"""
Emergency SOS Alert Dispatcher and Evidence Storage for Advanced CCTV Analytics.
Saves timestamped snapshots with overlay annotations and sends emergency notifications
(SMS, WhatsApp, Telegram, Local incident log) with Google Maps pinpointing.
"""

import os
import cv2
import json
import time
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from core.locator import LocationInfo

logger = logging.getLogger("CCTV.AlertDispatcher")


class AlertDispatcher:
    """
    Manages evidence snapshots and dispatches SOS alerts to the emergency contact number.
    """

    def __init__(self, config: Dict[str, Any], project_root: Path):
        self.config = config
        self.project_root = project_root
        self.snapshots_dir = project_root / config.get("evidence", {}).get("snapshots_dir", "evidence/snapshots")
        self.logs_dir = project_root / config.get("evidence", {}).get("logs_dir", "evidence/logs")
        self.incident_log_file = self.logs_dir / "incidents.json"

        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self._init_incident_log()

    def _init_incident_log(self):
        """Initializes incidents.json if it doesn't already exist."""
        if not self.incident_log_file.exists():
            with open(self.incident_log_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    def save_evidence_snapshot(
        self,
        frame,
        hazard_type: str,
        confidence: float,
        camera_name: str,
        location: LocationInfo
    ) -> Path:
        """
        Saves snapshot evidence image with timestamped HUD overlay.
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        time_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = f"hazard_{hazard_type.lower()}_{timestamp_str}.jpg"
        save_path = self.snapshots_dir / filename

        annotated_frame = frame.copy()
        h, w = annotated_frame.shape[:2]

        # Draw red alert banner header
        cv2.rectangle(annotated_frame, (0, 0), (w, 45), (0, 0, 180), -1)
        alert_header = f"HAZARD DETECTED: {hazard_type.upper()} ({confidence*100:.1f}%)"
        cv2.putText(annotated_frame, alert_header, (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

        # Draw footer banner with camera, time and coordinates
        cv2.rectangle(annotated_frame, (0, h - 35), (w, h), (20, 20, 20), -1)
        footer_text = f"Cam: {camera_name} | Time: {time_display} | Loc: {location.latitude:.4f}, {location.longitude:.4f}"
        cv2.putText(annotated_frame, footer_text, (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        cv2.imwrite(str(save_path), annotated_frame)
        logger.info(f"Evidence snapshot captured: {save_path.name}")
        return save_path

    def dispatch_sos(
        self,
        hazard_type: str,
        confidence: float,
        camera_name: str,
        location: LocationInfo,
        snapshot_path: Path
    ):
        """
        Dispatches emergency SOS notification in a background thread to prevent frame stalls.
        """
        thread = threading.Thread(
            target=self._dispatch_worker,
            args=(hazard_type, confidence, camera_name, location, snapshot_path),
            daemon=True
        )
        thread.start()

    def _dispatch_worker(
        self,
        hazard_type: str,
        confidence: float,
        camera_name: str,
        location: LocationInfo,
        snapshot_path: Path
    ):
        """Worker thread executing the notifications."""
        sos_cfg = self.config.get("sos_alert", {})
        target_number = sos_cfg.get("sos_phone_number", "+1234567890")
        time_str = datetime.now().strftime("%H:%M:%S")

        # Official alert message structure matching the project design
        alert_body = (
            f"🚨 EMERGENCY SOS ALERT: {hazard_type.upper()} DETECTED!\n"
            f"Camera: {camera_name} | Time: {time_str}\n"
            f"Confidence: {confidence * 100:.1f}%\n"
            f"Location: {location.maps_url}\n"
            f"Evidence: {snapshot_path.name}"
        )

        logger.warning("\n" + "=" * 65)
        logger.warning("DISPATCHING SOS EMERGENCY ALERT")
        logger.warning(f"Target SOS Number: {target_number}")
        logger.warning(alert_body)
        logger.warning("=" * 65 + "\n")

        # 1. Log incident to incident history
        incident_entry = {
            "id": int(time.time() * 1000),
            "timestamp": datetime.now().isoformat(),
            "time_display": time_str,
            "hazard_type": hazard_type,
            "confidence": round(confidence, 3),
            "camera_name": camera_name,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "maps_url": location.maps_url,
            "sos_number": target_number,
            "snapshot_file": snapshot_path.name,
            "snapshot_path": str(snapshot_path),
            "status": "DISPATCHED"
        }
        self._record_incident(incident_entry)

        channels = sos_cfg.get("channels", {})

        # 2. Twilio SMS
        if channels.get("sms") and sos_cfg.get("twilio", {}).get("account_sid"):
            self._send_twilio_sms(sos_cfg["twilio"], target_number, alert_body)

        # 3. Twilio WhatsApp
        if channels.get("whatsapp") and sos_cfg.get("twilio", {}).get("account_sid"):
            self._send_twilio_whatsapp(sos_cfg["twilio"], target_number, alert_body)

        # 4. Telegram Bot API
        if channels.get("telegram") and sos_cfg.get("telegram", {}).get("bot_token"):
            self._send_telegram(sos_cfg["telegram"], alert_body, snapshot_path)

    def _record_incident(self, entry: Dict[str, Any]):
        """Appends incident record to JSON store."""
        try:
            incidents = []
            if self.incident_log_file.exists():
                with open(self.incident_log_file, "r", encoding="utf-8") as f:
                    incidents = json.load(f)
            incidents.insert(0, entry)  # Prepend latest
            # Keep last 100 incidents
            incidents = incidents[:100]
            with open(self.incident_log_file, "w", encoding="utf-8") as f:
                json.dump(incidents, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to record incident: {e}")

    def _send_twilio_sms(self, twilio_cfg: dict, to_number: str, message: str):
        try:
            from twilio.rest import Client
            client = Client(twilio_cfg["account_sid"], twilio_cfg["auth_token"])
            msg = client.messages.create(
                body=message,
                from_=twilio_cfg.get("from_phone_number"),
                to=to_number
            )
            logger.info(f"Twilio SMS sent successfully! SID: {msg.sid}")
        except Exception as e:
            logger.error(f"Twilio SMS dispatch failed: {e}")

    def _send_twilio_whatsapp(self, twilio_cfg: dict, to_number: str, message: str):
        try:
            from twilio.rest import Client
            client = Client(twilio_cfg["account_sid"], twilio_cfg["auth_token"])
            from_whatsapp = twilio_cfg.get("whatsapp_from", "whatsapp:+14155238886")
            to_whatsapp = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
            msg = client.messages.create(
                body=message,
                from_=from_whatsapp,
                to=to_whatsapp
            )
            logger.info(f"Twilio WhatsApp alert sent! SID: {msg.sid}")
        except Exception as e:
            logger.error(f"Twilio WhatsApp dispatch failed: {e}")

    def _send_telegram(self, tg_cfg: dict, message: str, photo_path: Path):
        try:
            import urllib.request
            token = tg_cfg.get("bot_token")
            chat_id = tg_cfg.get("chat_id")
            if not token or not chat_id:
                return

            # Send photo with caption
            send_url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
            req = urllib.request.Request(
                send_url,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
            logger.info("Telegram emergency alert message dispatched.")
        except Exception as e:
            logger.error(f"Telegram dispatch failed: {e}")

    def get_recent_incidents(self, limit: int = 20) -> list:
        """Retrieves recent incidents from log."""
        try:
            if self.incident_log_file.exists():
                with open(self.incident_log_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data[:limit]
        except Exception:
            pass
        return []
