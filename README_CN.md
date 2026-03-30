[English](README.md) | [中文](README_CN.md)

# Mermaid Architect

**结构比能力更重要。给你的 AI 一张地图。**

我一直遇到同一个问题：Claude Code 在做大项目的时候会迷失，开始自相矛盾，
或者忘记自己已经做了什么。换更强的模型有一点帮助，加一个 DAG 帮助大得多。

这就是这个工具的由来。

---

## 它实际上做什么

你的项目变成一张图。每个任务是一个节点，依赖关系是边。
当你问 Claude Code "我下一步该做什么" 的时候，它调用 mermaid-architect，
拿回当前可执行的节点，认领一个，开始工作。不需要每次重新解释项目背景。

一个奇怪的发现：这对弱模型的帮助比强模型更大。结构化的图给弱模型
足够的上下文让它保持方向。没有这个，即使是强模型也会跑偏。

---

## 快速开始
```bash
# 安装
pip install -e .

# 加入 Claude Code（只需一次）
claude mcp add mermaid-architect mermaid-arch mcp .mermaid/current

# 生成项目图
export ANTHROPIC_API_KEY="你的key"
mermaid-arch init "你的项目描述"

# 启动可视化面板（可选）
python3 -m mermaid_architect.cli --api .mermaid/current/ --port 9001
cd graph-ui && npm install && npm run dev
```

然后直接和 Claude Code 说话：
```
"我下一步该做什么？"
"帮我认领 F-003，告诉我它需要什么"
"F-003 做完了，用了 8 分钟"
```

---

## Claude Code 获得的 5 个 MCP 工具

| 工具 | 作用 |
|---|---|
| `get_progress` | 项目整体进度 |
| `get_ready_nodes` | 当前可以执行的节点 |
| `get_context` | 某个节点的完整任务说明 |
| `claim_node` | 认领节点（防止多个 Agent 冲突）|
| `complete_node` | 标记完成，更新速度统计 |

---

## 四层模型

每个项目被拆解为：
- **R** — 用户能做什么（需求层）
- **D** — 数据结构和接口
- **F** — 具体实现文件
- **U** — 用户入口（CLI、UI）

DAG 强制执行顺序。D 没定义之前不能实现 F。
多个 Agent 可以同时在没有依赖关系的 F 节点上并行工作，互不干扰。

---

## 可视化面板（可选）

有一个基于 tldraw 的 UI，实时展示图的状态。
节点完成后变绿，新节点实时解锁。
不是必须的——CLI 和 MCP 工具没有它也能正常工作——
但在大项目里想看整体状态的时候很有用。

---

## CLI 命令
```bash
mermaid-arch init "描述"          # 用自然语言生成项目图
mermaid-arch work                 # 交互式任务循环
mermaid-arch context F-001        # 查看某节点的任务说明
mermaid-arch complete F-001 180   # 标记完成，用了 180 秒
mermaid-arch velocity             # 各层完成速度统计
mermaid-arch log                  # 最近 20 条图变更记录
```

---

## 为什么不直接用 task-master？

task-master 很适合线性任务列表。mermaid-architect 适合多个 Agent
并行工作且不产生冲突的场景。DAG 拓扑自动处理调度，你不需要想这些。

两者互补，不是竞争。task-master 做任务拆解，
mermaid-architect 在上面做并发执行层。

---

[Jinx](https://github.com/Zooeyii) 在试图让 Claude Code 
处理比周末项目更大的工程时做的。

MIT License
