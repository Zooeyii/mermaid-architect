"""
experience.py — record agent execution experience for future calibration.
"""

import json
from datetime import date
from pathlib import Path


def get_velocity_estimate(graph_dir: str, layer: str) -> str:
    velocity_path = Path(graph_dir).parent / "experience" / "velocity.json"
    if not velocity_path.exists():
        return "暂无数据"
    try:
        data = json.loads(velocity_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "暂无数据"

    entry = data.get("by_layer", {}).get(layer)
    if not entry or entry.get("count", 0) == 0:
        return "暂无数据"

    total = int(entry["avg_seconds"])
    m, s = divmod(total, 60)
    count = entry["count"]
    return f"约{m}分{s:02d}秒（基于{count}个样本）"


def record_completion(graph_dir: str, node_id: str, layer: str, duration_seconds: float, success: bool) -> None:
    velocity_path = Path(graph_dir).parent / "experience" / "velocity.json"
    velocity_path.parent.mkdir(parents=True, exist_ok=True)

    if velocity_path.exists():
        try:
            data = json.loads(velocity_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    data.setdefault("by_layer", {})
    data.setdefault("by_priority", {})
    data.setdefault("trend", "baseline")
    data.setdefault("last_updated", "")

    by_layer = data["by_layer"]
    entry = by_layer.get(layer, {"count": 0, "avg_seconds": 0.0, "success_rate": 1.0})

    old_count = entry["count"]
    new_count = old_count + 1
    entry["avg_seconds"] = (entry["avg_seconds"] * old_count + duration_seconds) / new_count
    entry["success_rate"] = (entry["success_rate"] * old_count + (1.0 if success else 0.0)) / new_count
    entry["count"] = new_count

    by_layer[layer] = entry

    data["last_updated"] = date.today().isoformat()

    velocity_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
