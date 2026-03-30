"""
Mermaid Architect - object graph query tool.

Source of truth:
  - Prefer .mermaid/current/graph.json
  - Fallback to parsing .mmd files and normalizing into object form

Usage:
  python3 merge_graph.py --serve .mermaid/current/           # Start DAG visualization UI (port 5173)
  python3 merge_graph.py --serve .mermaid/current/ --port 5174  # Custom port
  python3 merge_graph.py --api .mermaid/current/ --port 9001     # API only (for dev)
  python3 merge_graph.py --merge-all .mermaid/current/
  python3 merge_graph.py --normalize .mermaid/current/
  python3 merge_graph.py --node F-003 .mermaid/current/
  python3 merge_graph.py --ready .mermaid/current/
  python3 merge_graph.py --next F-003 .mermaid/current/
  python3 merge_graph.py --progress .mermaid/current/
  python3 merge_graph.py --analyze .mermaid/current/
  python3 merge_graph.py --validate .mermaid/current/
"""

import sys
import json
from pathlib import Path

from mermaid_architect.models import (
    Graph,
    json_dump,
    node_report,
    ready_report,
    next_report,
    progress_report,
    analysis_report,
)

from mermaid_architect.parser import load_source

from mermaid_architect.io import write_normalized_graph, safe_write_graph

from mermaid_architect.server import serve

def print_usage():
    print(__doc__.strip())


def parse_optional_port(args, default_port=9000):
    remaining = []
    port = default_port
    index = 0

    while index < len(args):
        token = args[index]
        if token == "--port":
            if index + 1 >= len(args):
                raise ValueError("--port requires a value")
            port = int(args[index + 1])
            index += 2
            continue
        remaining.append(token)
        index += 1

    return remaining, port


def main():
    args = sys.argv[1:]
    if not args:
        print_usage()
        return

    command = args[0]

    if command in ("-h", "--help", "help"):
        print_usage()
        return

    if command == "--serve":
        remaining, port = parse_optional_port(args[1:], default_port=5173)
        source = remaining[0] if remaining else ".mermaid/current/"
        serve(source, port=port, api_only=False)
        return

    if command == "--api":
        remaining, port = parse_optional_port(args[1:], default_port=9001)
        source = remaining[0] if remaining else ".mermaid/current/"
        serve(source, port=port, api_only=True)
        return

    if command == "--merge-all":
        source = args[1] if len(args) > 1 else ".mermaid/current/"
        print(load_source(source).full_summary())
        return

    if command == "--normalize":
        source = args[1] if len(args) > 1 else ".mermaid/current/"
        graph = load_source(source)
        if Path(source).is_dir():
            write_normalized_graph(source, graph)
        print(json_dump(graph.to_object_model()))
        return

    if command == "--node":
        if len(args) < 2:
            raise ValueError("--node requires a node id")
        node_id = args[1]
        source = args[2] if len(args) > 2 else ".mermaid/current/"
        print(node_report(load_source(source), node_id))
        return

    if command == "--ready":
        source = args[1] if len(args) > 1 else ".mermaid/current/"
        print(ready_report(load_source(source)))
        return

    if command == "--next":
        if len(args) < 2:
            raise ValueError("--next requires a node id")
        node_id = args[1]
        source = args[2] if len(args) > 2 else ".mermaid/current/"
        print(next_report(load_source(source), node_id))
        return

    if command == "--progress":
        source = args[1] if len(args) > 1 else ".mermaid/current/"
        print(progress_report(load_source(source)))
        return

    if command == "--analyze":
        source = args[1] if len(args) > 1 else ".mermaid/current/"
        print(analysis_report(load_source(source)))
        return

    if command == "--validate":
        source = args[1] if len(args) > 1 else ".mermaid/current/"
        graph = load_source(source)
        issues = graph.validate_issues()
        if issues:
            print("ISSUES FOUND:")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)
        print("OK")
        return

    if command == "complete":
        if len(args) < 3:
            raise ValueError("complete requires <node_id> <seconds>")
        node_id = args[1]
        seconds = float(args[2])
        failed = "--failed" in args
        remaining = [a for a in args[3:] if a != "--failed"]
        source = remaining[0] if remaining else ".mermaid/current"

        from mermaid_architect.parser import load_source
        from mermaid_architect.io import write_normalized_graph
        from mermaid_architect.experience import record_completion

        graph = load_source(source)
        node = graph.get_node(node_id)
        if not node:
            print(f"Node not found: {node_id}")
            sys.exit(1)

        node.status = "todo" if failed else "done"
        node.session = None
        write_normalized_graph(source, graph)
        print(f"[debug] record_completion({source!r}, {node_id!r}, {node.layer!r}, {seconds}, success={not failed})")
        record_completion(source, node_id, node.layer, seconds, success=not failed)

        m = int(seconds) // 60
        outcome = "标记失败" if failed else "标记完成"
        print(f"{'✗' if failed else '✓'} {node_id} {outcome}，用时{m}分钟，已更新velocity统计")
        return

    if command == "context":
        if len(args) < 2:
            raise ValueError("context requires a node_id")
        node_id = args[1]
        source = args[2] if len(args) > 2 else ".mermaid/current"
        from mermaid_architect.parser import load_source
        from mermaid_architect.experience import get_velocity_estimate
        graph = load_source(source)
        node = graph.get_node(node_id)
        if not node:
            print(f"Node not found: {node_id}")
            sys.exit(1)

        tdd = node.tdd or {}
        preds = graph.direct_predecessors(node_id)

        lines = []
        lines.append("## 任务")
        lines.append(f"节点 {node.id}: {node.title or '（无标题）'}")
        lines.append(f"期望结果: {node.expected or '（未定义）'}")
        lines.append(f"TDD入口: {tdd.get('entry', '（未定义）')}")
        lines.append(f"第一个失败用例: {tdd.get('first_fail', '（未定义）')}")
        lines.append("")
        lines.append("## 前置依赖")
        if preds:
            for pred in preds:
                lines.append(f"- {pred.id} [{pred.status}] {pred.title or ''}")
        else:
            lines.append("- 无")
        lines.append("")
        lines.append("## 速度参考")
        estimate = get_velocity_estimate(source, node.layer)
        lines.append(f"{node.layer}层历史平均: {estimate}")
        lines.append("")
        lines.append("## 注意事项")
        lines.append("暂无风险记录")

        print("\n".join(lines))
        return

    if command == "velocity":
        source = args[1] if len(args) > 1 else ".mermaid/current"
        velocity_path = Path(source).parent / "experience" / "velocity.json"
        if not velocity_path.exists():
            print("No velocity data found.")
            return
        data = json.loads(velocity_path.read_text(encoding="utf-8"))
        by_layer = data.get("by_layer", {})
        if not by_layer:
            print("No layer data yet.")
            return
        for layer in ("R", "D", "F", "U"):
            if layer not in by_layer:
                continue
            entry = by_layer[layer]
            total = int(entry.get("avg_seconds", 0))
            m, s = divmod(total, 60)
            success_pct = int(entry.get("success_rate", 0) * 100)
            count = entry.get("count", 0)
            print(f"{layer}层: 平均{m}分{s:02d}秒 | 成功率{success_pct}% | 样本数{count}")
        return

    if command == "log":
        source = args[1] if len(args) > 1 else ".mermaid/current/"
        log_path = Path(source) / "evolution-log.json"
        if not log_path.exists():
            print("No evolution log found.")
            return
        log = json.loads(log_path.read_text(encoding="utf-8"))
        history = log.get("history", [])[-20:]
        for entry in reversed(history):
            print(f"\n[{entry['ts']}]")
            for change in entry.get("changes", []):
                ctype = change["type"]
                if ctype in ("status", "session", "title", "layer"):
                    print(f"  {ctype:10s} {change['nodeId']:10s} {change['from']} → {change['to']}")
                elif ctype == "node_added":
                    print(f"  {'node_added':10s} {change['nodeId']}")
                elif ctype == "node_removed":
                    print(f"  {'node_removed':10s} {change['nodeId']}")
                elif ctype in ("edge_added", "edge_removed"):
                    print(f"  {ctype:10s} {change['from']} → {change['to']}")
        return

    if command == "mcp":
        source = args[1] if len(args) > 1 else ".mermaid/current"
        from mermaid_architect.mcp_server import run_mcp_server
        import os
        os.environ.setdefault("MERMAID_GRAPH_DIR", source)
        run_mcp_server()
        return

    if command == "work":
        source = args[1] if len(args) > 1 else ".mermaid/current"
        from mermaid_architect.work_cmd import run_work
        run_work(source)
        return

    if command == "init":
        if len(args) < 2:
            raise ValueError("init requires a description string")
        description = args[1]
        output_dir = args[2] if len(args) > 2 else ".mermaid/current/"
        from mermaid_architect.init_cmd import run_init
        run_init(description, output_dir)
        return

    raise ValueError(f"unknown command: {command}")


def test_concurrent_write():
    import threading
    import tempfile
    import shutil

    def worker(d, index):
        g = Graph()
        for j in range(10):
            g.add_node(f"N{index}-{j}", title=f"Node {index}-{j}")
        safe_write_graph(d, g)

    d = tempfile.mkdtemp()
    try:
        threads = [threading.Thread(target=worker, args=(d, i)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        p = Path(d) / "graph.json"
        if not p.exists():
            print("graph.json not found!")
            return False

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"Test passed! Valid JSON. Node count: {len(data.get('nodes', []))}")
        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_concurrent_write()
        sys.exit(0)
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
