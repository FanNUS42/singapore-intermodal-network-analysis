from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from config import CONFIG
from scripts.common.io_utils import load_json, project_root_from, resolve_path, save_json
from scripts.common.naming import bus_hub_id, bus_stop_alight_id, bus_stop_board_id


def infer_time_min(distance_km: float | None, speed_kmph: float) -> float | None:
    if distance_km is None:
        return None
    return round(distance_km / speed_kmph * 60.0, 3)


def build_bus_base(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    paths = cfg["paths"]
    bus_route_path = resolve_path(project_root, paths["raw"]["bus"]["bus_route_json"])
    out_path = resolve_path(project_root, paths["model"]["base"]["bus_base_json"])
    bus_speed_kmph = float(cfg["params"]["graph"]["bus_speed_kmph"])

    data = load_json(bus_route_path)
    route_nodes: List[Dict[str, Any]] = []
    stop_membership: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    run_links: List[Dict[str, Any]] = []

    for route_id, route in data.items():
        service_no = route.get("service_no")
        direction = route.get("direction")
        stops = route.get("stops_matrix", [])
        for stop_sequence, stop_code, stop_name, lat, lon, cum_distance_km in stops:
            node_id = f"{route_id}::#{stop_sequence}::{stop_code}"
            route_nodes.append(
                {
                    "node_id": node_id,
                    "route_id": route_id,
                    "service_no": service_no,
                    "direction": direction,
                    "stop_sequence": stop_sequence,
                    "stop_code": stop_code,
                    "stop_name": stop_name,
                    "lat": lat,
                    "lon": lon,
                    "cum_distance_km": cum_distance_km,
                }
            )
            stop_membership[str(stop_code)].append(
                {
                    "route_node_id": node_id,
                    "route_id": route_id,
                    "service_no": service_no,
                    "stop_name": stop_name,
                    "lat": lat,
                    "lon": lon,
                }
            )

        for a, b in zip(stops[:-1], stops[1:]):
            a_seq, a_code, a_name, _, _, a_cum = a
            b_seq, b_code, b_name, _, _, b_cum = b
            from_node = f"{route_id}::#{a_seq}::{a_code}"
            to_node = f"{route_id}::#{b_seq}::{b_code}"
            distance_km = round(float(b_cum) - float(a_cum), 3) if a_cum is not None and b_cum is not None else None
            run_links.append(
                {
                    "link_id": f"BUSRUN::{from_node}->{to_node}",
                    "from_node": from_node,
                    "to_node": to_node,
                    "link_type": "bus_run",
                    "mode": "bus",
                    "time_min": infer_time_min(distance_km, bus_speed_kmph),
                    "distance_m": round(distance_km * 1000.0, 3) if distance_km is not None else None,
                    "distance_km": distance_km,
                    "route_id": route_id,
                    "service_no": service_no,
                    "from_stop_code": a_code,
                    "to_stop_code": b_code,
                    "from_stop_name": a_name,
                    "to_stop_name": b_name,
                    "source": "raw_bus_route_plus_bus_speed",
                }
            )

    stop_hubs: List[Dict[str, Any]] = []
    for stop_code, members in sorted(stop_membership.items()):
        sample = members[0]
        stop_hubs.append(
            {
                "hub_id": bus_hub_id(stop_code),
                "board_node_id": bus_stop_board_id(stop_code),
                "alight_node_id": bus_stop_alight_id(stop_code),
                "stop_code": stop_code,
                "stop_name": sample.get("stop_name"),
                "lat": sample.get("lat"),
                "lon": sample.get("lon"),
                "route_node_ids": sorted({m["route_node_id"] for m in members}),
                "route_ids": sorted({str(m["route_id"]) for m in members if m.get("route_id") not in (None, "")}),
                "service_nos": sorted({str(m["service_no"]) for m in members if m.get("service_no") not in (None, "")}),
                "n_connected_routes": len({m["route_id"] for m in members if m.get("route_id") not in (None, "")}),
            }
        )

    payload = {
        "meta": {
            "source_files": {
                "bus_route_json": paths["raw"]["bus"]["bus_route_json"],
            },
            "parameters": {
                "bus_speed_kmph": bus_speed_kmph,
            },
            "counts": {
                "route_nodes": len(route_nodes),
                "stop_hubs": len(stop_hubs),
                "run_links": len(run_links),
            },
        },
        "route_nodes": route_nodes,
        "stop_hubs": stop_hubs,
        "run_links": run_links,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build model/base/bus_base.json")
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    root = project_root_from(CONFIG, args.project_root)
    build_bus_base(CONFIG, root)
