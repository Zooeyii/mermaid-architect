"""
init_cmd.py — generate graph.json from a natural language description via Claude API.
"""

import json
import re

import anthropic

from mermaid_architect.models import Graph
from mermaid_architect.io import write_normalized_graph

SYSTEM_PROMPT = """
你是一个软件架构师，专门把项目描述拆解为四层 DAG 对象图。

输出格式：只输出合法 JSON，不要有任何解释文字、markdown、代码块。

JSON 结构：
{
  "version": "0.1.0",
  "nodes": [...],
  "edges": [...]
}

节点规则：
- id 格式：R-001, D-001, F-001, U-001，三位数字
- layer 只能是 R / D / F / U
- status 全部是 "todo"
- session 全部是 null
- 每个节点必须有 expected 字段（一句话描述完成标准）
- 每个节点必须有 tdd 字段：{"entry": "tests/test_xxx.py", "first_fail": "描述第一个失败用例"}

四层含义：
- R 层：需求，用户能做什么，2-4个节点
- D 层：数据结构和接口 schema，3-5个节点
- F 层：具体函数和文件实现，4-8个节点
- U 层：用户入口，CLI或UI，1-3个节点

边规则：
- R→D 用 "-.->（跨层映射）
- D→F 用 "-.->（跨层映射）
- 同层之间用 "-->"
- F→U 用 "-.->（跨层映射）
- 不能有环
- 不能有孤立节点

质量要求：
- R层每个节点至少有一条边连到D层
- D层每个节点至少有一条边连到F层
- F层最终连到U层
- ready节点（无前序依赖）只能是R层节点
"""

def run_init(description: str, output_dir: str) -> None:
    client = anthropic.Anthropic()

    print("calling API...")
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": description},
        ],
    )
    print("got response")

    raw = message.content[0].text
    print("raw response:", raw)

    # 从响应里提取 JSON（兼容 Claude 用 ```json ... ``` 包裹的情况）
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    json_text = match.group(1).strip() if match else raw.strip()

    payload = json.loads(json_text)

    # 兼容 API 返回 name 字段而非 title
    for node in payload.get("nodes", []):
        if "title" not in node and "name" in node:
            node["title"] = node.pop("name")

    graph = Graph.from_object_model(payload)

    write_normalized_graph(output_dir, graph)
    print(f"graph.json written to {output_dir}")
