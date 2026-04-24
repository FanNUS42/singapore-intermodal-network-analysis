from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from scripts.common.io_utils import load_json, resolve_path


TRANSFER_LINK_TYPES = {"bus_transfer", "mrt_transfer", "intermodal_transfer"}
RUN_LINK_TYPES = {"bus_run", "mrt_run"}


def load_nodes_lookup(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(path)
    return {str(node["node_id"]): node for node in payload.get("nodes", [])}


def load_links_lookup(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(path)
    return {str(link["link_id"]): link for link in payload.get("links", []) if link.get("link_id")}


def ordered_unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def ordered_unique_consecutive(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    last: str | None = None
    for value in values:
        if value == last:
            continue
        out.append(value)
        last = value
    return out


def scenario_lookup_paths(cfg: Dict[str, Any], scenario_name: str) -> Tuple[Path, Path]:
    scenario_paths = cfg["paths"]["model"]["scenario"][scenario_name]
    return (
        Path(scenario_paths["nodes_json"]),
        Path(scenario_paths["links_json"]),
    )


def load_ring_overlay_info(cfg: Dict[str, Any], project_root: Path, post_scenario_name: str) -> Dict[str, Any]:
    mrt_base_rel = cfg["paths"]["model"]["scenario"][post_scenario_name]["mrt_base_json"]
    mrt_base_path = resolve_path(project_root, mrt_base_rel)
    mrt_payload = load_json(mrt_base_path)
    overlay = mrt_payload.get("meta", {}).get("cc_ring_overlay", {})
    closing_pairs = [str(x) for x in overlay.get("closing_pairs", [])]
    new_station_codes = [str(x) for x in overlay.get("new_platform_station_codes", [])]
    platform_lookup = {
        str(node.get("station_code")): node
        for node in mrt_payload.get("platform_nodes", [])
        if node.get("station_code")
    }
    new_station_names = []
    new_hub_ids = []
    for code in new_station_codes:
        row = platform_lookup.get(code, {})
        if row.get("station_name"):
            new_station_names.append(str(row["station_name"]))
        hub_id = row.get("hub_id")
        if hub_id:
            new_hub_ids.append(str(hub_id))
    full_forward = closing_pairs[:4] if len(closing_pairs) >= 4 else []
    full_reverse = closing_pairs[4:8] if len(closing_pairs) >= 8 else []
    return {
        "new_run_link_ids": [f"MRTRUN::{pair}" for pair in closing_pairs],
        "new_run_pairs": closing_pairs,
        "new_station_codes": new_station_codes,
        "new_station_names": new_station_names,
        "new_hub_ids": new_hub_ids,
        "full_forward": [f"MRTRUN::{pair}" for pair in full_forward],
        "full_reverse": [f"MRTRUN::{pair}" for pair in full_reverse],
    }


def path_transfer_count(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> int:
    count = 0
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        if str(link.get("link_type") or "") in TRANSFER_LINK_TYPES:
            count += 1
    return count


def path_modes_used(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        mode = link.get("mode")
        if mode:
            values.append(str(mode))
    return ordered_unique(values)


def path_lines_used(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        if str(link.get("link_type") or "") != "mrt_run":
            continue
        value = str(link.get("line_name") or link.get("service_no") or link.get("route_id") or "")
        if value:
            values.append(value)
    return ordered_unique(values)


def path_bus_services_used(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        if str(link.get("link_type") or "") != "bus_run":
            continue
        value = str(link.get("service_no") or link.get("route_id") or "")
        if value:
            values.append(value)
    return ordered_unique(values)


def path_mrt_station_sequence(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    values: List[Tuple[str, str]] = []
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        if str(link.get("link_type") or "") != "mrt_run":
            continue
        values.append((str(link.get("from_node") or ""), str(link.get("from_station_name") or link.get("from_node") or "")))
        values.append((str(link.get("to_node") or ""), str(link.get("to_station_name") or link.get("to_node") or "")))
    ordered: List[Dict[str, Any]] = []
    last_code: str | None = None
    for code, name in values:
        if not code or code == last_code:
            continue
        ordered.append({"station_code": code, "station_name": name})
        last_code = code
    return ordered


def path_run_link_sequence(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        link_type = str(link.get("link_type") or "")
        if link_type not in RUN_LINK_TYPES:
            continue
        out.append({
            "link_id": link_id,
            "link_type": link_type,
            "mode": link.get("mode"),
            "route_id": link.get("route_id"),
            "service_no": link.get("service_no"),
            "line_name": link.get("line_name"),
            "from_node": link.get("from_node"),
            "to_node": link.get("to_node"),
            "from_name": link.get("from_station_name") or link.get("from_stop_name") or link.get("from_node"),
            "to_name": link.get("to_station_name") or link.get("to_stop_name") or link.get("to_node"),
        })
    return out


def ring_usage_info(path_link_ids: List[str], ring_info: Dict[str, Any]) -> Dict[str, Any]:
    ring_set = set(ring_info.get("new_run_link_ids", []))
    used = [link_id for link_id in path_link_ids if link_id in ring_set]
    station_codes: List[str] = []
    for link_id in used:
        _, pair = link_id.split("::", 1)
        from_code, to_code = pair.split("->", 1)
        station_codes.append(from_code)
        station_codes.append(to_code)
    station_codes = ordered_unique_consecutive(station_codes)
    full_forward = ring_info.get("full_forward", [])
    full_reverse = ring_info.get("full_reverse", [])
    uses_new_ring = bool(used)
    is_full = used == full_forward or used == full_reverse
    if not uses_new_ring:
        pattern = "no_new_ring"
    elif is_full and station_codes:
        pattern = f"full_{station_codes[0]}_to_{station_codes[-1]}"
    elif station_codes:
        pattern = f"partial_{station_codes[0]}_to_{station_codes[-1]}"
    else:
        pattern = "partial_unknown"
    return {
        "uses_new_ring": uses_new_ring,
        "new_ring_run_link_ids_used": used,
        "new_ring_run_count": len(used),
        "new_ring_station_codes_used": station_codes,
        "new_ring_entry_station_code": station_codes[0] if station_codes else None,
        "new_ring_exit_station_code": station_codes[-1] if station_codes else None,
        "new_ring_is_full_traversal": is_full,
        "ring_usage_pattern": pattern,
    }


def _add_hit(store: Dict[str, Dict[str, Any]], key: str, payload: Dict[str, Any]) -> None:
    if key not in store:
        store[key] = payload


def extract_station_hits(
    path_node_ids: List[str],
    nodes_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    hits: Dict[str, Dict[str, Any]] = {}
    for node_id in path_node_ids:
        node = nodes_lookup.get(node_id, {})
        node_type = str(node.get("node_type") or "")
        if node_type in {"mrt_platform", "mrt_station_hub"}:
            physical_id = str(node.get("physical_id") or node_id)
            key = f"mrt_station::{physical_id}"
            _add_hit(hits, key, {
                "element_kind": "mrt_station",
                "element_id": physical_id,
                "name": str(node.get("name") or physical_id),
                "representative_node_id": node_id,
                "station_codes": list(node.get("meta", {}).get("station_codes", [])) or ([str(node.get("meta", {}).get("station_code"))] if node.get("meta", {}).get("station_code") else []),
                "line_names": list(node.get("meta", {}).get("line_names", [])) or ([str(node.get("meta", {}).get("line_name"))] if node.get("meta", {}).get("line_name") else []),
                "mode": "mrt",
            })
        elif node_type in {"bus_stop_board", "bus_stop_alight", "bus_route"}:
            physical_id = str(node.get("physical_id") or node_id)
            key = f"bus_stop::{physical_id}"
            _add_hit(hits, key, {
                "element_kind": "bus_stop",
                "element_id": physical_id,
                "name": str(node.get("name") or physical_id),
                "representative_node_id": node_id,
                "service_nos": list(node.get("meta", {}).get("service_nos", [])) or ([str(node.get("meta", {}).get("service_no"))] if node.get("meta", {}).get("service_no") else []),
                "mode": "bus",
            })
    return hits


def extract_line_hits(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    hits: Dict[str, Dict[str, Any]] = {}
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        link_type = str(link.get("link_type") or "")
        if link_type == "mrt_run":
            line_name = str(link.get("line_name") or link.get("service_no") or link.get("route_id") or "")
            if not line_name:
                continue
            key = f"mrt_line::{line_name}"
            _add_hit(hits, key, {
                "element_kind": "mrt_line",
                "element_id": line_name,
                "name": line_name,
                "mode": "mrt",
                "service_no": link.get("service_no"),
                "route_id_sample": link.get("route_id"),
            })
        elif link_type == "bus_run":
            service_no = str(link.get("service_no") or link.get("route_id") or "")
            if not service_no:
                continue
            key = f"bus_service::{service_no}"
            _add_hit(hits, key, {
                "element_kind": "bus_service",
                "element_id": service_no,
                "name": service_no,
                "mode": "bus",
                "route_id_sample": link.get("route_id"),
            })
    return hits


def extract_segment_hits(path_link_ids: List[str], links_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    hits: Dict[str, Dict[str, Any]] = {}
    for link_id in path_link_ids:
        link = links_lookup.get(link_id, {})
        link_type = str(link.get("link_type") or "")
        if link_type not in RUN_LINK_TYPES:
            continue
        _add_hit(hits, link_id, {
            "element_kind": "run_segment",
            "element_id": link_id,
            "name": link_id,
            "mode": link.get("mode"),
            "link_type": link_type,
            "route_id": link.get("route_id"),
            "service_no": link.get("service_no"),
            "line_name": link.get("line_name"),
            "from_node": link.get("from_node"),
            "to_node": link.get("to_node"),
            "from_name": link.get("from_station_name") or link.get("from_stop_name") or link.get("from_node"),
            "to_name": link.get("to_station_name") or link.get("to_stop_name") or link.get("to_node"),
            "time_min": link.get("time_min"),
            "distance_m": link.get("distance_m"),
        })
    return hits


def update_incidence_counter(counter: Counter[str], hits: Dict[str, Dict[str, Any]]) -> None:
    for key in hits:
        counter[key] += 1


def materialize_incidence_rows(
    meta_store: Dict[str, Dict[str, Any]],
    pre_all: Counter[str],
    post_all: Counter[str],
    pre_changed: Counter[str],
    post_changed: Counter[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    all_keys = sorted(set(meta_store) | set(pre_all) | set(post_all) | set(pre_changed) | set(post_changed))
    for key in all_keys:
        meta = meta_store.get(key, {})
        pre_all_count = int(pre_all.get(key, 0))
        post_all_count = int(post_all.get(key, 0))
        pre_changed_count = int(pre_changed.get(key, 0))
        post_changed_count = int(post_changed.get(key, 0))
        rows.append({
            "element_kind": meta.get("element_kind"),
            "element_id": meta.get("element_id", key),
            "name": meta.get("name", key),
            "mode": meta.get("mode"),
            "pre_path_count_all": pre_all_count,
            "post_path_count_all": post_all_count,
            "delta_path_count_all": post_all_count - pre_all_count,
            "abs_delta_path_count_all": abs(post_all_count - pre_all_count),
            "pre_path_count_changed_od": pre_changed_count,
            "post_path_count_changed_od": post_changed_count,
            "delta_path_count_changed_od": post_changed_count - pre_changed_count,
            "abs_delta_path_count_changed_od": abs(post_changed_count - pre_changed_count),
            **{k: v for k, v in meta.items() if k not in {"element_kind", "element_id", "name", "mode"}},
        })
    rows.sort(key=lambda row: (-int(row["abs_delta_path_count_all"]), str(row["element_id"])))
    return rows


def top_counter_deltas(rows: List[Dict[str, Any]], n: int = 20) -> Dict[str, List[Dict[str, Any]]]:
    increased = [row for row in rows if int(row.get("delta_path_count_all", 0)) > 0]
    decreased = [row for row in rows if int(row.get("delta_path_count_all", 0)) < 0]
    increased.sort(key=lambda row: (-int(row["delta_path_count_all"]), str(row["element_id"])))
    decreased.sort(key=lambda row: (int(row["delta_path_count_all"]), str(row["element_id"])))
    return {
        "top_increased": increased[:n],
        "top_decreased": decreased[:n],
    }


def counter_to_sorted_list(counter: Counter[str]) -> List[Dict[str, Any]]:
    return [
        {"key": key, "count": int(count)}
        for key, count in sorted(counter.items(), key=lambda item: (-int(item[1]), str(item[0])))
    ]
