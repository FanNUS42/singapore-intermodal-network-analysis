from __future__ import annotations


def normalize_name(name: str) -> str:
    safe = str(name or "").strip().replace("/", "_").replace("\\", "_")
    return "_".join(safe.split())


def bus_stop_id(stop_code: str) -> str:
    return f"BUSSTOP::{str(stop_code).strip()}"


def bus_hub_id(stop_code: str) -> str:
    return bus_stop_id(stop_code)


def bus_stop_board_id(stop_code: str) -> str:
    return f"BUSSTOP_IN::{str(stop_code).strip()}"


def bus_stop_alight_id(stop_code: str) -> str:
    return f"BUSSTOP_OUT::{str(stop_code).strip()}"


def mrt_hub_id(physical_station_name: str) -> str:
    return f"MRTHUB::{normalize_name(physical_station_name)}"
