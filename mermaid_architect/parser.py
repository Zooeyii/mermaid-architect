"""
Parser for Mermaid files and directory loading.
"""

import json
from pathlib import Path

from mermaid_architect.models import (
    Graph,
    Node,
    MERMAID_NODE_PATTERN,
    MERMAID_EDGE_PATTERN,
    canonical_node_id,
)

def load_merged_graph(graph_dir):
    """Load graph.json and merge with archive.json (for visualization)."""
    graph_path = Path(graph_dir) / "graph.json"
    if not graph_path.exists():
        return {"version": "unknown", "nodes": [], "edges": [], "milestones": {}}

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    # Merge with archive
    archive_path = Path(graph_dir) / "graph.archive.json"
    if archive_path.exists():
        try:
            with open(archive_path, "r", encoding="utf-8") as f:
                archive = json.load(f)

            live_ids = {n["id"] for n in graph.get("nodes", [])}
            archived_nodes = [
                {**n, "archived": True}
                for n in archive.get("nodes", [])
                if n["id"] not in live_ids
            ]

            # Merge nodes
            graph["nodes"] = graph.get("nodes", []) + archived_nodes

            # Merge milestones
            if archive.get("milestones"):
                graph["milestones"] = {**archive["milestones"], **graph.get("milestones", {})}
        except Exception:
            pass  # Archive read errors are non-fatal

    return graph


def parse_mmd_to_graph(text):
    graph = Graph()
    alias_map = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("flowchart") or line.startswith("graph") or line.startswith("%%"):
            continue

        node_matches = list(MERMAID_NODE_PATTERN.finditer(line))
        for match in node_matches:
            alias, label = match.groups()
            node_id = canonical_node_id(alias, label)
            alias_map[alias] = node_id
            graph.add_node(Node.from_mermaid(node_id, label), declared=True)

        edge_match = MERMAID_EDGE_PATTERN.match(line)
        if edge_match:
            src_alias, rel, dst_alias = edge_match.groups()
            src = alias_map.get(src_alias, canonical_node_id(src_alias))
            dst = alias_map.get(dst_alias, canonical_node_id(dst_alias))
            graph.add_edge(src, rel, dst)

    return graph


def read_version(directory):
    version_path = directory / "version.txt"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip() or None
    return None


def load_directory(directory):
    directory = Path(directory)
    version = read_version(directory)
    graph_path = directory / "graph.json"
    mmd_files = sorted(directory.glob("*.mmd"))

    if graph_path.exists():
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph = Graph.from_object_model(payload)
        if version and not graph.version:
            graph.version = version

        if graph.nodes:
            return graph

        parsed_graphs = [
            parse_mmd_to_graph(file_path.read_text(encoding="utf-8"))
            for file_path in mmd_files
        ]
        parsed_graph = Graph.merge(*parsed_graphs) if parsed_graphs else Graph()
        if parsed_graph.nodes:
            if version and not parsed_graph.version:
                parsed_graph.version = version
            return parsed_graph

        return graph

    graphs = [
        parse_mmd_to_graph(file_path.read_text(encoding="utf-8"))
        for file_path in mmd_files
    ]
    graph = Graph.merge(*graphs) if graphs else Graph()
    if version:
        graph.version = version
    return graph


def load_source(pathname):
    path = Path(pathname)

    if path.is_dir():
        return load_directory(path)

    if path.suffix == ".json":
        return Graph.from_object_model(json.loads(path.read_text(encoding="utf-8")))

    if path.suffix == ".mmd":
        return parse_mmd_to_graph(path.read_text(encoding="utf-8"))

    raise ValueError(f"unsupported source: {pathname}")
