# Methodology-to-code mapping

This file connects the report structure to the repository pipeline.

| Report component | Code and output basis |
|---|---|
| 3.1 MRT Network Mechanism | `build_mrt_station_centrality.py`; outputs in `analysis/scenario/<scenario>/network/` and `analysis/comparison/pre_vs_post_ring_mrt_station_centrality.*` |
| 3.2 Intermodal Network Modelling | `build_bus_base.py`, `build_mrt_base.py`, `build_scenario_mrt_base.py`, `build_intermodal_base.py`, `build_nodes_from_base.py`, `build_links_from_base.py` |
| 3.2 Path Comparison | `build_od_shortest_paths.py`, `compare_od_shortest_paths.py` |
| 4.2 Optimal Path Restructuring | `build_path_restructuring_analysis.py`, `build_network_incidence_delta.py` |
| 4.3 Travel-time Impact | `build_summary_4_3.py`, `build_origin_impact_payload.py`, `build_origin_spatial_visualization.py`, `build_origin_impact_dashboard.py` |

The report should use the same terminology as the generated files: `pre_ring`, `post_ring`, `path_changed`, `uses_new_ring`, `new_ring_is_full_traversal`, `delta_time_min`, and destination groups `CBD` and `Airport`.
