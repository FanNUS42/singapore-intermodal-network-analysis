from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import CONFIG
from scripts.common.io_utils import (
    get_active_scenario,
    get_scenario_model_paths,
    load_json,
    project_root_from,
    resolve_path,
    save_json,
)

EARTH_RADIUS_M = 6371000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def point_distance_m(a: Dict[str, Any], b: Dict[str, Any]) -> float | None:
    lat1, lon1 = a.get("lat"), a.get("lon")
    lat2, lon2 = b.get("lat"), b.get("lon")
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    return haversine_m(float(lat1), float(lon1), float(lat2), float(lon2))


def collect_centroids(geojson: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        node_id = str(props.get("grid_id") or props.get("centroid_id") or props.get("fid") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        out.append({
            "centroid_id": node_id,
            "grid_id": props.get("grid_id"),
            "lat": props.get("lat"),
            "lon": props.get("lon"),
            "x_svy": props.get("x_svy"),
            "y_svy": props.get("y_svy"),
        })
    return sorted(out, key=lambda x: x["centroid_id"])


def limit_items(items: List[Dict[str, Any]], max_keep: int | None) -> List[Dict[str, Any]]:
    if max_keep is None:
        return items
    return items[:max_keep]


def effective_walk_distance_m(raw_distance_m: float, access_cfg: Dict[str, Any]) -> float:
    factor = float(access_cfg.get("distance_detour_factor", 1.0))
    return float(raw_distance_m) * factor


def generate_bus_mrt_walk_pairs(bus_hubs: List[Dict[str, Any]], mrt_hubs: List[Dict[str, Any]], radius_m: float, fixed_transfer_time_min: float, round_distance_m: int, round_walk_time_min: int) -> List[Dict[str, Any]]:
    walk_pairs: List[Dict[str, Any]] = []
    for bus_hub in bus_hubs:
        for mrt_hub in mrt_hubs:
            d = point_distance_m(bus_hub, mrt_hub)
            if d is None or d > radius_m:
                continue
            primary_mrt_code = mrt_hub.get("primary_station_code") or (mrt_hub.get("station_codes") or [None])[0]
            walk_pairs.append({
                "bus_stop_code": str(bus_hub["stop_code"]),
                "bus_stop_id": bus_hub["hub_id"],
                "bus_board_node_id": bus_hub["board_node_id"],
                "bus_alight_node_id": bus_hub["alight_node_id"],
                "bus_stop_name": bus_hub.get("stop_name"),
                "mrt_station_code": primary_mrt_code,
                "mrt_hub_id": mrt_hub["hub_id"],
                "mrt_station_name": mrt_hub.get("physical_station_name"),
                "distance_m": round(float(d), round_distance_m),
                "walk_time_min": round(fixed_transfer_time_min, round_walk_time_min),
                "selected_by": "within_radius",
                "source_rule": "radius_filter_plus_fixed_transfer_time",
            })
    walk_pairs.sort(key=lambda x: (x["bus_stop_id"], x["mrt_hub_id"]))
    for idx, pair in enumerate(walk_pairs, start=1):
        pair["pair_id"] = f"IMPAIR::{idx}"
    return walk_pairs


def generate_centroid_access_pairs(centroids: List[Dict[str, Any]], bus_hubs: List[Dict[str, Any]], mrt_hubs: List[Dict[str, Any]], access_cfg: Dict[str, Any], walk_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    mode_max_distance_m = access_cfg["mode_max_distance_m"]
    keep_nearest_if_empty = bool(access_cfg.get("keep_nearest_if_empty", True))
    max_keep_per_mode = access_cfg.get("max_keep_per_mode", {"BUS": None, "MRT": None})
    round_distance_m = int(access_cfg.get("round_distance_m", 3))
    round_walk_time_min = int(access_cfg.get("round_walk_time_min", 3))
    walk_speed_kmph = float(walk_cfg["walk_speed_kmph"])
    mode_specs = [
        ("BUS", "bus", bus_hubs, float(mode_max_distance_m["BUS"]), max_keep_per_mode.get("BUS")),
        ("MRT", "mrt", mrt_hubs, float(mode_max_distance_m["MRT"]), max_keep_per_mode.get("MRT")),
    ]
    access_pairs: List[Dict[str, Any]] = []
    for centroid in centroids:
        for _mode_label, mode_name, targets, threshold_m, max_keep in mode_specs:
            candidates: List[Dict[str, Any]] = []
            for target in targets:
                d_raw = point_distance_m(centroid, target)
                if d_raw is None:
                    continue
                d_eff = effective_walk_distance_m(d_raw, access_cfg)
                if mode_name == "bus":
                    target_node_id = target["board_node_id"]
                    target_physical_node_id = target["hub_id"]
                    primary_station_id = target.get("stop_code")
                    station_name = target.get("stop_name")
                else:
                    target_node_id = target["hub_id"]
                    target_physical_node_id = target["hub_id"]
                    primary_station_id = target.get("primary_station_code") or (target.get("station_codes") or [None])[0]
                    station_name = target.get("physical_station_name")
                walk_time = d_eff / 1000.0 / walk_speed_kmph * 60.0
                candidates.append({
                    "centroid_id": centroid["centroid_id"],
                    "target_mode": mode_name,
                    "target_node_id": target_node_id,
                    "target_physical_node_id": target_physical_node_id,
                    "target_station_id": primary_station_id,
                    "target_station_name": station_name,
                    "distance_m": round(float(d_eff), round_distance_m),
                    "distance_raw_m": round(float(d_raw), round_distance_m),
                    "walk_time_min": round(float(walk_time), round_walk_time_min),
                    "selected_by": "within_threshold" if d_eff <= threshold_m else "out_of_threshold",
                })
            chosen = [c for c in candidates if c["selected_by"] == "within_threshold"]
            chosen.sort(key=lambda x: (x["distance_m"], x["target_station_id"] or ""))
            if not chosen and keep_nearest_if_empty and candidates:
                nearest = min(candidates, key=lambda x: (x["distance_m"], x["target_station_id"] or ""))
                nearest = dict(nearest)
                nearest["selected_by"] = "nearest_fallback"
                chosen = [nearest]
            for item in limit_items(chosen, max_keep):
                access_pairs.append(dict(item))
    access_pairs.sort(key=lambda x: (x["centroid_id"], x["target_mode"], x["distance_m"], x["target_node_id"]))
    for idx, pair in enumerate(access_pairs, start=1):
        pair["pair_id"] = f"ACCESS::{idx}"
    return access_pairs


def should_union_with_pre(cfg: Dict[str, Any], scenario_name: str) -> bool:
    access_cfg = cfg["params"]["access"]
    policy = str(access_cfg.get("post_access_policy", "scenario_generated_only"))
    strategy = str(cfg.get("scenarios", {}).get(scenario_name, {}).get("mrt_strategy", ""))
    return policy == "union_with_pre" and strategy != "baseline_copy"


def access_pair_key(pair: Dict[str, Any]) -> Tuple[str, str]:
    return str(pair["centroid_id"]), str(pair["target_node_id"])


def merge_access_pairs(pre_pairs: List[Dict[str, Any]], post_pairs: List[Dict[str, Any]], access_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    preserve_pre_fallback = bool(access_cfg.get("preserve_pre_fallback", True))
    walk_rule = str(access_cfg.get("union_walk_time_rule", "min"))
    distance_rule = str(access_cfg.get("union_distance_rule", "min"))
    if not preserve_pre_fallback:
        pre_pairs = [p for p in pre_pairs if p.get("selected_by") != "nearest_fallback"]
    pre_map = {access_pair_key(p): p for p in pre_pairs}
    post_map = {access_pair_key(p): p for p in post_pairs}
    merged: List[Dict[str, Any]] = []
    for key in sorted(set(pre_map) | set(post_map)):
        pre = pre_map.get(key)
        post = post_map.get(key)
        if pre and post:
            item = dict(post)
            if walk_rule == "min":
                item["walk_time_min"] = min(float(pre["walk_time_min"]), float(post["walk_time_min"]))
            if distance_rule == "min":
                item["distance_m"] = min(float(pre["distance_m"]), float(post["distance_m"]))
                item["distance_raw_m"] = min(float(pre.get("distance_raw_m", pre["distance_m"])), float(post.get("distance_raw_m", post["distance_m"])))
            item["source_tag"] = "pre_and_post"
            item["selected_by_pre"] = pre.get("selected_by")
            item["selected_by_post"] = post.get("selected_by")
        elif post:
            item = dict(post)
            item["source_tag"] = "post_only_added"
            item["selected_by_pre"] = None
            item["selected_by_post"] = post.get("selected_by")
        else:
            item = dict(pre)
            item["source_tag"] = "pre_only_preserved"
            item["selected_by_pre"] = pre.get("selected_by")
            item["selected_by_post"] = None
        merged.append(item)
    merged.sort(key=lambda x: (x["centroid_id"], x["target_mode"], x["distance_m"], x["target_node_id"]))
    for idx, pair in enumerate(merged, start=1):
        pair["pair_id"] = f"ACCESS::{idx}"
    return merged


def build_intermodal_base(cfg: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    scenario_name = get_active_scenario(cfg)
    scenario_paths = get_scenario_model_paths(cfg, scenario_name)
    out_path = resolve_path(project_root, scenario_paths["intermodal_base_json"])
    bus_base = load_json(resolve_path(project_root, cfg["paths"]["model"]["base"]["bus_base_json"]))
    mrt_base = load_json(resolve_path(project_root, scenario_paths["mrt_base_json"]))
    centroids_geojson = load_json(resolve_path(project_root, cfg["paths"]["raw"]["spatial"]["centroids_geojson"]))
    access_cfg = cfg["params"]["access"]
    walk_cfg = cfg["params"]["walk"]
    radius_m = float(cfg["params"]["intermodal_transfer"]["radius_m"])
    fixed_transfer_time_min = float(cfg["params"]["intermodal_transfer"]["fixed_transfer_time_min"])
    round_distance_m = int(access_cfg.get("round_distance_m", 3))
    round_walk_time_min = int(access_cfg.get("round_walk_time_min", 3))
    bus_hubs = bus_base.get("stop_hubs", [])
    mrt_hubs = mrt_base.get("station_hubs", [])
    centroids = collect_centroids(centroids_geojson)
    walk_pairs = generate_bus_mrt_walk_pairs(bus_hubs=bus_hubs, mrt_hubs=mrt_hubs, radius_m=radius_m, fixed_transfer_time_min=fixed_transfer_time_min, round_distance_m=round_distance_m, round_walk_time_min=round_walk_time_min)
    post_generated_access_pairs = generate_centroid_access_pairs(centroids=centroids, bus_hubs=bus_hubs, mrt_hubs=mrt_hubs, access_cfg=access_cfg, walk_cfg=walk_cfg)
    pre_generated_access_pairs: List[Dict[str, Any]] = []
    if should_union_with_pre(cfg, scenario_name):
        baseline_mrt_base = load_json(resolve_path(project_root, cfg["paths"]["model"]["base"]["mrt_base_json"]))
        pre_generated_access_pairs = generate_centroid_access_pairs(centroids=centroids, bus_hubs=bus_hubs, mrt_hubs=baseline_mrt_base.get("station_hubs", []), access_cfg=access_cfg, walk_cfg=walk_cfg)
        access_pairs = merge_access_pairs(pre_generated_access_pairs, post_generated_access_pairs, access_cfg)
    else:
        access_pairs = [dict(pair, source_tag="scenario_generated", selected_by_pre=None, selected_by_post=pair.get("selected_by")) for pair in post_generated_access_pairs]
        for idx, pair in enumerate(access_pairs, start=1):
            pair["pair_id"] = f"ACCESS::{idx}"
    source_tag_counts: Dict[str, int] = {}
    for pair in access_pairs:
        source_tag = str(pair.get("source_tag", "unknown"))
        source_tag_counts[source_tag] = source_tag_counts.get(source_tag, 0) + 1
    payload = {
        "meta": {
            "scenario": scenario_name,
            "source_files": {
                "bus_base_json": cfg["paths"]["model"]["base"]["bus_base_json"],
                "mrt_base_json": scenario_paths["mrt_base_json"],
                "centroids_geojson": cfg["paths"]["raw"]["spatial"]["centroids_geojson"],
                "baseline_mrt_base_json": cfg["paths"]["model"]["base"]["mrt_base_json"] if pre_generated_access_pairs else None,
            },
            "parameters": {
                "intermodal_transfer_radius_m": radius_m,
                "fixed_transfer_time_min": fixed_transfer_time_min,
                "walk_speed_kmph": walk_cfg["walk_speed_kmph"],
                "distance_detour_factor": access_cfg.get("distance_detour_factor", 1.0),
                "post_access_policy": access_cfg.get("post_access_policy"),
                "preserve_pre_fallback": access_cfg.get("preserve_pre_fallback"),
            },
            "counts": {
                "bus_mrt_walk_pairs": len(walk_pairs),
                "centroid_access_pairs": len(access_pairs),
                "raw_post_generated_access_pairs": len(post_generated_access_pairs),
                "raw_pre_generated_access_pairs": len(pre_generated_access_pairs),
                "source_tag_counts": source_tag_counts,
            },
        },
        "bus_mrt_walk_pairs": walk_pairs,
        "centroid_access_pairs": access_pairs,
    }
    save_json(out_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build scenario-specific intermodal_base.json")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--scenario", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = dict(CONFIG)
    cfg["_runtime"] = {"active_scenario": args.scenario}
    root = project_root_from(cfg, args.project_root)
    build_intermodal_base(cfg, root)
