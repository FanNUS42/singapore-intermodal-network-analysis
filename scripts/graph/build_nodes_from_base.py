from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from config import CONFIG
from scripts.common.io_utils import (
    get_active_scenario,
    get_scenario_model_paths,
    load_json,
    project_root_from,
    resolve_path,
    save_json,
)


def build_nodes_from_base(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    scenario_name = get_active_scenario(cfg)
    scenario_paths = get_scenario_model_paths(cfg, scenario_name)
    bus_base = load_json(resolve_path(project_root, cfg["paths"]["model"]["base"]["bus_base_json"]))
    mrt_base = load_json(resolve_path(project_root, scenario_paths["mrt_base_json"]))
    terminal_sets = load_json(resolve_path(project_root, scenario_paths["terminal_sets_json"]))
    out_path = resolve_path(project_root, scenario_paths["nodes_json"])

    nodes: List[Dict[str, Any]] = []
    for item in terminal_sets.get("detail", {}).get("source_centroids", []):
        nodes.append({
            "node_id": item["node_id"],
            "node_type": "centroid",
            "mode": None,
            "physical_id": item["node_id"],
            "name": item["node_id"],
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "x_svy": item.get("x_svy"),
            "y_svy": item.get("y_svy"),
            "meta": {
                "grid_id": item.get("grid_id"),
                "row_index": item.get("row_index"),
                "col_index": item.get("col_index"),
            },
        })

    for item in bus_base.get("route_nodes", []):
        nodes.append({
            "node_id": item["node_id"],
            "node_type": "bus_route",
            "mode": "bus",
            "physical_id": item["stop_code"],
            "name": item.get("stop_name"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "x_svy": None,
            "y_svy": None,
            "meta": {
                "route_id": item.get("route_id"),
                "service_no": item.get("service_no"),
                "direction": item.get("direction"),
                "stop_sequence": item.get("stop_sequence"),
            },
        })

    for item in bus_base.get("stop_hubs", []):
        nodes.append({
            "node_id": item["board_node_id"],
            "node_type": "bus_stop_board",
            "mode": "bus",
            "physical_id": item["stop_code"],
            "name": item.get("stop_name"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "x_svy": None,
            "y_svy": None,
            "meta": {
                "stop_id": item.get("hub_id"),
                "stop_code": item.get("stop_code"),
                "paired_alight_node_id": item.get("alight_node_id"),
                "route_node_ids": item.get("route_node_ids", []),
                "service_nos": item.get("service_nos", []),
                "n_connected_routes": item.get("n_connected_routes"),
            },
        })
        nodes.append({
            "node_id": item["alight_node_id"],
            "node_type": "bus_stop_alight",
            "mode": "bus",
            "physical_id": item["stop_code"],
            "name": item.get("stop_name"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "x_svy": None,
            "y_svy": None,
            "meta": {
                "stop_id": item.get("hub_id"),
                "stop_code": item.get("stop_code"),
                "paired_board_node_id": item.get("board_node_id"),
                "route_node_ids": item.get("route_node_ids", []),
                "service_nos": item.get("service_nos", []),
                "n_connected_routes": item.get("n_connected_routes"),
            },
        })

    for item in mrt_base.get("platform_nodes", []):
        nodes.append({
            "node_id": item["node_id"],
            "node_type": "mrt_platform",
            "mode": "mrt",
            "physical_id": item["hub_id"],
            "name": item.get("station_name"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "x_svy": None,
            "y_svy": None,
            "meta": {
                "station_code": item.get("station_code"),
                "line_name": item.get("line_name"),
                "hub_id": item.get("hub_id"),
            },
        })

    for item in mrt_base.get("station_hubs", []):
        nodes.append({
            "node_id": item["hub_id"],
            "node_type": "mrt_station_hub",
            "mode": "mrt",
            "physical_id": item["hub_id"],
            "name": item.get("physical_station_name"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "x_svy": None,
            "y_svy": None,
            "meta": {
                "station_codes": item.get("station_codes", []),
                "service_nos": item.get("service_nos", []),
                "line_names": item.get("line_names", []),
                "is_interchange": item.get("is_interchange", False),
            },
        })

    counts: Dict[str, int] = {}
    for node in nodes:
        counts[node["node_type"]] = counts.get(node["node_type"], 0) + 1

    payload = {
        "meta": {
            "scenario": scenario_name,
            "counts": {
                "nodes_total": len(nodes),
                **counts,
            },
        },
        "nodes": nodes,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build scenario-specific graph nodes from base files")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = dict(CONFIG)
    cfg["_runtime"] = {"active_scenario": args.scenario}
    root = project_root_from(cfg, args.project_root)
    build_nodes_from_base(cfg, root)
