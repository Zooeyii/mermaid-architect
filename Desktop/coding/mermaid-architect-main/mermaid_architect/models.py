"""
Core object models and analysis reports.
"""

import json
import re
from collections import defaultdict

STATUS_VALUES = ("todo", "doing", "blocked", "done")
LAYER_VALUES = ("R", "D", "F", "U")
LAYER_ORDER = {"R": 0, "D": 1, "F": 2, "U": 3}
EDGE_TYPES = ("-->", "-.->", "==>")

MERMAID_NODE_PATTERN = re.compile(r'([A-Za-z0-9_]+)\["(.+?)"\]')
MERMAID_EDGE_PATTERN = re.compile(
    r'^\s*([A-Za-z0-9_]+)(?:\[".*?"\])?\s*(-->|-.->|==>)\s*([A-Za-z0-9_]+)(?:\[".*?"\])?\s*$'
)
CANONICAL_ID_PATTERN = re.compile(r'\b([RDFU]-\d{3,})\b')
MERMAID_ALIAS_PATTERN = re.compile(r'^([RDFU])[_-]?(\d+)$')



def split_label_lines(label):
    normalized = label.replace("<br/>", "\n").replace("<br>", "\n")
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def canonical_node_id(alias, label=None):
    if label:
        first_line = split_label_lines(label)[0]
        match = CANONICAL_ID_PATTERN.search(first_line)
        if match:
            return match.group(1)

    match = MERMAID_ALIAS_PATTERN.match(alias)
    if match:
        prefix, digits = match.groups()
        return f"{prefix}-{digits.zfill(3)}"

    return alias


def mermaid_alias(node_id):
    match = CANONICAL_ID_PATTERN.fullmatch(node_id)
    if match:
        return node_id.replace("-", "")

    compact = re.sub(r'[^A-Za-z0-9_]', '', node_id)
    return compact or node_id.replace("-", "")


def json_dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False)

class Node:
    __slots__ = (
        "id",
        "title",
        "layer",
        "status",
        "session",
        "kind",
        "file",
        "functions",
        "tdd",
        "expected",
        "metadata",
    )

    def __init__(
        self,
        nid,
        title="",
        layer=None,
        status="todo",
        session=None,
        kind=None,
        file=None,
        functions=None,
        tdd=None,
        expected=None,
        metadata=None,
    ):
        self.id = nid
        self.title = title or nid
        self.layer = layer if layer in LAYER_VALUES else self._parse_layer(nid)
        self.status = status if status in STATUS_VALUES else "todo"
        self.session = session
        self.kind = kind
        self.file = file
        self.functions = list(functions or [])
        self.tdd = dict(tdd or {})
        self.expected = expected
        self.metadata = dict(metadata or {})

    @staticmethod
    def _parse_layer(nid):
        prefix = nid.split("-")[0] if "-" in nid else nid[:1]
        return prefix if prefix in LAYER_VALUES else "?"

    @classmethod
    def from_dict(cls, payload):
        return cls(
            nid=payload["id"],
            title=payload.get("title", payload["id"]),
            layer=payload.get("layer"),
            status=payload.get("status", "todo"),
            session=payload.get("session"),
            kind=payload.get("kind"),
            file=payload.get("file"),
            functions=payload.get("functions", []),
            tdd=payload.get("tdd", {}),
            expected=payload.get("expected"),
            metadata=payload.get("metadata", {}),
        )

    @classmethod
    def from_mermaid(cls, nid, label):
        lines = split_label_lines(label)
        title_line = lines[0] if lines else nid
        if title_line == nid:
            title = nid
        elif title_line.startswith(f"{nid} "):
            title = title_line[len(nid) + 1 :]
        else:
            title = title_line

        payload = {
            "id": nid,
            "title": title,
            "layer": cls._parse_layer(nid),
            "status": "todo",
            "session": None,
            "kind": None,
            "file": None,
            "functions": [],
            "tdd": {},
            "expected": None,
            "metadata": {},
        }

        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if key == "status" and value in STATUS_VALUES:
                payload["status"] = value
            elif key == "session":
                payload["session"] = value or None
            elif key == "kind":
                payload["kind"] = value or None
            elif key == "file":
                payload["file"] = value or None
            elif key == "functions":
                payload["functions"] = [item.strip() for item in value.split(",") if item.strip()]
            elif key == "expected":
                payload["expected"] = value or None
            else:
                payload["metadata"][key] = value

        return cls.from_dict(payload)

    def merge(self, other):
        if self.id != other.id:
            raise ValueError("cannot merge nodes with different ids")

        functions = list(self.functions)
        for name in other.functions:
            if name not in functions:
                functions.append(name)

        merged_tdd = dict(self.tdd)
        merged_tdd.update(other.tdd)

        merged_metadata = dict(self.metadata)
        merged_metadata.update(other.metadata)

        return Node(
            nid=self.id,
            title=other.title if other.title and other.title != other.id else self.title,
            layer=other.layer if other.layer in LAYER_VALUES else self.layer,
            status=other.status if other.status in STATUS_VALUES else self.status,
            session=other.session if other.session is not None else self.session,
            kind=other.kind or self.kind,
            file=other.file or self.file,
            functions=functions,
            tdd=merged_tdd,
            expected=other.expected or self.expected,
            metadata=merged_metadata,
        )

    def render_label(self):
        parts = [f"{self.id} {self.title}".strip()]
        parts.append(f"status: {self.status}")

        if self.session:
            parts.append(f"session: {self.session}")
        if self.kind:
            parts.append(f"kind: {self.kind}")
        if self.file:
            parts.append(f"file: {self.file}")
        if self.functions:
            parts.append(f"functions: {','.join(self.functions)}")
        if self.expected:
            parts.append(f"expected: {self.expected}")

        for key in sorted(self.metadata):
            parts.append(f"{key}: {self.metadata[key]}")

        return "<br/>".join(parts).replace('"', "&quot;")

    def to_dict(self):
        payload = {
            "id": self.id,
            "title": self.title,
            "layer": self.layer,
            "status": self.status,
            "session": self.session,
        }

        if self.kind:
            payload["kind"] = self.kind
        if self.file:
            payload["file"] = self.file
        if self.functions:
            payload["functions"] = self.functions
        if self.tdd:
            payload["tdd"] = self.tdd
        if self.expected:
            payload["expected"] = self.expected
        if self.metadata:
            payload["metadata"] = self.metadata

        return payload


class Graph:
    def __init__(self, version=None):
        self.version = version
        self.nodes = {}
        self.edges = set()
        self._fwd = defaultdict(set)
        self._rev = defaultdict(set)
        self._declared_counts = defaultdict(int)

    def add_node(self, node_or_id, title="", declared=True):
        if isinstance(node_or_id, Node):
            incoming = node_or_id
        else:
            incoming = Node(node_or_id, title=title)

        existing = self.nodes.get(incoming.id)
        self.nodes[incoming.id] = existing.merge(incoming) if existing else incoming

        if declared:
            self._declared_counts[incoming.id] += 1

    def add_edge(self, src, rel, dst):
        relation = rel if rel in EDGE_TYPES else "-->"
        self.edges.add((src, relation, dst))
        self._fwd[src].add(dst)
        self._rev[dst].add(src)

        if src not in self.nodes:
            self.add_node(src, declared=False)
        if dst not in self.nodes:
            self.add_node(dst, declared=False)

    def get_node(self, nid):
        return self.nodes.get(nid)

    def _sorted_ids(self, ids):
        return sorted(
            ids,
            key=lambda nid: (
                LAYER_ORDER.get(self.nodes.get(nid).layer if self.nodes.get(nid) else "?", 99),
                nid,
            ),
        )

    def _sorted_nodes(self, ids):
        return [self.nodes[nid] for nid in self._sorted_ids(ids) if nid in self.nodes]

    def direct_predecessors(self, nid):
        return self._sorted_nodes(self._rev.get(nid, set()))

    def direct_successors(self, nid):
        return self._sorted_nodes(self._fwd.get(nid, set()))

    def all_predecessors(self, nid):
        visited = set()
        stack = list(self._rev.get(nid, set()))

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self._rev.get(current, set()))

        return self._sorted_nodes(visited)

    def all_successors(self, nid):
        visited = set()
        stack = list(self._fwd.get(nid, set()))

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self._fwd.get(current, set()))

        return self._sorted_nodes(visited)

    def blockers(self, nid):
        return [node for node in self.direct_predecessors(nid) if node.status != "done"]

    def can_execute(self, nid):
        node = self.get_node(nid)
        if not node or node.status == "done":
            return False
        return len(self.blockers(nid)) == 0

    def is_ready(self, nid):
        node = self.get_node(nid)
        if not node or node.status != "todo":
            return False
        if node.session:
            return False
        return self.can_execute(nid)

    def ready_nodes(self):
        ready = [node for nid, node in self.nodes.items() if self.is_ready(nid)]
        ready.sort(
            key=lambda node: (
                -len(self.all_successors(node.id)),
                -self.out_degree(node.id),
                LAYER_ORDER.get(node.layer, 99),
                node.id,
            )
        )
        return ready

    def next_after(self, nid):
        result = []
        for successor in self.direct_successors(nid):
            if successor.status not in ("todo", "blocked"):
                continue

            blockers = [
                pred
                for pred in self.direct_predecessors(successor.id)
                if pred.id != nid and pred.status != "done"
            ]
            if not blockers:
                result.append(successor)

        return self._sorted_nodes([node.id for node in result])

    def progress(self):
        layers = {
            layer: {"total": 0, "done": 0, "doing": 0, "todo": 0, "blocked": 0}
            for layer in LAYER_VALUES
        }
        overall = {"total": 0, "done": 0, "doing": 0, "todo": 0, "blocked": 0}
        sessions = defaultdict(lambda: {"claimed": 0, "todo": 0, "doing": 0, "blocked": 0, "done": 0})

        for node in self.nodes.values():
            overall["total"] += 1
            overall[node.status] += 1

            if node.layer in layers:
                layers[node.layer]["total"] += 1
                layers[node.layer][node.status] += 1

            if node.session:
                sessions[node.session]["claimed"] += 1
                sessions[node.session][node.status] += 1

        return {
            "overall": overall,
            "layers": {layer: stats for layer, stats in layers.items() if stats["total"] > 0},
            "sessions": dict(sorted(sessions.items())),
        }

    def in_degree(self, nid):
        return len(self._rev.get(nid, set()))

    def out_degree(self, nid):
        return len(self._fwd.get(nid, set()))

    def degree_analysis(self):
        in_top = sorted(
            [(nid, self.in_degree(nid)) for nid in self.nodes if self.in_degree(nid) > 0],
            key=lambda item: (-item[1], item[0]),
        )[:5]
        out_top = sorted(
            [(nid, self.out_degree(nid)) for nid in self.nodes if self.out_degree(nid) > 0],
            key=lambda item: (-item[1], item[0]),
        )[:5]
        isolated = [
            nid
            for nid in self._sorted_ids(self.nodes.keys())
            if self.in_degree(nid) == 0 and self.out_degree(nid) == 0
        ]

        return {
            "in_degree_top": in_top,
            "out_degree_top": out_top,
            "isolated": isolated,
        }

    def duplicate_ids(self):
        return sorted([nid for nid, count in self._declared_counts.items() if count > 1])

    def detect_cycle(self):
        white, gray, black = 0, 1, 2
        color = {nid: white for nid in self.nodes}
        trail = []

        def dfs(node_id):
            color[node_id] = gray
            trail.append(node_id)

            for successor in self._fwd.get(node_id, set()):
                if color[successor] == gray:
                    start = trail.index(successor) if successor in trail else 0
                    return True, trail[start:] + [successor]
                if color[successor] == white:
                    found, cycle = dfs(successor)
                    if found:
                        return True, cycle

            trail.pop()
            color[node_id] = black
            return False, []

        for nid in self._sorted_ids(self.nodes.keys()):
            if color[nid] == white:
                found, cycle = dfs(nid)
                if found:
                    return True, cycle

        return False, []

    def topological_order(self):
        in_degree = {nid: 0 for nid in self.nodes}
        for _, _, dst in self.edges:
            in_degree[dst] += 1

        queue = self._sorted_ids([nid for nid, degree in in_degree.items() if degree == 0])
        order = []

        while queue:
            current = queue.pop(0)
            order.append(current)
            for successor in self._sorted_ids(self._fwd.get(current, set())):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)
                    queue.sort(key=lambda nid: (LAYER_ORDER.get(self.nodes[nid].layer, 99), nid))

        return order

    def longest_path(self):
        order = self.topological_order()
        if len(order) != len(self.nodes):
            return []

        distance = {nid: 0 for nid in self.nodes}
        previous = {nid: None for nid in self.nodes}

        for node_id in order:
            for successor in self._fwd.get(node_id, set()):
                if distance[successor] < distance[node_id] + 1:
                    distance[successor] = distance[node_id] + 1
                    previous[successor] = node_id

        if not distance:
            return []

        end = max(distance, key=distance.get)
        path = []
        current = end
        while current is not None:
            path.append(current)
            current = previous[current]
        path.reverse()
        return path

    def check_layer_coverage(self):
        layers = {layer: set() for layer in LAYER_VALUES}
        for nid, node in self.nodes.items():
            if node.layer in layers:
                layers[node.layer].add(nid)

        unmapped_r = []
        for nid in self._sorted_ids(layers["R"]):
            if not any(node.layer == "D" for node in self.direct_successors(nid)):
                unmapped_r.append(nid)

        unmapped_d = []
        for nid in self._sorted_ids(layers["D"]):
            if not any(node.layer == "F" for node in self.direct_successors(nid)):
                unmapped_d.append(nid)

        dangling_f = []
        for nid in self._sorted_ids(layers["F"]):
            if self.out_degree(nid) == 0 and self.in_degree(nid) > 0:
                dangling_f.append(nid)

        return {
            "R_count": len(layers["R"]),
            "D_count": len(layers["D"]),
            "F_count": len(layers["F"]),
            "U_count": len(layers["U"]),
            "unmapped_R_to_D": unmapped_r,
            "unmapped_D_to_F": unmapped_d,
            "dangling_F": dangling_f,
        }

    def validate_issues(self):
        issues = []
        duplicates = self.duplicate_ids()
        has_cycle, cycle = self.detect_cycle()
        degree = self.degree_analysis()
        coverage = self.check_layer_coverage()

        if duplicates:
            issues.append(f"duplicate node ids: {duplicates}")
        if has_cycle:
            issues.append(f"cycle detected: {cycle}")
        if degree["isolated"]:
            issues.append(f"isolated nodes: {degree['isolated']}")
        if coverage["unmapped_R_to_D"]:
            issues.append(f"R nodes without D mapping: {coverage['unmapped_R_to_D']}")
        if coverage["unmapped_D_to_F"]:
            issues.append(f"D nodes without F mapping: {coverage['unmapped_D_to_F']}")

        return issues

    def to_object_model(self):
        return {
            "version": self.version,
            "nodes": [self.nodes[nid].to_dict() for nid in self._sorted_ids(self.nodes.keys())],
            "edges": [
                {"from": src, "to": dst, "type": rel}
                for src, rel, dst in sorted(self.edges, key=lambda item: (item[0], item[2], item[1]))
            ],
        }

    def _layer_subgraph(self, layer):
        subgraph = Graph(version=self.version)

        for nid, node in self.nodes.items():
            if node.layer == layer:
                subgraph.add_node(node, declared=True)

        for src, rel, dst in self.edges:
            if src in subgraph.nodes and dst in subgraph.nodes:
                subgraph.add_edge(src, rel, dst)

        return subgraph

    def to_mermaid(self, layer=None, direction="TD"):
        target = self._layer_subgraph(layer) if layer else self
        aliases = {nid: mermaid_alias(nid) for nid in target.nodes}

        lines = [f"flowchart {direction}"]
        for nid in target._sorted_ids(target.nodes.keys()):
            node = target.nodes[nid]
            lines.append(f'    {aliases[nid]}["{node.render_label()}"]')

        lines.append("")

        for src, rel, dst in sorted(target.edges, key=lambda item: (item[0], item[2], item[1])):
            lines.append(f"    {aliases[src]} {rel} {aliases[dst]}")

        return "\n".join(lines).rstrip() + "\n"

    def full_summary(self):
        degree = self.degree_analysis()
        path = self.longest_path()
        progress = self.progress()
        ready = self.ready_nodes()
        issues = self.validate_issues()

        lines = []
        version = self.version or "unversioned"
        lines.append(f"## Current Graph ({version})")
        lines.append(f"nodes: {len(self.nodes)} | edges: {len(self.edges)}")

        in_degree_text = ", ".join(f"{nid}({value})" for nid, value in degree["in_degree_top"]) or "-"
        out_degree_text = ", ".join(f"{nid}({value})" for nid, value in degree["out_degree_top"]) or "-"
        path_text = " -> ".join(path) if path else "-"
        lines.append(f"in-degree top: {in_degree_text}")
        lines.append(f"out-degree top: {out_degree_text}")
        lines.append(f"critical path: {path_text}")

        if issues:
            lines.append(f"issues: {'; '.join(issues)}")

        lines.append("")
        lines.append("## Progress")
        overall = progress["overall"]
        done_pct = (overall["done"] / overall["total"] * 100) if overall["total"] else 0
        lines.append(
            f"overall: {overall['done']}/{overall['total']} done ({done_pct:.0f}%) | "
            f"doing:{overall['doing']} todo:{overall['todo']} blocked:{overall['blocked']}"
        )

        for layer in LAYER_VALUES:
            if layer not in progress["layers"]:
                continue
            stats = progress["layers"][layer]
            done_pct = (stats["done"] / stats["total"] * 100) if stats["total"] else 0
            lines.append(
                f"{layer}: {stats['done']}/{stats['total']} done ({done_pct:.0f}%) | "
                f"doing:{stats['doing']} todo:{stats['todo']} blocked:{stats['blocked']}"
            )

        lines.append("")
        lines.append("## Ready Nodes")
        if ready:
            for node in ready:
                blockers = self.blockers(node.id)
                blocker_text = ", ".join(blocker.id for blocker in blockers) or "-"
                lines.append(
                    f"{node.id} | downstream:{len(self.all_successors(node.id))} | "
                    f"blockers:{blocker_text} | {node.title}"
                )
        else:
            lines.append("none")

        for layer, label in (("R", "Requirements"), ("D", "Data"), ("F", "Files"), ("U", "UI")):
            subgraph = self._layer_subgraph(layer)
            if not subgraph.nodes:
                continue
            lines.append("")
            lines.append(f"### {label}")
            lines.append("```mermaid")
            lines.append(subgraph.to_mermaid().rstrip())
            lines.append("```")

        return "\n".join(lines)

    @staticmethod
    def merge(*graphs):
        result = Graph()
        for graph in graphs:
            if graph.version and not result.version:
                result.version = graph.version

            for node in graph.nodes.values():
                result.add_node(node, declared=True)

            for src, rel, dst in graph.edges:
                result.add_edge(src, rel, dst)

        return result

    @classmethod
    def from_object_model(cls, payload):
        graph = cls(version=payload.get("version"))

        for node_payload in payload.get("nodes", []):
            graph.add_node(Node.from_dict(node_payload), declared=True)

        for edge_payload in payload.get("edges", []):
            graph.add_edge(
                edge_payload["from"],
                edge_payload.get("type", "-->"),
                edge_payload["to"],
            )

        return graph


def node_report(graph, node_id):
    node = graph.get_node(node_id)
    if not node:
        return json_dump({"error": f"node not found: {node_id}"})

    blockers = graph.blockers(node_id)

    return json_dump(
        {
            "node": node.to_dict(),
            "in_degree": graph.in_degree(node_id),
            "out_degree": graph.out_degree(node_id),
            "can_execute": graph.can_execute(node_id),
            "is_ready": graph.is_ready(node_id),
            "blockers": [item.to_dict() for item in blockers],
            "direct_predecessors": [item.to_dict() for item in graph.direct_predecessors(node_id)],
            "all_predecessors": [item.to_dict() for item in graph.all_predecessors(node_id)],
            "direct_successors": [item.to_dict() for item in graph.direct_successors(node_id)],
            "all_successors": [item.to_dict() for item in graph.all_successors(node_id)],
            "next_after_done": [item.to_dict() for item in graph.next_after(node_id)],
        }
    )


def ready_report(graph):
    ready = graph.ready_nodes()
    return json_dump(
        {
            "version": graph.version,
            "ready_count": len(ready),
            "nodes": [
                {
                    **node.to_dict(),
                    "out_degree": graph.out_degree(node.id),
                    "downstream_count": len(graph.all_successors(node.id)),
                    "unlocks_after_done": [item.to_dict() for item in graph.next_after(node.id)],
                }
                for node in ready
            ],
        }
    )


def next_report(graph, node_id):
    return json_dump(
        {
            "node_id": node_id,
            "next_after_done": [item.to_dict() for item in graph.next_after(node_id)],
        }
    )


def progress_report(graph):
    progress = graph.progress()
    ready = graph.ready_nodes()
    return json_dump(
        {
            "version": graph.version,
            "progress": progress,
            "ready_count": len(ready),
            "ready_nodes": [node.id for node in ready],
        }
    )


def analysis_report(graph):
    degree = graph.degree_analysis()
    has_cycle, cycle = graph.detect_cycle()
    return json_dump(
        {
            "version": graph.version,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "duplicates": graph.duplicate_ids(),
            "in_degree_top": [{"node": nid, "degree": degree} for nid, degree in degree["in_degree_top"]],
            "out_degree_top": [{"node": nid, "degree": degree} for nid, degree in degree["out_degree_top"]],
            "isolated": degree["isolated"],
            "longest_path": graph.longest_path(),
            "has_cycle": has_cycle,
            "cycle": cycle,
            "coverage": graph.check_layer_coverage(),
            "ready_nodes": [node.id for node in graph.ready_nodes()],
        }
    )
