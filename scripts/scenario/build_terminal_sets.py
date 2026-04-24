from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Set

from config import CONFIG
from scripts.common.io_utils import (
    get_active_scenario,
    get_scenario_model_paths,
    load_json,
    project_root_from,
    resolve_path,
    save_json,
)
from scripts.common.naming import bus_stop_alight_id, mrt_hub_id


def collect_centroids(geojson: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        node_id = str(props.get("grid_id") or props.get("centroid_id") or props.get("fid") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        out.append({
            "node_id": node_id,
            "node_type": "centroid",
            "grid_id": props.get("grid_id"),
            "fid": props.get("fid"),
            "row_index": props.get("row_index"),
            "col_index": props.get("col_index"),
            "x_svy": props.get("x_svy"),
            "y_svy": props.get("y_svy"),
            "lon": props.get("lon"),
            "lat": props.get("lat"),
        })
    return sorted(out, key=lambda x: x["node_id"])


def collect_bus_nodes(geojson: Dict[str, Any], excluded_stop_codes: Set[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        stop_code = str(props.get("BUS_STOP_N") or props.get("BusStopCode") or "").strip()
        if not stop_code or stop_code in excluded_stop_codes:
            continue
        node_id = bus_stop_alight_id(stop_code)
        if node_id in seen:
            continue
        seen.add(node_id)
        out.append({
            "node_id": node_id,
            "node_type": "bus_stop_alight",
            "bus_stop_code": stop_code,
            "name": props.get("LOC_DESC") or props.get("Description"),
        })
    return sorted(out, key=lambda x: x["node_id"])


def collect_mrt_nodes(geojson: Dict[str, Any], station_to_hub: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        station_code = str(props.get("station_code") or "").strip()
        station_name = str(props.get("station_name") or station_code).strip()
        node_id = station_to_hub.get(station_code, mrt_hub_id(station_name))
        if node_id in seen:
            continue
        seen.add(node_id)
        out.append({
            "node_id": node_id,
            "node_type": "mrt_station_hub",
            "station_code": station_code,
            "station_name": station_name,
        })
    return sorted(out, key=lambda x: x["node_id"])


def build_terminal_sets(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    scenario_name = get_active_scenario(cfg)
    scenario_paths = get_scenario_model_paths(cfg, scenario_name)
    raw = cfg["paths"]["raw"]["spatial"]
    out_path = resolve_path(project_root, scenario_paths["terminal_sets_json"])
    mrt_base = load_json(resolve_path(project_root, scenario_paths["mrt_base_json"]))
    station_to_hub = {code: hub["hub_id"] for hub in mrt_base.get("station_hubs", []) for code in hub.get("station_codes", [])}

    centroids = load_json(resolve_path(project_root, raw["centroids_geojson"]))
    cbd_bus = load_json(resolve_path(project_root, raw["cbd_bus_geojson"]))
    cbd_mrt = load_json(resolve_path(project_root, raw["cbd_mrt_geojson"]))
    airport_bus = load_json(resolve_path(project_root, raw["airport_bus_geojson"]))

    excluded_codes = set(str(x) for x in cfg["manual_rules"]["terminal_filters"].get("excluded_under_construction_bus_stop_codes", []))
    source_centroids = collect_centroids(centroids)
    cbd_bus_nodes = collect_bus_nodes(cbd_bus, excluded_codes)
    cbd_mrt_nodes = collect_mrt_nodes(cbd_mrt, station_to_hub)
    airport_bus_nodes = collect_bus_nodes(airport_bus, set())

    airport_code = cfg["params"]["terminals"]["airport_mrt_station_code"]
    airport_name = cfg["params"]["terminals"]["airport_mrt_station_name"]
    airport_mrt_node = {
        "node_id": station_to_hub.get(airport_code, mrt_hub_id(airport_name)),
        "node_type": "mrt_station_hub",
        "station_code": airport_code,
        "station_name": airport_name,
    }

    payload = {
        "meta": {
            "scenario": scenario_name,
            "parameters": {
                "airport_mrt_station_code": airport_code,
                "airport_mrt_station_name": airport_name,
                "excluded_under_construction_bus_stop_codes": sorted(excluded_codes),
            },
            "counts": {
                "source_centroids": len(source_centroids),
                "cbd_bus": len(cbd_bus_nodes),
                "cbd_mrt": len(cbd_mrt_nodes),
                "airport_bus": len(airport_bus_nodes),
                "airport_mrt": 1,
            },
        },
        "sets": {
            "source_centroids": [x["node_id"] for x in source_centroids],
            "cbd_bus": [x["node_id"] for x in cbd_bus_nodes],
            "cbd_mrt": [x["node_id"] for x in cbd_mrt_nodes],
            "airport_bus": [x["node_id"] for x in airport_bus_nodes],
            "airport_mrt": [airport_mrt_node["node_id"]],
        },
        "detail": {
            "source_centroids": source_centroids,
            "cbd_bus": cbd_bus_nodes,
            "cbd_mrt": cbd_mrt_nodes,
            "airport_bus": airport_bus_nodes,
            "airport_mrt": [airport_mrt_node],
        },
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build scenario-specific terminal_sets.json")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = dict(CONFIG)
    cfg["_runtime"] = {"active_scenario": args.scenario}
    root = project_root_from(cfg, args.project_root)
    build_terminal_sets(cfg, root)
