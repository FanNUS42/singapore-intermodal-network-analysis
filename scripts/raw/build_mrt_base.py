from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import CONFIG
from scripts.common.io_utils import load_json, project_root_from, resolve_path, save_json
from scripts.common.naming import mrt_hub_id


def split_codes(raw: Any) -> List[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in str(raw).replace("|", ";").split(";") if x.strip()]


def station_point_lookup(station_points_geojson: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    by_code: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for feat in station_points_geojson.get("features", []):
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        lon = coords[0] if len(coords) >= 2 else None
        lat = coords[1] if len(coords) >= 2 else None
        name = str(props.get("station_name") or "").strip()
        for code in split_codes(props.get("all_codes") or props.get("station_codes") or props.get("station_code")):
            by_code[code] = {"lat": lat, "lon": lon, "station_name": name}
        if name:
            by_name[name] = {"lat": lat, "lon": lon, "station_name": name}
    return {"by_code": by_code, "by_name": by_name}


def build_pair_lookup(route_topology: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for route_id, route in route_topology.items():
        cols = route["stops_columns"]
        idx = {c: i for i, c in enumerate(cols)}
        for a, b in zip(route["stops_matrix"][:-1], route["stops_matrix"][1:]):
            from_code = str(a[idx["station_code"]])
            to_code = str(b[idx["station_code"]])
            lookup[(from_code, to_code)] = {
                "route_id": route_id,
                "service_no": route.get("service_no"),
                "line_name": route.get("line_name"),
                "direction": route.get("direction"),
                "from_station_name": a[idx["station_name"]],
                "to_station_name": b[idx["station_name"]],
            }
    return lookup


def build_mrt_base(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    raw = cfg["paths"]["raw"]["mrt"]
    out_path = resolve_path(project_root, cfg["paths"]["model"]["base"]["mrt_base_json"])

    route_topology = load_json(resolve_path(project_root, raw["route_topology_json"]))
    transfer_stations = load_json(resolve_path(project_root, raw["transfer_stations_json"]))
    raw_links = load_json(resolve_path(project_root, raw["links_json"]))
    station_points = load_json(resolve_path(project_root, raw["station_points_geojson"]))
    point_lookup = station_point_lookup(station_points)
    pair_lookup = build_pair_lookup(route_topology)

    fallback_cfg = cfg["manual_rules"]["fallbacks"]["mrt"]
    default_transfer_time = float(cfg["params"]["mrt"]["default_transfer_time_min"])

    station_to_hub: Dict[str, str] = {}
    hubs: Dict[str, Dict[str, Any]] = {}

    for station in transfer_stations.get("stations", []):
        physical_name = station["physical_station_name"]
        codes = list(station.get("station_codes", []))
        hub_id = mrt_hub_id(physical_name)
        sample_coord = None
        for code in codes:
            sample_coord = point_lookup["by_code"].get(code)
            if sample_coord:
                break
        if sample_coord is None:
            sample_coord = point_lookup["by_name"].get(physical_name, {})
        n_connected_lines = station.get("n_connected_lines")
        n_station_codes = station.get("n_station_codes", len(codes))
        n_service_nos = station.get("n_service_nos", len(set(station.get("service_nos", []))))
        is_interchange = bool((n_connected_lines or 0) > 1 or n_station_codes > 1 or n_service_nos > 1)
        hubs[hub_id] = {
            "hub_id": hub_id,
            "physical_station_name": physical_name,
            "station_codes": codes,
            "primary_station_code": station.get("primary_station_code") or (codes[0] if codes else None),
            "service_nos": station.get("service_nos", []),
            "line_names": station.get("line_names", []),
            "is_interchange": is_interchange,
            "n_connected_lines": n_connected_lines if n_connected_lines is not None else len(station.get("line_names", [])),
            "n_station_codes": n_station_codes,
            "n_service_nos": n_service_nos,
            "default_transfer_time_min": float(station.get("default_transfer_time_min", default_transfer_time)),
            "lat": sample_coord.get("lat") if isinstance(sample_coord, dict) else None,
            "lon": sample_coord.get("lon") if isinstance(sample_coord, dict) else None,
        }
        for code in codes:
            station_to_hub[code] = hub_id

    platform_nodes: List[Dict[str, Any]] = []
    seen_codes = set()
    for route_id, route in route_topology.items():
        line_name = route.get("line_name") or route.get("service_no") or route_id
        cols = route["stops_columns"]
        cidx = {c: i for i, c in enumerate(cols)}
        for row in route["stops_matrix"]:
            code = str(row[cidx["station_code"]])
            name = row[cidx["station_name"]]
            if code not in station_to_hub and bool(fallback_cfg.get("auto_create_missing_hub", True)):
                hub_id = mrt_hub_id(name)
                station_to_hub[code] = hub_id
                if hub_id not in hubs:
                    coord = point_lookup["by_code"].get(code) or point_lookup["by_name"].get(name, {})
                    hubs[hub_id] = {
                        "hub_id": hub_id,
                        "physical_station_name": name,
                        "station_codes": [code],
                        "primary_station_code": code,
                        "service_nos": [route.get("service_no")] if route.get("service_no") else [],
                        "line_names": [line_name],
                        "is_interchange": bool(fallback_cfg.get("missing_hub_is_interchange", False)),
                        "n_connected_lines": 1,
                        "n_station_codes": 1,
                        "n_service_nos": 1 if route.get("service_no") else 0,
                        "default_transfer_time_min": float(fallback_cfg.get("missing_hub_transfer_time_min", 0.0)),
                        "lat": coord.get("lat") if isinstance(coord, dict) else None,
                        "lon": coord.get("lon") if isinstance(coord, dict) else None,
                    }
            if code in seen_codes:
                continue
            seen_codes.add(code)
            coord = point_lookup["by_code"].get(code) or point_lookup["by_name"].get(name, {})
            platform_nodes.append(
                {
                    "node_id": code,
                    "station_code": code,
                    "station_name": name,
                    "line_name": line_name,
                    "hub_id": station_to_hub[code],
                    "lat": coord.get("lat") if isinstance(coord, dict) else None,
                    "lon": coord.get("lon") if isinstance(coord, dict) else None,
                }
            )

    run_links: List[Dict[str, Any]] = []
    for row in raw_links:
        meta = pair_lookup.get((str(row["from_node"]), str(row["to_node"])), {})
        run_links.append(
            {
                "link_id": row.get("link_id") or f"MRTRUN::{row['from_node']}->{row['to_node']}",
                "from_node": row["from_node"],
                "to_node": row["to_node"],
                "link_type": "mrt_run",
                "mode": "mrt",
                "time_min": float(row["time_min"]) if row.get("time_min") not in (None, "") else None,
                "time_source": row.get("time_source", "raw_mrt_links"),
                "route_id": row.get("route_id") or meta.get("route_id"),
                "service_no": row.get("service_no") or meta.get("service_no"),
                "line_name": row.get("line_name") or meta.get("line_name"),
                "direction": row.get("direction") if row.get("direction") is not None else meta.get("direction"),
                "from_station_name": row.get("from_station_name") or meta.get("from_station_name"),
                "to_station_name": row.get("to_station_name") or meta.get("to_station_name"),
                "source": row.get("source", "raw_mrt_links"),
            }
        )

    payload = {
        "meta": {
            "source_files": {
                "route_topology_json": raw["route_topology_json"],
                "transfer_stations_json": raw["transfer_stations_json"],
                "links_json": raw["links_json"],
                "station_points_geojson": raw["station_points_geojson"],
            },
            "counts": {
                "platform_nodes": len(platform_nodes),
                "station_hubs": len(hubs),
                "run_links": len(run_links),
            },
        },
        "platform_nodes": sorted(platform_nodes, key=lambda x: x["station_code"]),
        "station_hubs": sorted(hubs.values(), key=lambda x: x["hub_id"]),
        "run_links": run_links,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build model/base/mrt_base.json")
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    root = project_root_from(CONFIG, args.project_root)
    build_mrt_base(CONFIG, root)
