from __future__ import annotations

import argparse
import heapq
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


def build_graph(links_payload: Dict[str, Any]) -> Dict[str, List[Tuple[str, float, str]]]:
    graph: Dict[str, List[Tuple[str, float, str]]] = {}
    for link in links_payload.get("links", []):
        u = str(link["from_node"])
        v = str(link["to_node"])
        t = link.get("time_min")
        if t in (None, ""):
            continue
        try:
            w = float(t)
        except (TypeError, ValueError):
            continue
        graph.setdefault(u, []).append((v, w, str(link.get("link_id") or "")))
    return graph


def build_reverse_graph(links_payload: Dict[str, Any]) -> Dict[str, List[Tuple[str, float, str]]]:
    reverse_graph: Dict[str, List[Tuple[str, float, str]]] = {}
    for link in links_payload.get("links", []):
        u = str(link["from_node"])
        v = str(link["to_node"])
        t = link.get("time_min")
        if t in (None, ""):
            continue
        try:
            w = float(t)
        except (TypeError, ValueError):
            continue
        reverse_graph.setdefault(v, []).append((u, w, str(link.get("link_id") or "")))
    return reverse_graph


def build_link_lookup(links_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(link.get("link_id") or ""): link for link in links_payload.get("links", []) if link.get("link_id")}


def dijkstra_to_sink(
    reverse_graph: Dict[str, List[Tuple[str, float, str]]],
    sink: str,
    sources: set[str] | None = None,
) -> Tuple[Dict[str, float], Dict[str, Tuple[str, str]]]:
    dist: Dict[str, float] = {sink: 0.0}
    next_step: Dict[str, Tuple[str, str]] = {}
    pq: List[Tuple[float, str]] = [(0.0, sink)]
    settled_sources: set[str] = set()
    while pq:
        cur_dist, node = heapq.heappop(pq)
        if cur_dist > dist.get(node, float("inf")):
            continue
        if sources is not None and node in sources:
            settled_sources.add(node)
            if len(settled_sources) >= len(sources):
                break
        for pred, weight, link_id in reverse_graph.get(node, []):
            nd = cur_dist + weight
            if nd < dist.get(pred, float("inf")):
                dist[pred] = nd
                next_step[pred] = (node, link_id)
                heapq.heappush(pq, (nd, pred))
    return dist, next_step


def reconstruct_path_to_sink(next_step: Dict[str, Tuple[str, str]], source: str, sink: str) -> Tuple[List[str], List[str]]:
    if source == sink:
        return [source], []
    if source not in next_step:
        return [], []
    nodes = [source]
    links: List[str] = []
    cur = source
    seen = {source}
    while cur != sink:
        if cur not in next_step:
            return [], []
        nxt, link_id = next_step[cur]
        if nxt in seen and nxt != sink:
            return [], []
        links.append(link_id)
        nodes.append(nxt)
        cur = nxt
        seen.add(cur)
    return nodes, links


def build_name_lookup(nodes_payload: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for node in nodes_payload.get("nodes", []):
        node_id = str(node["node_id"])
        out[node_id] = str(node.get("name") or node_id)
    return out


def collect_sources_and_sinks(terminal_sets: Dict[str, Any]) -> Tuple[List[str], List[Tuple[str, str]]]:
    sources = [str(x["node_id"]) for x in terminal_sets.get("detail", {}).get("source_centroids", [])]
    sinks: List[Tuple[str, str]] = []
    for sink_set, node_ids in terminal_sets.get("sets", {}).items():
        if sink_set == "source_centroids":
            continue
        for node_id in node_ids:
            sinks.append((sink_set, str(node_id)))
    return sources, sinks


def build_path_segments(path_link_ids: List[str], link_lookup: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    cumulative_time = 0.0
    for seq, link_id in enumerate(path_link_ids, start=1):
        link = link_lookup.get(link_id, {})
        time_min = link.get("time_min")
        try:
            time_val = float(time_min)
        except (TypeError, ValueError):
            time_val = None
        if time_val is not None:
            cumulative_time += time_val
        segments.append({
            "seq": seq,
            "link_id": link_id,
            "from_node": link.get("from_node"),
            "to_node": link.get("to_node"),
            "link_type": link.get("link_type"),
            "mode": link.get("mode"),
            "time_min": round(time_val, 3) if time_val is not None else None,
            "distance_m": link.get("distance_m"),
            "cumulative_time_min": round(cumulative_time, 3) if time_val is not None else None,
        })
    return segments


def build_time_breakdown(path_segments: List[Dict[str, Any]]) -> Dict[str, float]:
    breakdown: Dict[str, float] = {}
    for seg in path_segments:
        key = str(seg.get("link_type") or "unknown")
        time_min = seg.get("time_min")
        if time_min is None:
            continue
        breakdown[key] = round(breakdown.get(key, 0.0) + float(time_min), 3)
    return breakdown


def build_od_shortest_paths(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    scenario_name = get_active_scenario(cfg)
    model_paths = get_scenario_model_paths(cfg, scenario_name)
    analysis_paths = get_scenario_analysis_paths(cfg, scenario_name)
    nodes_path = resolve_path(project_root, model_paths["nodes_json"])
    links_path = resolve_path(project_root, model_paths["links_json"])
    terminals_path = resolve_path(project_root, model_paths["terminal_sets_json"])
    out_path = resolve_path(project_root, analysis_paths["od_shortest_paths_json"])
    nodes_payload = load_json(nodes_path)
    links_payload = load_json(links_path)
    terminal_sets = load_json(terminals_path)
    name_lookup = build_name_lookup(nodes_payload)
    link_lookup = build_link_lookup(links_payload)
    reverse_graph = build_reverse_graph(links_payload)
    sources, sinks = collect_sources_and_sinks(terminal_sets)
    emit_path_segments = bool(cfg["params"].get("analysis", {}).get("emit_path_segments", True))

    source_ids = set(sources)
    sink_results: Dict[str, Tuple[Dict[str, float], Dict[str, Tuple[str, str]]]] = {}
    for _, sink_id in sinks:
        if sink_id not in sink_results:
            sink_results[sink_id] = dijkstra_to_sink(reverse_graph, sink_id, source_ids)

    records: List[Dict[str, Any]] = []
    for source_id in sources:
        for sink_set, sink_id in sinks:
            dist_to_sink, next_step = sink_results[sink_id]
            reachable = source_id in dist_to_sink
            if reachable:
                path_node_ids, path_link_ids = reconstruct_path_to_sink(next_step, source_id, sink_id)
            else:
                path_node_ids, path_link_ids = [], []
            path_segments = build_path_segments(path_link_ids, link_lookup) if reachable and emit_path_segments else []
            path_time_breakdown = build_time_breakdown(path_segments) if path_segments else {}
            record = {
                "source_id": source_id,
                "source_name": name_lookup.get(source_id, source_id),
                "sink_set": sink_set,
                "sink_id": sink_id,
                "sink_name": name_lookup.get(sink_id, sink_id),
                "reachable": reachable,
                "time_min": round(dist_to_sink[source_id], 3) if reachable else None,
                "n_hops": len(path_link_ids),
                "path_node_ids": path_node_ids,
                "path_link_ids": path_link_ids,
            }
            if emit_path_segments:
                record["path_segments"] = path_segments
                record["path_time_breakdown"] = path_time_breakdown
            records.append(record)

    payload = {
        "meta": {
            "scenario": scenario_name,
            "description": "All centroid x terminal shortest paths",
            "source_count": len(sources),
            "sink_count": len(sinks),
            "record_count": len(records),
            "paths": {
                "nodes_json": model_paths["nodes_json"],
                "links_json": model_paths["links_json"],
                "terminal_sets_json": model_paths["terminal_sets_json"],
            },
            "notes": [
                "Centroids are source nodes only",
                "path_segments expands each chosen link with time and cumulative time",
            ],
        },
        "records": records,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build scenario-specific centroid x terminal shortest paths JSON")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = dict(CONFIG)
    cfg["_runtime"] = {"active_scenario": args.scenario}
    root = project_root_from(cfg, args.project_root)
    build_od_shortest_paths(cfg, root)
