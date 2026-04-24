from __future__ import annotations

import argparse
import heapq
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import CONFIG

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = "G_000_003"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def node_name_map(nodes_payload: Dict[str, Any]) -> Dict[str, str]:
    return {
        str(node["node_id"]): str(node.get("name") or node["node_id"])
        for node in nodes_payload.get("nodes", [])
    }


def build_graph(links_payload: Dict[str, Any]) -> Dict[str, List[Tuple[str, float, str]]]:
    graph: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
    for link in links_payload.get("links", []):
        u = str(link["from_node"])
        v = str(link["to_node"])
        w = link.get("time_min")
        if w is None:
            continue
        try:
            weight = float(w)
        except (TypeError, ValueError):
            continue
        graph[u].append((v, weight, str(link.get("link_type") or "")))
    return graph


def dijkstra(
    graph: Dict[str, List[Tuple[str, float, str]]],
    source: str,
) -> Tuple[Dict[str, float], Dict[str, Tuple[str, str]]]:
    dist: Dict[str, float] = {source: 0.0}
    prev: Dict[str, Tuple[str, str]] = {}
    pq: List[Tuple[float, str]] = [(0.0, source)]

    while pq:
        cur_dist, u = heapq.heappop(pq)
        if cur_dist > dist.get(u, float("inf")):
            continue
        for v, weight, link_type in graph.get(u, []):
            nd = cur_dist + weight
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, link_type)
                heapq.heappush(pq, (nd, v))
    return dist, prev


def reconstruct_path(
    prev: Dict[str, Tuple[str, str]],
    source: str,
    target: str,
) -> Tuple[List[str], List[str]]:
    if source == target:
        return [source], []
    if target not in prev:
        return [], []

    nodes_rev = [target]
    link_types_rev: List[str] = []
    cur = target
    while cur != source:
        p, lt = prev[cur]
        nodes_rev.append(p)
        link_types_rev.append(lt)
        cur = p

    nodes = list(reversed(nodes_rev))
    link_types = list(reversed(link_types_rev))
    return nodes, link_types


def format_path(nodes: List[str], names: Dict[str, str], link_types: List[str]) -> str:
    if not nodes:
        return "(unreachable)"
    parts: List[str] = []
    for i, node in enumerate(nodes):
        parts.append(f"{node}({names.get(node, node)})")
        if i < len(link_types):
            parts.append(f"--[{link_types[i]}]-->")
    return " ".join(parts)


def flatten_destinations(terminal_sets: Dict[str, Any]) -> List[Tuple[str, str]]:
    dests: List[Tuple[str, str]] = []
    sets = terminal_sets.get("sets", {})
    for set_name, node_ids in sets.items():
        if set_name == "source_centroids":
            continue
        for node_id in node_ids:
            dests.append((set_name, str(node_id)))
    return dests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate shortest paths for one scenario")
    parser.add_argument("--scenario", choices=list(CONFIG["scenario_order"]), default="pre_ring")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenario_paths = CONFIG["paths"]["model"]["scenario"][args.scenario]
    nodes_path = PROJECT_ROOT / scenario_paths["nodes_json"]
    links_path = PROJECT_ROOT / scenario_paths["links_json"]
    terminals_path = PROJECT_ROOT / scenario_paths["terminal_sets_json"]
    log_path = PROJECT_ROOT / "log" / f"validate_shortest_paths_{args.scenario}_{args.source}.txt"

    nodes_payload = load_json(nodes_path)
    links_payload = load_json(links_path)
    terminal_sets = load_json(terminals_path)

    names = node_name_map(nodes_payload)
    graph = build_graph(links_payload)

    source = args.source
    if source not in names and source not in graph:
        raise ValueError(f"Source node {source!r} not found in nodes/graph.")

    dests = flatten_destinations(terminal_sets)
    dist, prev = dijkstra(graph, source)

    lines: List[str] = []
    lines.append(f"Validation log: shortest paths from {source}")
    lines.append(f"Scenario: {args.scenario}")
    lines.append(f"Source: {source} ({names.get(source, source)})")
    lines.append(f"Destination count: {len(dests)}")
    lines.append("")
    lines.append("=== Best destination in each destination set ===")
    grouped: Dict[str, List[str]] = defaultdict(list)
    for set_name, node_id in dests:
        grouped[set_name].append(node_id)

    for set_name in sorted(grouped):
        reachable = [(node_id, dist[node_id]) for node_id in grouped[set_name] if node_id in dist]
        if not reachable:
            lines.append(f"{set_name}: no reachable destination")
            continue
        best_node, best_time = min(reachable, key=lambda x: x[1])
        best_nodes, best_link_types = reconstruct_path(prev, source, best_node)
        lines.append(f"{set_name}: best={best_node} time_min={best_time:.3f}")
        lines.append(f"  path: {format_path(best_nodes, names, best_link_types)}")
    lines.append("")

    lines.append("=== Detailed results for every destination ===")
    for set_name, node_id in sorted(dests, key=lambda x: (x[0], x[1])):
        lines.append(f"[{set_name}] {node_id} ({names.get(node_id, node_id)})")
        if node_id not in dist:
            lines.append("  reachable: False")
            lines.append("  time_min: INF")
            lines.append("  path: (unreachable)")
            lines.append("")
            continue
        path_nodes, path_link_types = reconstruct_path(prev, source, node_id)
        lines.append("  reachable: True")
        lines.append(f"  time_min: {dist[node_id]:.3f}")
        lines.append(f"  n_hops: {max(len(path_nodes) - 1, 0)}")
        lines.append(f"  path: {format_path(path_nodes, names, path_link_types)}")
        lines.append("")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote log to: {log_path}")


if __name__ == "__main__":
    main()
