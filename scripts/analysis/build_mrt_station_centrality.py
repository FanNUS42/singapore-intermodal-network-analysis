from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import networkx as nx

from config import CONFIG
from scripts.common.io_utils import (
    get_active_scenario,
    get_scenario_analysis_paths,
    get_scenario_model_paths,
    load_json,
    project_root_from,
    resolve_path,
    save_json,
)


def _station_hub_lookup(mrt_base: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(hub["hub_id"]): hub for hub in mrt_base.get("station_hubs", []) if hub.get("hub_id")}


def _platform_to_station_lookup(mrt_base: Dict[str, Any]) -> Dict[str, str]:
    hubs = _station_hub_lookup(mrt_base)
    out: Dict[str, str] = {}
    for platform in mrt_base.get("platform_nodes", []):
        node_id = str(platform.get("node_id") or "")
        hub_id = str(platform.get("hub_id") or "")
        if not node_id or hub_id not in hubs:
            continue
        out[node_id] = str(hubs[hub_id].get("primary_station_code") or node_id)
    return out


def _station_node_records(mrt_base: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for hub in mrt_base.get("station_hubs", []):
        station_id = str(hub.get("primary_station_code") or hub.get("hub_id") or "")
        if not station_id:
            continue
        rows.append(
            {
                "station_id": station_id,
                "station_name": hub.get("physical_station_name"),
                "hub_id": hub.get("hub_id"),
                "station_codes": list(hub.get("station_codes", [])),
                "line_names": list(hub.get("line_names", [])),
                "service_nos": list(hub.get("service_nos", [])),
                "is_interchange": bool(hub.get("is_interchange", False)),
                "lat": hub.get("lat"),
                "lon": hub.get("lon"),
            }
        )
    rows.sort(key=lambda r: r["station_id"])
    return rows


def _collapsed_edge_rows(mrt_base: Dict[str, Any]) -> List[Dict[str, Any]]:
    platform_to_station = _platform_to_station_lookup(mrt_base)
    edge_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for link in mrt_base.get("run_links", []):
        if str(link.get("link_type") or "") != "mrt_run":
            continue
        from_platform = str(link.get("from_node") or "")
        to_platform = str(link.get("to_node") or "")
        from_station = platform_to_station.get(from_platform)
        to_station = platform_to_station.get(to_platform)
        if not from_station or not to_station or from_station == to_station:
            continue
        try:
            time_min = float(link.get("time_min"))
        except (TypeError, ValueError):
            continue
        key = (from_station, to_station)
        current = edge_map.get(key)
        candidate = {
            "from_station_id": from_station,
            "to_station_id": to_station,
            "time_min": round(time_min, 3),
            "from_platform": from_platform,
            "to_platform": to_platform,
            "line_name": link.get("line_name"),
            "service_no": link.get("service_no"),
            "route_id": link.get("route_id"),
            "source_link_id": link.get("link_id"),
        }
        if current is None or float(candidate["time_min"]) < float(current["time_min"]):
            edge_map[key] = candidate

    rows = list(edge_map.values())
    rows.sort(key=lambda r: (r["from_station_id"], r["to_station_id"]))
    return rows


def _build_station_graph(station_rows: Iterable[Dict[str, Any]], edge_rows: Iterable[Dict[str, Any]]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for row in station_rows:
        graph.add_node(
            str(row["station_id"]),
            station_name=row.get("station_name"),
            is_interchange=row.get("is_interchange", False),
            lat=row.get("lat"),
            lon=row.get("lon"),
            station_codes=row.get("station_codes", []),
            line_names=row.get("line_names", []),
            service_nos=row.get("service_nos", []),
            hub_id=row.get("hub_id"),
        )
    for row in edge_rows:
        graph.add_edge(
            str(row["from_station_id"]),
            str(row["to_station_id"]),
            time_min=float(row["time_min"]),
            from_platform=row.get("from_platform"),
            to_platform=row.get("to_platform"),
            line_name=row.get("line_name"),
            service_no=row.get("service_no"),
            route_id=row.get("route_id"),
            source_link_id=row.get("source_link_id"),
        )
    return graph


def _outward_closeness(graph: nx.DiGraph) -> Dict[str, float]:
    return nx.closeness_centrality(graph.reverse(copy=False), distance="time_min", wf_improved=True)


def _round_metric_map(metric_map: Dict[str, float]) -> Dict[str, float]:
    return {str(k): round(float(v), 8) for k, v in metric_map.items()}


def build_mrt_station_centrality(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    scenario_name = get_active_scenario(cfg)
    model_paths = get_scenario_model_paths(cfg, scenario_name)
    analysis_paths = get_scenario_analysis_paths(cfg, scenario_name)
    mrt_path = resolve_path(project_root, model_paths["mrt_base_json"])
    out_path = resolve_path(project_root, analysis_paths["mrt_station_centrality_json"])

    mrt_base = load_json(mrt_path)
    station_rows = _station_node_records(mrt_base)
    edge_rows = _collapsed_edge_rows(mrt_base)
    graph = _build_station_graph(station_rows, edge_rows)

    betweenness = _round_metric_map(nx.betweenness_centrality(graph, weight="time_min", normalized=True))
    closeness = _round_metric_map(_outward_closeness(graph))

    records: List[Dict[str, Any]] = []
    for row in station_rows:
        station_id = str(row["station_id"])
        records.append(
            {
                **row,
                "betweenness": betweenness.get(station_id, 0.0),
                "closeness": closeness.get(station_id, 0.0),
                "out_degree": int(graph.out_degree(station_id)),
                "in_degree": int(graph.in_degree(station_id)),
            }
        )

    payload = {
        "meta": {
            "scenario": scenario_name,
            "input_mrt_base_json": model_paths["mrt_base_json"],
            "network_definition": {
                "node_unit": "physical_mrt_station",
                "edge_unit": "collapsed_adjacent_station_run_link",
                "graph_type": "directed",
                "weight": "time_min",
                "parallel_edge_rule": "keep_min_time_per_ordered_station_pair",
                "transfer_model": "interchange penalties are omitted in this simplified physical-station graph",
                "closeness_definition": "outward closeness on directed graph using weighted shortest-path distance",
                "betweenness_definition": "weighted node betweenness on directed graph using time_min",
            },
            "counts": {
                "station_nodes": graph.number_of_nodes(),
                "station_edges": graph.number_of_edges(),
            },
        },
        "station_edges": edge_rows,
        "records": records,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MRT physical-station centrality results for one scenario")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = dict(CONFIG)
    cfg["_runtime"] = {"active_scenario": args.scenario}
    root = project_root_from(cfg, args.project_root)
    build_mrt_station_centrality(cfg, root)
