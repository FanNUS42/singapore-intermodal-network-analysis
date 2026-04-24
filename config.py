from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

CONFIG = {
    "project_root": ".",
    "shared_stage_order": [
        "build_bus_base",
        "build_mrt_base",
    ],
    "scenario_stage_order": [
        "build_scenario_mrt_base",
        "build_mrt_station_centrality",
        "build_intermodal_base",
        "build_terminal_sets",
        "build_nodes_from_base",
        "build_links_from_base",
        "build_od_shortest_paths",
    ],
    "comparison_stage_order": [
        "compare_mrt_station_centrality",
        "compare_od_shortest_paths",
        "build_path_restructuring_analysis",
        "build_network_incidence_delta",
        "build_summary_4_3",
        "build_origin_impact_payload",
        "build_origin_spatial_visualization",
        "build_origin_impact_dashboard",
        "write_run_metadata",
    ],
    "scenario_order": [
        "pre_ring",
        "post_ring",
    ],
    "scenarios": {
        "pre_ring": {
            "description": "CC line before ring closure",
            "mrt_strategy": "baseline_copy",
        },
        "post_ring": {
            "description": "CC line after ring closure with CC29-CC30-CC31-CC32-CE2 links",
            "mrt_strategy": "cc_ring_overlay",
            "overlay_key": "cc_ring",
        },
    },
    "switches": {
        "build_bus_base": True,
        "build_mrt_base": True,
        "build_scenario_mrt_base": True,
        "build_mrt_station_centrality": True,
        "build_intermodal_base": True,
        "build_terminal_sets": True,
        "build_nodes_from_base": True,
        "build_links_from_base": True,
        "build_od_shortest_paths": True,
        "compare_mrt_station_centrality": True,
        "compare_od_shortest_paths": True,
        "build_path_restructuring_analysis": True,
        "build_network_incidence_delta": True,
        "build_origin_impact_payload": True,
        "build_summary_4_3": True,
        "build_origin_spatial_visualization": True,
        "build_origin_impact_dashboard": True,
        "write_run_metadata": True,
    },
    "params": {
        "bus": {
            "default_transfer_time_min": 7.1,
            "board_time_min": 0.0,
            "alight_time_min": 0.0,
        },
        "mrt": {
            "default_transfer_time_min": 4.4,
        },
        "intermodal_transfer": {
            "radius_m": 400.0,
            "fixed_transfer_time_min": 10.3,
        },
        "walk": {
            "walk_speed_kmph": 4.8,
        },
        "access": {
            "distance_metric": "haversine_latlon",
            "distance_detour_factor": 1.414,
            "mode_max_distance_m": {
                "MRT": 800.0,
                "BUS": 400.0,
            },
            "keep_nearest_if_empty": True,
            "max_keep_per_mode": {
                "MRT": None,
                "BUS": None,
            },
            "post_access_policy": "union_with_pre",
            "preserve_pre_fallback": True,
            "union_dedupe_key": "centroid_target_node",
            "union_walk_time_rule": "min",
            "union_distance_rule": "min",
            "round_distance_m": 3,
            "round_walk_time_min": 3,
        },
        "graph": {
            "bus_speed_kmph": 16.1,
            "mrt_transfer_split_rule": "equal_half",
        },
        "analysis": {
            "emit_path_segments": False,
        },
        "terminals": {
            "airport_mrt_station_code": "CG2",
            "airport_mrt_station_name": "Changi Airport",
        },
    },
    "manual_rules": {
        "mrt_alignment": {
            "drop_objectids": [],
            "manual_merge_groups": [],
            "manual_station_overrides": {},
            "manual_station_name_aliases": {},
        },
        "mrt_scraper": {
            "station_label_overrides": {
                "Bayfront": "Bayfront [CE1/DT16]",
                "Bishan": "Bishan [NS17/CC15]",
                "Bugis": "Bugis [EW12/DT14]",
                "Changi Airport": "Changi Airport [CG2]",
                "Dhoby Ghaut": "Dhoby Ghaut [NS24/NE6/CC1]",
                "Expo": "Expo [CG1/DT35]",
                "Jurong East": "Jurong East [NS1/EW24]",
                "Little India": "Little India [NE7/DT12]",
                "Marina Bay": "Marina Bay [NS27/CE2/TE20]",
                "Outram Park": "Outram Park [EW16/NE3/TE17]",
                "Promenade": "Promenade [CC4/DT15]",
                "Tampines": "Tampines [EW2/DT32]",
                "Woodlands": "Woodlands [NS9/TE2]",
            },
        },
        "bus_link_sanitization": {
            "negative_bus_routes_to_drop": ["179B_1", "S38_1", "S38_2"],
            "remove_if_negative_distance": True,
            "remove_if_negative_time": True,
        },
        "terminal_filters": {
            "excluded_under_construction_bus_stop_codes": ["03211", "03219", "03561", "03569", "05009"],
        },
        "fallbacks": {
            "mrt": {
                "auto_create_missing_hub": True,
                "missing_hub_is_interchange": False,
                "missing_hub_transfer_time_min": 0.0,
            },
        },
    },
    "paths": {
        "raw": {
            "bus": {
                "bus_route_json": "raw/bus/bus_route.json",
                "busstop_geojson": "raw/bus/busstop.geojson",
            },
            "mrt": {
                "adjacent_time_observations_csv": "cache/mrt/adjacent_time_observations.csv",
                "exit_geojson": "raw/mrt/LTAMRTStationExitGEOJSON.geojson",
                "route_topology_json": "raw/mrt/mrt_route_topology.json",
                "transfer_stations_json": "raw/mrt/mrt_transfer_stations.json",
                "links_json": "raw/mrt/mrt_links.json",
                "station_points_geojson": "raw/mrt/mrt_station_alignment/LTAMRTStation_topology_station_points_manual_rules.geojson",
            },
            "spatial": {
                "centroids_geojson": "raw/spatial/refactored centroids.geojson",
                "clipped_grids_geojson": "raw/spatial/Clipped grids.geojson",
                "cbd_bus_geojson": "raw/spatial/CBD_Bus.geojson",
                "cbd_mrt_geojson": "raw/spatial/CBD_MRT.geojson",
                "airport_bus_geojson": "raw/spatial/Airport_Bus.geojson",
            },
            "scenario": {
                "cc_ring": {
                    "new_mrt_stations_geojson": "raw/scenario/New_MRT_stations.geojson",
                    "cc_ring_links_json": "raw/scenario/cc_ring_links.json",
                }
            },
        },
        "model": {
            "base": {
                "bus_base_json": "model/base/bus_base.json",
                "mrt_base_json": "model/base/mrt_base.json",
            },
            "scenario": {
                "pre_ring": {
                    "mrt_base_json": "model/scenario/pre_ring/mrt_base.json",
                    "intermodal_base_json": "model/scenario/pre_ring/intermodal_base.json",
                    "terminal_sets_json": "model/scenario/pre_ring/terminal_sets.json",
                    "nodes_json": "model/scenario/pre_ring/graph/nodes.json",
                    "links_json": "model/scenario/pre_ring/graph/links.json",
                },
                "post_ring": {
                    "mrt_base_json": "model/scenario/post_ring/mrt_base.json",
                    "intermodal_base_json": "model/scenario/post_ring/intermodal_base.json",
                    "terminal_sets_json": "model/scenario/post_ring/terminal_sets.json",
                    "nodes_json": "model/scenario/post_ring/graph/nodes.json",
                    "links_json": "model/scenario/post_ring/graph/links.json",
                },
            },
        },
        "analysis": {
            "scenario": {
                "pre_ring": {
                    "od_shortest_paths_json": "analysis/scenario/pre_ring/od/centroid_terminal_shortest_paths.json",
                    "mrt_station_centrality_json": "analysis/scenario/pre_ring/network/mrt_station_centrality.json",
                },
                "post_ring": {
                    "od_shortest_paths_json": "analysis/scenario/post_ring/od/centroid_terminal_shortest_paths.json",
                    "mrt_station_centrality_json": "analysis/scenario/post_ring/network/mrt_station_centrality.json",
                },
            },
            "comparison": {
                "od_shortest_paths_json": "analysis/comparison/pre_vs_post_ring_od_shortest_paths.json",
                "mrt_station_centrality_csv": "analysis/comparison/pre_vs_post_ring_mrt_station_centrality.csv",
                "mrt_station_centrality_json": "analysis/comparison/pre_vs_post_ring_mrt_station_centrality.json",
                "path_restructuring": {
                    "od_records_json": "analysis/comparison/path_restructuring/od_path_restructuring.json",
                    "summary_json": "analysis/comparison/path_restructuring/summary.json",
                },
                "network_incidence": {
                    "station_csv": "analysis/comparison/network_incidence/station_incidence_delta.csv",
                    "line_csv": "analysis/comparison/network_incidence/line_incidence_delta.csv",
                    "segment_csv": "analysis/comparison/network_incidence/segment_incidence_delta.csv",
                    "summary_json": "analysis/comparison/network_incidence/summary.json",
                },
            },
            "origin_impact": {
                "origin_csv": "analysis/origin_impact/origin_aggregate_metrics.csv",
                "destination_csv": "analysis/origin_impact/destination_aggregate_metrics.csv",
                "od_long_csv": "analysis/origin_impact/origin_destination_saving_long.csv",
                "payload_json": "analysis/origin_impact/origin_dashboard_payload.json",
            },
            "visualization": {
                "origin_heatmap_png": "analysis/visualization/origin_spatial_saving_heatmap_abc.png",
                "dashboard_html": "analysis/visualization/origin_impact_dashboard.html",
            },
            "run_metadata_json": "analysis/run_metadata.json",
        },
    },
}
