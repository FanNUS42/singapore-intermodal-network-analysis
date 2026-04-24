from __future__ import annotations

# Final placement version for the fixed project structure.
# Put this file at the path shown by its filename under the project root.

import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _find_project_root(start: Optional[Path] = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "scripts").exists() and (candidate / "model").exists():
            return candidate
    return here.parent


PROJECT_ROOT = _find_project_root()

try:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from config import CONFIG as PROJECT_CONFIG  # type: ignore
except Exception:
    PROJECT_CONFIG = {}


DEFAULT_CONFIG: Dict[str, Any] = {
    "switches": {
        "fetch_mrt_adjacent_times": False,
    },
    "api": {
        "mrt_adjacent_times": {
            "url": "https://stg.transitlink.com.sg/eservice/eguide/rail_idx.php",
        }
    },
    "paths": {
        "raw": {
            "mrt": {
                "adjacent_time_observations_csv": "raw/mrt/adjacent_time_observations.csv",
            }
        },
        "model": {
            "mrt": {
                "adjacent_pairs_directed_csv": "model/mrt/mrt_adjacent_pairs_directed.csv",
                "adjacent_times_full_csv": "model/mrt/mrt_adjacent_times_full.csv",
            }
        },
    },
    "params": {
        "mrt": {
            "default_adjacent_run_time_min": 2.0,
            "round_time_min": 3,
            "scraper": {
                "headless": True,
                "sleep_sec": 1.0,
                "page_wait_ms": 1200,
                "post_submit_wait_ms": 1000,
                "click_timeout_ms": 3000,
                "goto_wait_until": "domcontentloaded",
                "limit": None,
                "max_retries": 2,
            },
        }
    },
}


SPECIAL_LABELS = {
    "Bayfront": "Bayfront [CE1/DT16]",
    "Bayshore": "Bayshore [TE29]",
    "Bishan": "Bishan [NS17/CC15]",
    "Botanic Gardens": "Botanic Gardens [CC19/DT9]",
    "Bugis": "Bugis [EW12/DT14]",
    "Bukit Panjang": "Bukit Panjang [BP6/DT1]",
    "Buona Vista": "Buona Vista [EW21/CC22]",
    "Caldecott": "Caldecott [CC17/TE9]",
    "Changi Airport": "Changi Airport [CG2]",
    "Chinatown": "Chinatown [NE4/DT19]",
    "Choa Chu Kang": "Choa Chu Kang [NS4/BP1]",
    "City Hall": "City Hall [NS25/EW13]",
    "Dhoby Ghaut": "Dhoby Ghaut [NS24/NE6/CC1]",
    "Expo": "Expo [CG1/DT35]",
    "Gardens by the Bay": "Gardens By the Bay [TE22]",
    "HarbourFront": "HarbourFront [NE1/CC29]",
    "Jurong East": "Jurong East [NS1/EW24]",
    "Little India": "Little India [NE7/DT12]",
    "MacPherson": "MacPherson [CC10/DT26]",
    "Marina Bay": "Marina Bay [NS27/CE2/TE20]",
    "Newton": "Newton [NS21/DT11]",
    "one-north": "one-north [CC23]",
    "Orchard": "Orchard [NS22/TE14]",
    "Outram Park": "Outram Park [EW16/NE3/TE17]",
    "Paya Lebar": "Paya Lebar [EW8/CC9]",
    "Promenade": "Promenade [CC4/DT15]",
    "Punggol": "Punggol [NE17/PTC]",
    "Raffles Place": "Raffles Place [NS26/EW14]",
    "Serangoon": "Serangoon [NE12/CC13]",
    "Sengkang": "Sengkang [NE16/STC]",
    "Stevens": "Stevens [DT10/TE11]",
    "Tampines": "Tampines [EW2/DT32]",
    "Woodlands": "Woodlands [NS9/TE2]",
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out



def load_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    merged = _deep_merge(DEFAULT_CONFIG, PROJECT_CONFIG if isinstance(PROJECT_CONFIG, dict) else {})
    if isinstance(config, dict):
        merged = _deep_merge(merged, config)
    return merged



def _resolve_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else project_root / path



def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))



def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)



def _first_nonempty(record: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default



def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default



def normalize_station_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name)).strip()



def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()



def make_station_label(name: str, code: str) -> str:
    name = normalize_station_name(name)
    if name in SPECIAL_LABELS:
        return SPECIAL_LABELS[name]
    return f"{name} [{code}]"



def choose_option_by_label(select_locator, label: str) -> bool:
    options = [opt.strip() for opt in select_locator.locator("option").all_inner_texts()]
    if label in options:
        select_locator.select_option(label=label)
        return True
    for opt in options:
        if opt.lower() == label.lower():
            select_locator.select_option(label=opt)
            return True
    return False



def parse_minutes_from_text(text: str) -> Optional[int]:
    text = clean_text(text)

    patterns = [
        r"Travel\s*Time\s*[:\-]?\s*(\d+)\s*mins?",
        r"Journey\s*Time\s*[:\-]?\s*(\d+)\s*mins?",
        r"Total\s*Travel\s*Time\s*[:\-]?\s*(\d+)\s*mins?",
        r"Estimated\s*Travel\s*Time\s*\(min\)\s*[:\-]?\s*(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))

    m = re.search(
        r"Estimated\s*Travel\s*Time\s*\(min\).*?Adult\s*\$?\d+(?:\.\d+)?\D{1,20}(\d{1,2})\D{1,40}Senior\s*Citizen",
        text,
        re.IGNORECASE,
    )
    if m:
        return int(m.group(1))

    m = re.search(
        r"Adult\s*\$?\d+(?:\.\d+)?\D{1,20}(\d{1,2})\D{1,40}(?:Senior\s*Citizen|Student|WTCS)",
        text,
        re.IGNORECASE,
    )
    if m:
        return int(m.group(1))

    return None


# ============================================================
# scraper
# ============================================================

def _extract_pair_codes(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    from_node = str(_first_nonempty(row, ["from_node", "from_code"], "")).strip()
    to_node = str(_first_nonempty(row, ["to_node", "to_code"], "")).strip()
    from_name = str(_first_nonempty(row, ["from_station_name", "from_name"], "")).strip()
    to_name = str(_first_nonempty(row, ["to_station_name", "to_name"], "")).strip()
    return from_node, to_node, from_name, to_name



def _scrape_one_pair(page, row: Dict[str, str], url: str, scraper_cfg: Dict[str, Any]) -> Dict[str, Any]:
    goto_wait_until = str(scraper_cfg.get("goto_wait_until", "domcontentloaded"))
    page_wait_ms = int(scraper_cfg.get("page_wait_ms", 1200))
    post_submit_wait_ms = int(scraper_cfg.get("post_submit_wait_ms", 1000))
    click_timeout_ms = int(scraper_cfg.get("click_timeout_ms", 3000))

    from_code, to_code, from_name, to_name = _extract_pair_codes(row)
    boarding_label = make_station_label(from_name, from_code)
    alighting_label = make_station_label(to_name, to_code)

    result: Dict[str, Any] = {
        "from_node": from_code,
        "to_node": to_code,
        "from_station_name": from_name,
        "to_station_name": to_name,
        "boarding_label": boarding_label,
        "alighting_label": alighting_label,
        "query_ok": 0,
        "travel_time_min": "",
        "status": "",
        "raw_excerpt": "",
    }

    page.goto(url, wait_until=goto_wait_until)
    page.wait_for_timeout(page_wait_ms)

    selects = page.locator("select")
    if selects.count() < 2:
        result["status"] = "select_not_found"
        return result

    boarding_select = selects.nth(0)
    alighting_select = selects.nth(1)

    ok_from = choose_option_by_label(boarding_select, boarding_label)
    ok_to = choose_option_by_label(alighting_select, alighting_label)
    result["query_ok"] = int(ok_from and ok_to)

    if not ok_from or not ok_to:
        result["status"] = "option_not_found"
        return result

    clicked = False
    for selector in [
        "input[type='submit']",
        "button[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Search')",
        "button:has-text('Go')",
        "input[value='Submit']",
        "input[value='Go']",
    ]:
        loc = page.locator(selector)
        if loc.count() <= 0:
            continue
        try:
            loc.first.click(timeout=click_timeout_ms)
            clicked = True
            break
        except PlaywrightTimeoutError:
            continue

    if not clicked:
        page.keyboard.press("Enter")

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(post_submit_wait_ms)
    text = page.locator("body").inner_text()
    tt = parse_minutes_from_text(text)

    result["travel_time_min"] = "" if tt is None else tt
    result["status"] = "ok" if tt is not None else "time_not_parsed"
    result["raw_excerpt"] = clean_text(text)[:1500]
    return result



def fetch_raw_adjacent_times(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = load_config(config)
    url = cfg["api"]["mrt_adjacent_times"].get("url", "")
    if not url:
        raise ValueError("config.api.mrt_adjacent_times.url 为空，无法执行网页抓取。")

    scraper_cfg = cfg["params"]["mrt"].get("scraper", {})
    headless = bool(scraper_cfg.get("headless", True))
    sleep_sec = float(scraper_cfg.get("sleep_sec", 1.0))
    limit = scraper_cfg.get("limit")
    max_retries = int(scraper_cfg.get("max_retries", 2))

    pairs_path = _resolve_path(PROJECT_ROOT, cfg["paths"]["model"]["mrt"]["adjacent_pairs_directed_csv"])
    output_path = _resolve_path(PROJECT_ROOT, cfg["paths"]["raw"]["mrt"]["adjacent_time_observations_csv"])

    rows = _read_csv(pairs_path)
    if limit is not None:
        rows = rows[: int(limit)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        for idx, row in enumerate(rows, start=1):
            final_result: Optional[Dict[str, Any]] = None
            for attempt in range(1, max_retries + 2):
                try:
                    final_result = _scrape_one_pair(page=page, row=row, url=url, scraper_cfg=scraper_cfg)
                    if final_result.get("status") == "ok":
                        break
                except Exception as exc:
                    from_code, to_code, from_name, to_name = _extract_pair_codes(row)
                    final_result = {
                        "from_node": from_code,
                        "to_node": to_code,
                        "from_station_name": from_name,
                        "to_station_name": to_name,
                        "boarding_label": make_station_label(from_name, from_code),
                        "alighting_label": make_station_label(to_name, to_code),
                        "query_ok": 0,
                        "travel_time_min": "",
                        "status": f"exception_{type(exc).__name__}",
                        "raw_excerpt": str(exc)[:1500],
                    }
                if attempt < max_retries + 1:
                    page.wait_for_timeout(1000)

            if final_result is None:
                continue

            results.append(final_result)
            print(
                f"[{idx}/{len(rows)}] {final_result['from_node']}->{final_result['to_node']} "
                f"status={final_result['status']} time={final_result['travel_time_min']}"
            )
            time.sleep(max(sleep_sec, 0.0))

        browser.close()

    _write_csv(output_path, results)
    status_counts: Dict[str, int] = {}
    for row in results:
        key = str(row.get("status", ""))
        status_counts[key] = status_counts.get(key, 0) + 1

    result = {
        "pairs_input_path": str(pairs_path),
        "raw_output_path": str(output_path),
        "n_pairs_attempted": len(rows),
        "n_rows_written": len(results),
        "status_counts": status_counts,
        "url": url,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ============================================================
# standardlized
# ============================================================

def _build_raw_time_lookup(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        from_code = str(_first_nonempty(row, ["from_node", "from_code", "from_station_code", "origin"], "")).strip()
        to_code = str(_first_nonempty(row, ["to_node", "to_code", "to_station_code", "destination"], "")).strip()
        time_min = _safe_float(_first_nonempty(row, ["time_min", "travel_time_min", "duration_min", "adjacent_time_min"], None))
        source = str(_first_nonempty(row, ["source", "data_source", "method"], "transitlink_web_scrape")).strip()
        status = str(_first_nonempty(row, ["status"], "")).strip()

        if not from_code or not to_code or time_min is None:
            continue
        if status and status != "ok":
            continue

        lookup[(from_code, to_code)] = {
            "time_min": time_min,
            "source": source or "transitlink_web_scrape",
        }
    return lookup



def build_mrt_adjacent_times_full(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = load_config(config)
    params = cfg["params"]["mrt"]
    default_time = float(params.get("default_adjacent_run_time_min", 2.0))
    round_ndigits = int(params.get("round_time_min", 3))

    pairs_path = _resolve_path(PROJECT_ROOT, cfg["paths"]["model"]["mrt"]["adjacent_pairs_directed_csv"])
    raw_obs_path = _resolve_path(PROJECT_ROOT, cfg["paths"]["raw"]["mrt"]["adjacent_time_observations_csv"])
    output_path = _resolve_path(PROJECT_ROOT, cfg["paths"]["model"]["mrt"]["adjacent_times_full_csv"])

    pairs_rows = _read_csv(pairs_path)
    raw_rows = _read_csv(raw_obs_path) if raw_obs_path.exists() else []
    raw_lookup = _build_raw_time_lookup(raw_rows)

    output_rows: List[Dict[str, Any]] = []
    used_raw = 0
    used_default = 0

    for row in pairs_rows:
        from_node = str(_first_nonempty(row, ["from_node", "from_code", "origin", "u"], "")).strip()
        to_node = str(_first_nonempty(row, ["to_node", "to_code", "destination", "v"], "")).strip()
        from_station_name = str(_first_nonempty(row, ["from_station_name", "from_name"], "")).strip()
        to_station_name = str(_first_nonempty(row, ["to_station_name", "to_name"], "")).strip()

        if not from_node or not to_node:
            continue

        raw_match = raw_lookup.get((from_node, to_node))
        if raw_match:
            time_min = round(float(raw_match["time_min"]), round_ndigits)
            source = raw_match.get("source", "transitlink_web_scrape")
            used_raw += 1
        else:
            time_min = round(default_time, round_ndigits)
            source = "default_parameter"
            used_default += 1

        output_rows.append(
            {
                "from_node": from_node,
                "to_node": to_node,
                "from_station_name": from_station_name,
                "to_station_name": to_station_name,
                "time_min": time_min,
                "time_source": source,
            }
        )

    _write_csv(output_path, output_rows)

    result = {
        "pairs_input_path": str(pairs_path),
        "raw_observation_path": str(raw_obs_path),
        "output_path": str(output_path),
        "n_pairs": len(output_rows),
        "n_raw_used": used_raw,
        "n_default_used": used_default,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ============================================================
# main
# ============================================================

def run(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = load_config(config)
    fetch_summary: Optional[Dict[str, Any]] = None
    if cfg["switches"].get("fetch_mrt_adjacent_times", False):
        fetch_summary = fetch_raw_adjacent_times(cfg)

    build_summary = build_mrt_adjacent_times_full(cfg)
    result = {
        "fetch": fetch_summary,
        "build": build_summary,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    run()
