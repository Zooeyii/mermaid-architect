"""
MCP Server for mermaid-architect, stdio transport.

Tools:
  get_progress(graph_dir)
  get_ready_nodes(graph_dir)
  get_context(graph_dir, node_id)
  claim_node(graph_dir, node_id, session)
  complete_node(graph_dir, node_id, seconds, success)
"""

import asyncio
import json
import os

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from mermaid_architect.models import progress_report, ready_report
from mermaid_architect.parser import load_source
from mermaid_architect.io import write_normalized_graph
from mermaid_architect.experience import get_velocity_estimate, record_completion


server = Server("mermaid-architect")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_progress",
            description="返回 graph 各层完成情况（done/todo/doing/blocked 计数）",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_dir": {"type": "string", "description": "graph 目录路径 (可选，默认使用初始化时的路径)"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_ready_nodes",
            description="返回当前可立即执行的节点列表（无 blocker、未认领）",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_dir": {"type": "string", "description": "graph 目录路径 (可选)"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_context",
            description="返回指定节点的完整任务 prompt，包含期望结果、TDD入口、前置依赖、速度参考",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_dir": {"type": "string", "description": "graph 目录路径 (可选)"},
                    "node_id": {"type": "string", "description": "节点 ID，如 F-001"},
                },
                "required": ["node_id"],
            },
        ),
        types.Tool(
            name="claim_node",
            description="认领节点，设置 status=doing 并绑定 session；节点已被认领返回错误",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_dir": {"type": "string", "description": "graph 目录路径 (可选)"},
                    "node_id": {"type": "string", "description": "节点 ID"},
                    "session": {"type": "string", "description": "session 标识符"},
                },
                "required": ["node_id", "session"],
            },
        ),
        types.Tool(
            name="complete_node",
            description="标记节点完成（或失败），更新 velocity 统计",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_dir": {"type": "string", "description": "graph 目录路径 (可选)"},
                    "node_id": {"type": "string", "description": "节点 ID"},
                    "seconds": {"type": "number", "description": "耗时秒数"},
                    "success": {"type": "boolean", "description": "是否成功，默认 true"},
                },
                "required": ["node_id", "seconds"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "get_progress":
        graph_dir = arguments.get("graph_dir") or os.environ.get("MERMAID_GRAPH_DIR", ".mermaid/current")
        graph = load_source(graph_dir)
        result = progress_report(graph)
        return [types.TextContent(type="text", text=result)]

    if name == "get_ready_nodes":
        graph_dir = arguments.get("graph_dir") or os.environ.get("MERMAID_GRAPH_DIR", ".mermaid/current")
        graph = load_source(graph_dir)
        result = ready_report(graph)
        return [types.TextContent(type="text", text=result)]

    if name == "get_context":
        graph_dir = arguments.get("graph_dir") or os.environ.get("MERMAID_GRAPH_DIR", ".mermaid/current")
        node_id = arguments["node_id"]
        graph = load_source(graph_dir)
        node = graph.get_node(node_id)
        if not node:
            return [types.TextContent(type="text", text=f"错误：节点不存在 {node_id}")]

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
        estimate = get_velocity_estimate(graph_dir, node.layer)
        lines.append(f"{node.layer}层历史平均: {estimate}")
        lines.append("")
        lines.append("## 注意事项")
        lines.append("暂无风险记录")

        return [types.TextContent(type="text", text="\n".join(lines))]

    if name == "claim_node":
        graph_dir = arguments.get("graph_dir") or os.environ.get("MERMAID_GRAPH_DIR", ".mermaid/current")
        node_id = arguments["node_id"]
        session = arguments["session"]

        graph = load_source(graph_dir)
        node = graph.get_node(node_id)

        if not node:
            return [types.TextContent(type="text", text=json.dumps({"ok": False, "error": f"节点不存在: {node_id}"}))]

        if node.session:
            return [types.TextContent(type="text", text=json.dumps({"ok": False, "error": "already claimed", "session": node.session}))]

        if not graph.can_execute(node_id):
            blockers = [b.id for b in graph.blockers(node_id)]
            return [types.TextContent(type="text", text=json.dumps({"ok": False, "error": "not ready", "blockers": blockers}))]

        node.session = session
        node.status = "doing"
        write_normalized_graph(graph_dir, graph)

        return [types.TextContent(type="text", text=json.dumps({"ok": True, "node_id": node_id, "session": session}))]

    if name == "complete_node":
        graph_dir = arguments.get("graph_dir") or os.environ.get("MERMAID_GRAPH_DIR", ".mermaid/current")
        node_id = arguments["node_id"]
        seconds = float(arguments["seconds"])
        success = bool(arguments.get("success", True))

        graph = load_source(graph_dir)
        node = graph.get_node(node_id)

        if not node:
            return [types.TextContent(type="text", text=json.dumps({"ok": False, "error": f"节点不存在: {node_id}"}))]

        node.status = "done" if success else "todo"
        node.session = None
        write_normalized_graph(graph_dir, graph)
        record_completion(graph_dir, node_id, node.layer, seconds, success=success)

        m = int(seconds) // 60
        outcome = "标记完成" if success else "标记失败"
        return [types.TextContent(type="text", text=json.dumps({"ok": True, "node_id": node_id, "outcome": outcome, "minutes": m}))]

    return [types.TextContent(type="text", text=f"错误：未知 tool: {name}")]


def run_mcp_server():
    async def _main():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_main())
