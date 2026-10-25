"""
Location and Google Maps Pinpointing Service for Advanced CCTV Analytics.
Supports fixed camera coordinates from config and live auto-geolocation.
Generates exact Google Maps pinpoint links as specified in the project flowchart.
"""

import logging
import urllib.request
import json
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("CCTV.Locator")


@dataclass
class LocationInfo:
    latitude: float
    longitude: float
    location_name: str
    maps_url: str


class CameraLocator:
    """
    Retrieves camera location and builds Google Maps links for SOS emergency dispatches.
    """

    def __init__(self, default_lat: float = 28.6139, default_lon: float = 77.2090, 
                 location_name: str = "Gate 2 - Main Perimeter", use_auto: bool = True):
        self.default_lat = default_lat
        self.default_lon = default_lon
        self.location_name = location_name
        self.use_auto = use_auto
        self._cached_location: Optional[LocationInfo] = None

    def get_current_location(self) -> LocationInfo:
        """
        Retrieves current location coordinates.
        Tries auto-geolocation if enabled, otherwise returns configured coordinates.
        """
        if self._cached_location:
            return self._cached_location

        lat = self.default_lat
        lon = self.default_lon
        name = self.location_name

        if self.use_auto:
            try:
                # Attempt lightweight IP-based location lookup
                req = urllib.request.Request(
                    "http://ip-api.com/json/?fields=lat,lon,city,country,status",
                    headers={"User-Agent": "CCTV-Analytics/1.0"}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get("status") == "success":
                        lat = float(data.get("lat", lat))
                        lon = float(data.get("lon", lon))
                        city = data.get("city", "")
                        country = data.get("country", "")
                        name = f"{self.location_name} ({city}, {country})".strip()
                        logger.info(f"Auto-geolocation resolved: {lat}, {lon} ({name})")
            except Exception as e:
                logger.debug(f"Auto-geolocation lookup skipped or failed ({e}), using fixed config coordinates.")

        maps_url = self.format_maps_link(lat, lon)
        self._cached_location = LocationInfo(
            latitude=lat,
            longitude=lon,
            location_name=name,
            maps_url=maps_url
        )
        return self._cached_location

    @staticmethod
    def format_maps_link(lat: float, lon: float) -> str:
        """Formats the official Google Maps query link as specified in the project PDF."""
        return f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"
