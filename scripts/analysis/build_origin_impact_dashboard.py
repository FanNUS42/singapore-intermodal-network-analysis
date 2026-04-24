from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from config import CONFIG
from scripts.common.io_utils import load_json, project_root_from, resolve_path, runtime_cfg_for_comparison


def _dashboard_html(payload: Dict[str, Any]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    template = Path(__file__).with_name("build_origin_impact_dashboard_template.html").read_text(encoding="utf-8")
    return template.replace("__PAYLOAD_JSON__", payload_json)


def build_origin_impact_dashboard(cfg: Dict[str, Any], project_root: Path) -> Dict[str, str]:
    payload_path = resolve_path(project_root, cfg["paths"]["analysis"]["origin_impact"]["payload_json"])
    payload = load_json(payload_path)
    output_path = resolve_path(project_root, cfg["paths"]["analysis"]["visualization"]["dashboard_html"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_dashboard_html(payload), encoding="utf-8")
    return {"dashboard_html": str(output_path.relative_to(project_root))}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build self-contained origin-side impact HTML dashboard")
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = runtime_cfg_for_comparison(CONFIG, ["pre_ring", "post_ring"])
    root = project_root_from(cfg, args.project_root)
    print(json.dumps(build_origin_impact_dashboard(cfg, root), ensure_ascii=False, indent=2))
