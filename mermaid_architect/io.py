"""
Disk I/O operations for the graph.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None


from mermaid_architect.models import json_dump


def _build_diff(old_model, new_model):
    """Compare two graph object models and return a list of change dicts."""
    changes = []

    old_nodes = {n["id"]: n for n in old_model.get("nodes", [])}
    new_nodes = {n["id"]: n for n in new_model.get("nodes", [])}

    for nid in set(old_nodes) | set(new_nodes):
        if nid not in old_nodes:
            changes.append({"type": "node_added", "nodeId": nid})
        elif nid not in new_nodes:
            changes.append({"type": "node_removed", "nodeId": nid})
        else:
            old, new = old_nodes[nid], new_nodes[nid]
            for field in ("status", "session", "title", "layer"):
                if old.get(field) != new.get(field):
                    changes.append({
                        "type": field,
                        "nodeId": nid,
                        "from": old.get(field),
                        "to": new.get(field),
                    })

    old_edges = {(e["from"], e["to"]): e for e in old_model.get("edges", [])}
    new_edges = {(e["from"], e["to"]): e for e in new_model.get("edges", [])}

    for key in set(old_edges) | set(new_edges):
        if key not in old_edges:
            changes.append({"type": "edge_added", "from": key[0], "to": key[1]})
        elif key not in new_edges:
            changes.append({"type": "edge_removed", "from": key[0], "to": key[1]})

    return changes


def _append_evolution(directory, old_model, new_model):
    """Append a history entry to evolution-log.json if there are changes."""
    changes = _build_diff(old_model, new_model)
    if not changes:
        return

    log_path = Path(directory) / "evolution-log.json"

    if log_path.exists():
        try:
            log = json.loads(log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log = {}
    else:
        log = {}

    log.setdefault("applied", [])
    log.setdefault("pending", [])
    log.setdefault("history", [])

    log["history"].append({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "changes": changes,
    })

    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_write_graph(directory, graph):
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    temp_path = dir_path / "graph.tmp.json"
    final_path = dir_path / "graph.json"
    lock_path = dir_path / "graph.lock"

    new_model = graph.to_object_model()
    content = json_dump(new_model) + "\n"

    # Load existing graph for diff before acquiring lock
    old_model = {}
    if final_path.exists():
        try:
            old_model = json.loads(final_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            old_model = {}

    with open(lock_path, "w", encoding="utf-8") as lock_file:
        if fcntl:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        elif msvcrt:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)

        try:
            temp_path.write_text(content, encoding="utf-8")
            os.replace(temp_path, final_path)
        finally:
            if fcntl:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            elif msvcrt:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

    _append_evolution(directory, old_model, new_model)

    return final_path


def write_normalized_graph(directory, graph):
    return safe_write_graph(directory, graph)
