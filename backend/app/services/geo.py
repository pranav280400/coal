"""Geospatial helpers: distance and geofence verification of field reports."""

from __future__ import annotations

import math
from typing import Any

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def point_in_polygon(lat: float, lon: float, ring: list[list[float]]) -> bool:
    """Ray casting on a GeoJSON linear ring ([lon, lat] pairs)."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def verify_location(
    lat: float | None,
    lon: float | None,
    mine_lat: float,
    mine_lon: float,
    boundary: dict[str, Any] | None,
    radius_km: float,
) -> tuple[bool, float | None]:
    """Return (verified, distance_km). Inside the lease polygon, or within radius of the mine centroid."""
    if lat is None or lon is None:
        return False, None
    distance = round(haversine_km(lat, lon, mine_lat, mine_lon), 3)
    if boundary and boundary.get("type") == "Polygon" and boundary.get("coordinates"):
        if point_in_polygon(lat, lon, boundary["coordinates"][0]):
            return True, distance
    return distance <= radius_km, distance
