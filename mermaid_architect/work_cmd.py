from mermaid_architect.parser import load_source
from mermaid_architect.io import write_normalized_graph
from mermaid_architect.experience import record_completion, get_velocity_estimate


def _print_context(graph, node, source):
    tdd = node.tdd or {}
    preds = graph.direct_predecessors(node.id)

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


def run_work(graph_dir):
    source = graph_dir
    skipped = set()

    while True:
        graph = load_source(source)
        progress = graph.progress()
        overall = progress["overall"]
        done_count = overall["done"]
        total_count = overall["total"]
        ready_nodes = graph.ready_nodes()
        available = [n for n in ready_nodes if n.id not in skipped]

        print(f"\n📊 进度: {done_count}/{total_count} 完成 | 当前可执行: {len(available)}个")

        if not available:
            if not ready_nodes:
                print("🎉 所有任务已完成或无可执行任务。")
            else:
                print("所有可执行任务已跳过。")
            break

        node = available[0]
        print(f"⚡ 推荐任务: {node.id} {node.title or ''}")
        print()
        _print_context(graph, node, source)
        print()
        print("─" * 40)
        raw = input("[Enter] 完成  [f] 失败  [s] 跳过  [q] 退出\n> ").strip().lower()

        if raw == "q":
            print("已退出。")
            break
        elif raw == "s":
            skipped.add(node.id)
            continue
        elif raw == "f":
            graph = load_source(source)
            n = graph.get_node(node.id)
            n.status = "todo"
            n.session = None
            write_normalized_graph(source, graph)
            print(f"✗ {node.id} 标记失败")
            seconds_raw = input("用时（秒，可留空跳过）: ").strip()
            if seconds_raw:
                try:
                    seconds = float(seconds_raw)
                    record_completion(source, node.id, n.layer, seconds, success=False)
                    print("已更新velocity统计")
                except ValueError:
                    pass
        else:
            seconds_raw = input("用时（秒）: ").strip()
            seconds = 0.0
            if seconds_raw:
                try:
                    seconds = float(seconds_raw)
                except ValueError:
                    pass
            graph = load_source(source)
            n = graph.get_node(node.id)
            n.status = "done"
            n.session = None
            write_normalized_graph(source, graph)
            record_completion(source, node.id, n.layer, seconds, success=True)
            m = int(seconds) // 60
            print(f"✓ {node.id} 标记完成，用时{m}分钟，已更新velocity统计")
