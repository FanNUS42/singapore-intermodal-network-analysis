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


def build_links_from_base(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    scenario_name = get_active_scenario(cfg)
    scenario_paths = get_scenario_model_paths(cfg, scenario_name)
    bus_base = load_json(resolve_path(project_root, cfg["paths"]["model"]["base"]["bus_base_json"]))
    mrt_base = load_json(resolve_path(project_root, scenario_paths["mrt_base_json"]))
    intermodal_base = load_json(resolve_path(project_root, scenario_paths["intermodal_base_json"]))
    out_path = resolve_path(project_root, scenario_paths["links_json"])

    bus_board_time = float(cfg["params"]["bus"]["board_time_min"])
    bus_alight_time = float(cfg["params"]["bus"]["alight_time_min"])
    bus_transfer_time = float(cfg["params"]["bus"]["default_transfer_time_min"])
    mrt_split_rule = str(cfg["params"]["graph"].get("mrt_transfer_split_rule", "equal_half"))

    links: List[Dict[str, Any]] = []
    links.extend(bus_base.get("run_links", []))
    links.extend(mrt_base.get("run_links", []))

    stop_hubs = {hub["stop_code"]: hub for hub in bus_base.get("stop_hubs", [])}
    for hub in stop_hubs.values():
        board_node_id = hub["board_node_id"]
        alight_node_id = hub["alight_node_id"]
        for route_node_id in hub.get("route_node_ids", []):
            links.append({
                "link_id": f"BUSBOARD::{board_node_id}->{route_node_id}",
                "from_node": board_node_id,
                "to_node": route_node_id,
                "link_type": "bus_board",
                "mode": "bus",
                "time_min": bus_board_time,
                "distance_m": 0.0,
                "meta": {"stop_id": hub["hub_id"], "stop_code": hub["stop_code"]},
            })
            links.append({
                "link_id": f"BUSALIGHT::{route_node_id}->{alight_node_id}",
                "from_node": route_node_id,
                "to_node": alight_node_id,
                "link_type": "bus_alight",
                "mode": "bus",
                "time_min": bus_alight_time,
                "distance_m": 0.0,
                "meta": {"stop_id": hub["hub_id"], "stop_code": hub["stop_code"]},
            })
        links.append({
            "link_id": f"BUSTRANSFER::{alight_node_id}->{board_node_id}",
            "from_node": alight_node_id,
            "to_node": board_node_id,
            "link_type": "bus_transfer",
            "mode": "bus",
            "time_min": bus_transfer_time,
            "distance_m": 0.0,
            "meta": {"stop_id": hub["hub_id"], "stop_code": hub["stop_code"], "route_count": hub.get("n_connected_routes")},
        })

    station_hubs = {hub["hub_id"]: hub for hub in mrt_base.get("station_hubs", [])}
    for platform in mrt_base.get("platform_nodes", []):
        hub = station_hubs[platform["hub_id"]]
        total = float(hub.get("default_transfer_time_min", 0.0)) if hub.get("is_interchange", False) else 0.0
        edge_time = round(total / 2.0, 3) if mrt_split_rule == "equal_half" else total
        links.append({
            "link_id": f"MRTXFER::{platform['node_id']}->{hub['hub_id']}",
            "from_node": platform["node_id"],
            "to_node": hub["hub_id"],
            "link_type": "mrt_transfer",
            "mode": "mrt",
            "time_min": edge_time,
            "distance_m": 0.0,
        })
        links.append({
            "link_id": f"MRTXFER::{hub['hub_id']}->{platform['node_id']}",
            "from_node": hub["hub_id"],
            "to_node": platform["node_id"],
            "link_type": "mrt_transfer",
            "mode": "mrt",
            "time_min": edge_time,
            "distance_m": 0.0,
        })

    for pair in intermodal_base.get("bus_mrt_walk_pairs", []):
        links.append({
            "link_id": f"IMXFER::{pair['bus_alight_node_id']}->{pair['mrt_hub_id']}",
            "from_node": pair["bus_alight_node_id"],
            "to_node": pair["mrt_hub_id"],
            "link_type": "intermodal_transfer",
            "mode": None,
            "time_min": pair.get("walk_time_min"),
            "distance_m": pair.get("distance_m"),
            "meta": {
                "pair_id": pair.get("pair_id"),
                "bus_stop_code": pair.get("bus_stop_code"),
                "mrt_station_code": pair.get("mrt_station_code"),
                "direction": "bus_to_mrt",
            },
        })
        links.append({
            "link_id": f"IMXFER::{pair['mrt_hub_id']}->{pair['bus_board_node_id']}",
            "from_node": pair["mrt_hub_id"],
            "to_node": pair["bus_board_node_id"],
            "link_type": "intermodal_transfer",
            "mode": None,
            "time_min": pair.get("walk_time_min"),
            "distance_m": pair.get("distance_m"),
            "meta": {
                "pair_id": pair.get("pair_id"),
                "bus_stop_code": pair.get("bus_stop_code"),
                "mrt_station_code": pair.get("mrt_station_code"),
                "direction": "mrt_to_bus",
            },
        })

    for pair in intermodal_base.get("centroid_access_pairs", []):
        links.append({
            "link_id": f"ACCESS::{pair['centroid_id']}->{pair['target_node_id']}",
            "from_node": pair["centroid_id"],
            "to_node": pair["target_node_id"],
            "link_type": "access",
            "mode": None,
            "time_min": pair.get("walk_time_min"),
            "distance_m": pair.get("distance_m"),
            "meta": {
                "pair_id": pair.get("pair_id"),
                "target_mode": pair.get("target_mode"),
                "target_physical_node_id": pair.get("target_physical_node_id"),
                "selected_by": pair.get("selected_by"),
                "selected_by_pre": pair.get("selected_by_pre"),
                "selected_by_post": pair.get("selected_by_post"),
                "source_tag": pair.get("source_tag"),
                "distance_raw_m": pair.get("distance_raw_m"),
            },
        })

    counts: Dict[str, int] = {}
    access_source_tags: Dict[str, int] = {}
    for link in links:
        counts[link["link_type"]] = counts.get(link["link_type"], 0) + 1
        if link["link_type"] == "access":
            tag = str(link.get("meta", {}).get("source_tag", "unknown"))
            access_source_tags[tag] = access_source_tags.get(tag, 0) + 1

    payload = {
        "meta": {
            "scenario": scenario_name,
            "counts": counts,
            "access_source_tags": access_source_tags,
        },
        "links": links,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build scenario-specific graph links from base files")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = dict(CONFIG)
    cfg["_runtime"] = {"active_scenario": args.scenario}
    root = project_root_from(cfg, args.project_root)
    build_links_from_base(cfg, root)
