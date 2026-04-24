from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from config import CONFIG
from scripts.common.io_utils import load_json, project_root_from, resolve_path, save_json
from scripts.common.naming import mrt_hub_id

DEFAULT_NEW_STATIONS: List[Dict[str, Any]] = [
    {"station_code": "CC30", "station_name": "Keppel", "lon": 103.83071819091853, "lat": 1.2689374617139454},
    {"station_code": "CC31", "station_name": "Cantonment", "lon": 103.83706882494067, "lat": 1.273113045942889},
    {"station_code": "CC32", "station_name": "Prince Edward Road", "lon": 103.84739661653211, "lat": 1.2732880758617391},
]

DEFAULT_CLOSING_LINKS: List[Dict[str, Any]] = [
    {"from_node": "CC29", "to_node": "CC30", "time_min": 2.0, "direction": 1},
    {"from_node": "CC30", "to_node": "CC31", "time_min": 2.0, "direction": 1},
    {"from_node": "CC31", "to_node": "CC32", "time_min": 2.0, "direction": 1},
    {"from_node": "CC32", "to_node": "CE2", "time_min": 2.0, "direction": 1},
    {"from_node": "CC30", "to_node": "CC29", "time_min": 2.0, "direction": 2},
    {"from_node": "CC31", "to_node": "CC30", "time_min": 2.0, "direction": 2},
    {"from_node": "CC32", "to_node": "CC31", "time_min": 2.0, "direction": 2},
    {"from_node": "CE2", "to_node": "CC32", "time_min": 2.0, "direction": 2},
]


def _coord_from_feature(feature: Dict[str, Any]) -> Tuple[float | None, float | None]:
    props = feature.get("properties", {})
    lon = props.get("lon")
    lat = props.get("lat")
    if lon is not None and lat is not None:
        return float(lat), float(lon)

    coords = feature.get("geometry", {}).get("coordinates", [])
    if len(coords) >= 2:
        x0 = coords[0]
        y0 = coords[1]
        if isinstance(x0, (int, float)) and isinstance(y0, (int, float)) and abs(x0) <= 180 and abs(y0) <= 90:
            return float(y0), float(x0)
    return None, None


def load_new_stations(path: Path | None = None) -> List[Dict[str, Any]]:
    if path is None or not path.exists():
        return list(DEFAULT_NEW_STATIONS)

    geojson = load_json(path)
    out: List[Dict[str, Any]] = []
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        code = str(props.get("code") or props.get("station_code") or "").strip()
        name = str(props.get("name") or props.get("station_name") or "").strip()
        if not code or not name:
            continue
        lat, lon = _coord_from_feature(feat)
        out.append({"station_code": code, "station_name": name, "lat": lat, "lon": lon})
    return out or list(DEFAULT_NEW_STATIONS)


def load_closing_links(path: Path | None = None) -> List[Dict[str, Any]]:
    if path is None or not path.exists():
        return list(DEFAULT_CLOSING_LINKS)

    rows = load_json(path)
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        from_node = str(row.get("from_node") or "").strip()
        to_node = str(row.get("to_node") or "").strip()
        if not from_node or not to_node:
            continue
        out.append(
            {
                "from_node": from_node,
                "to_node": to_node,
                "time_min": float(row.get("time_min", 2.0)),
                "direction": row.get("direction", 1 if idx < max(len(rows) // 2, 1) else 2),
            }
        )
    return out or list(DEFAULT_CLOSING_LINKS)


def _existing_station_codes(mrt_base: Dict[str, Any]) -> set[str]:
    return {str(x.get("station_code")) for x in mrt_base.get("platform_nodes", []) if x.get("station_code")}


def _platform_lookup(mrt_base: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(x["station_code"]): x for x in mrt_base.get("platform_nodes", []) if x.get("station_code")}


def _existing_link_pairs(mrt_base: Dict[str, Any]) -> set[Tuple[str, str]]:
    return {
        (str(link.get("from_node")), str(link.get("to_node")))
        for link in mrt_base.get("run_links", [])
        if link.get("from_node") is not None and link.get("to_node") is not None
    }


def _append_new_hubs_and_platforms(mrt_base: Dict[str, Any], new_stations: Iterable[Dict[str, Any]]) -> None:
    station_codes = _existing_station_codes(mrt_base)
    hubs = mrt_base.setdefault("station_hubs", [])
    platforms = mrt_base.setdefault("platform_nodes", [])

    for station in new_stations:
        code = str(station["station_code"])
        if code in station_codes:
            continue
        hub_id = mrt_hub_id(str(station["station_name"]))
        hubs.append(
            {
                "hub_id": hub_id,
                "physical_station_name": station["station_name"],
                "station_codes": [code],
                "primary_station_code": code,
                "service_nos": ["CCL"],
                "line_names": ["Circle Line"],
                "is_interchange": False,
                "n_connected_lines": 1,
                "n_station_codes": 1,
                "n_service_nos": 1,
                "default_transfer_time_min": 0.0,
                "lat": station.get("lat"),
                "lon": station.get("lon"),
            }
        )
        platforms.append(
            {
                "node_id": code,
                "station_code": code,
                "station_name": station["station_name"],
                "line_name": "Circle Line",
                "hub_id": hub_id,
                "lat": station.get("lat"),
                "lon": station.get("lon"),
            }
        )
        station_codes.add(code)


def _append_closing_run_links(mrt_base: Dict[str, Any], closing_links: Iterable[Dict[str, Any]]) -> None:
    platform_by_code = _platform_lookup(mrt_base)
    existing_pairs = _existing_link_pairs(mrt_base)
    run_links = mrt_base.setdefault("run_links", [])

    for row in closing_links:
        from_code = str(row["from_node"])
        to_code = str(row["to_node"])
        if (from_code, to_code) in existing_pairs:
            continue
        if from_code not in platform_by_code or to_code not in platform_by_code:
            raise ValueError(f"Missing platform node for closing link {from_code}->{to_code}")
        from_station = platform_by_code[from_code]
        to_station = platform_by_code[to_code]
        run_links.append(
            {
                "link_id": f"MRTRUN::{from_code}->{to_code}",
                "from_node": from_code,
                "to_node": to_code,
                "link_type": "mrt_run",
                "mode": "mrt",
                "time_min": float(row.get("time_min", 2.0)),
                "time_source": "cc_ring_overlay",
                "route_id": "CCL_RING",
                "service_no": "CCL",
                "line_name": "Circle Line",
                "direction": row.get("direction"),
                "from_station_name": from_station.get("station_name"),
                "to_station_name": to_station.get("station_name"),
                "source": "cc_ring_overlay",
            }
        )
        existing_pairs.add((from_code, to_code))


def apply_cc_ring_overlay_to_payload(mrt_base: Dict[str, Any], new_stations: List[Dict[str, Any]], closing_links: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = copy.deepcopy(mrt_base)
    _append_new_hubs_and_platforms(payload, new_stations)
    _append_closing_run_links(payload, closing_links)
    payload["platform_nodes"] = sorted(payload.get("platform_nodes", []), key=lambda x: str(x.get("station_code", "")))
    payload["station_hubs"] = sorted(payload.get("station_hubs", []), key=lambda x: str(x.get("hub_id", "")))
    payload["run_links"] = sorted(payload.get("run_links", []), key=lambda x: (str(x.get("from_node", "")), str(x.get("to_node", "")), str(x.get("link_id", ""))))
    return payload


def annotate_cc_ring_meta(
    mrt_base: Dict[str, Any],
    new_station_path: str | None,
    closing_link_path: str | None,
    new_stations: List[Dict[str, Any]] | None = None,
    closing_links: List[Dict[str, Any]] | None = None,
    scenario_name: str = "post_ring",
) -> Dict[str, Any]:
    payload = copy.deepcopy(mrt_base)
    meta = payload.setdefault("meta", {})
    source_files = meta.setdefault("source_files", {})
    if new_station_path is not None:
        source_files["cc_ring_new_stations_geojson"] = new_station_path
    if closing_link_path is not None:
        source_files["cc_ring_links_json"] = closing_link_path
    meta["scenario"] = {"scenario_name": scenario_name, "mrt_strategy": "cc_ring_overlay"}
    meta["cc_ring_overlay"] = {
        "new_platform_station_codes": [str(row["station_code"]) for row in (new_stations or DEFAULT_NEW_STATIONS)],
        "closing_pairs": [f"{row['from_node']}->{row['to_node']}" for row in (closing_links or DEFAULT_CLOSING_LINKS)],
    }
    meta["counts"] = {
        "platform_nodes": len(payload.get("platform_nodes", [])),
        "station_hubs": len(payload.get("station_hubs", [])),
        "run_links": len(payload.get("run_links", [])),
    }
    return payload


def apply_cc_ring_overlay(base_input_path: Path, output_path: Path, new_station_path: Path | None = None, closing_link_path: Path | None = None, scenario_name: str = "post_ring") -> Dict[str, Any]:
    base_payload = load_json(base_input_path)
    new_stations = load_new_stations(new_station_path)
    closing_links = load_closing_links(closing_link_path)
    payload = apply_cc_ring_overlay_to_payload(base_payload, new_stations, closing_links)
    payload = annotate_cc_ring_meta(payload, str(new_station_path) if new_station_path is not None else None, str(closing_link_path) if closing_link_path is not None else None, new_stations=new_stations, closing_links=closing_links, scenario_name=scenario_name)
    save_json(output_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply CC ring overlay onto an MRT base JSON")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--base-input", type=str, default="model/base/mrt_base.json")
    parser.add_argument("--output", type=str, default="model/scenario/post_ring/mrt_base.json")
    parser.add_argument("--stations", type=str, default="raw/scenario/New_MRT_stations.geojson")
    parser.add_argument("--links", type=str, default="raw/scenario/cc_ring_links.json")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    root = project_root_from(CONFIG, args.project_root)
    apply_cc_ring_overlay(base_input_path=resolve_path(root, args.base_input), output_path=resolve_path(root, args.output), new_station_path=resolve_path(root, args.stations), closing_link_path=resolve_path(root, args.links))
