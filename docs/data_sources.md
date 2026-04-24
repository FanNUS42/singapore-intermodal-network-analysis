# Data sources and file provenance

This document records the project data inventory. It separates external or manually prepared inputs from generated outputs so that the repository can be audited and rerun.

## Raw and manually prepared inputs

| Data group | File | Role in the project | Processing status | Used by |
|---|---|---|---|---|
| Bus route topology | `raw/bus/bus_route.json` | Ordered bus route-stop sequences and route distance attributes | Cleaned project input | `build_bus_base.py` |
| Bus stop locations | `raw/bus/busstop.geojson` | Spatial reference for bus stops | Raw or lightly cleaned spatial input | Documentation and validation reference |
| MRT station exits | `raw/mrt/LTAMRTStationExitGEOJSON.geojson` | Source station spatial reference | Raw spatial input | Alignment archive or validation reference |
| MRT route topology | `raw/mrt/mrt_route_topology.json` | MRT line station order and platform-node basis | Project-compiled topology | `build_mrt_base.py` |
| MRT adjacent travel time | `raw/mrt/mrt_links.json` | Adjacent-station run links and travel times | Scraped from TransitLink Rail eGuide observations and manual/default fill where required | `build_mrt_base.py` `mrt_adjacent_time_scraper.py`|
| MRT transfer stations | `raw/mrt/mrt_transfer_stations.json` | Physical-station transfer grouping and transfer-time assumptions | Project-prepared | `build_mrt_base.py` |
| MRT station alignment | `raw/mrt/mrt_station_alignment/LTAMRTStation_topology_station_points_manual_rules.geojson` | One point per topology station after name and geometry alignment | Project-prepared aligned station point file | `build_mrt_base.py` |
| New MRT stations | `raw/scenario/New_MRT_stations.geojson` | CC30 Keppel, CC31 Cantonment, and CC32 Prince Edward Road scenario nodes | Scenario overlay input | `apply_cc_ring_overlay.py` |
| New Circle Line links | `raw/scenario/cc_ring_links.json` | New directed run links for CC29-CC30-CC31-CC32-CE2 | Scenario overlay input | `apply_cc_ring_overlay.py` |
| Origin centroids | `raw/spatial/refactored centroids.geojson` | Residential grid centroids used as OD origins | Project-prepared spatial input | `build_intermodal_base.py` |
| Study-area grid polygons | `raw/spatial/Clipped grids.geojson` | Polygon geometry for origin-side visualization | Project-prepared spatial input | `build_origin_impact_payload.py`, `build_origin_spatial_visualization.py` |
| CBD bus terminals | `raw/spatial/CBD_Bus.geojson` | CBD-bound bus destination terminals | Project-selected destination input | `build_terminal_sets.py` |
| CBD MRT terminals | `raw/spatial/CBD_MRT.geojson` | CBD-bound MRT destination terminals | Project-selected destination input | `build_terminal_sets.py` |
| Airport bus terminals | `raw/spatial/Airport_Bus.geojson` | Airport-bound bus destination terminals | Project-selected destination input | `build_terminal_sets.py` |
| Airport MRT terminal | configured as `CG2` in `config.py` | Airport-bound MRT destination terminal | Configuration-defined terminal | `build_terminal_sets.py` |

## Main modelling assumptions recorded in configuration

| Parameter group | Current value | Location |
|---|---:|---|
| Bus operating speed | 16.1 km/h | `CONFIG["params"]["graph"]["bus_speed_kmph"]` |
| Walking speed | 4.8 km/h | `CONFIG["params"]["walk"]["walk_speed_kmph"]` |
| Bus access radius | 400 m | `CONFIG["params"]["access"]["mode_max_distance_m"]["BUS"]` |
| MRT access radius | 800 m | `CONFIG["params"]["access"]["mode_max_distance_m"]["MRT"]` |
| Walking detour factor | 1.414 | `CONFIG["params"]["access"]["distance_detour_factor"]` |
| Bus-to-MRT transfer radius | 400 m | `CONFIG["params"]["intermodal_transfer"]["radius_m"]` |
| Bus-to-MRT transfer time | 10.3 min | `CONFIG["params"]["intermodal_transfer"]["fixed_transfer_time_min"]` |
| Default bus transfer time | 7.1 min | `CONFIG["params"]["bus"]["default_transfer_time_min"]` |
| Default MRT transfer time | 4.4 min | `CONFIG["params"]["mrt"]["default_transfer_time_min"]` |
| Post-ring access policy | union with pre-ring access | `CONFIG["params"]["access"]["post_access_policy"]` |

## Generated outputs

| Output group | Location | Regeneration command |
|---|---|---|
| Shared base network | `model/base/` | `python main.py --scenario all --only build_bus_base build_mrt_base` |
| Scenario graph files | `model/scenario/<scenario>/` | `python main.py --scenario <scenario>` |
| Scenario OD shortest paths | `analysis/scenario/<scenario>/od/` | `python main.py --scenario <scenario> --only build_od_shortest_paths` |
| Pre-post OD comparison | `analysis/comparison/pre_vs_post_ring_od_shortest_paths.json` | `python main.py --scenario all --only compare_od_shortest_paths` |
| Path restructuring outputs | `analysis/comparison/path_restructuring/` | `python main.py --scenario all --only build_path_restructuring_analysis` |
| Network incidence tables | `analysis/comparison/network_incidence/` | `python main.py --scenario all --only build_network_incidence_delta` |
| Report tables and figures | `analysis/summary/`, `analysis/visualization/` | `python main.py --scenario all --only build_summary_4_3 build_origin_impact_payload build_origin_spatial_visualization build_origin_impact_dashboard` |

## Notes for public release

Check the licensing and redistribution terms of any third-party transport datasets before publishing raw data. If redistribution is restricted, replace raw data with a documented acquisition guide and keep only derived examples or small demonstration inputs in the public repository.
