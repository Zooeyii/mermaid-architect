---
name: mermaid-architect
description: Mermaid DAG 驱动的设计与执行 Skill。用于新需求拆解、四层 DAG 更新、节点对象化、依赖查询、执行进度判断、下一个可执行节点推导，以及多 sub-agent 并发调度。当用户说“新需求”“设计”“架构”“拆解”“进度如何”“这个节点能不能执行”“前序依赖是什么”“下一个做什么”“/mermaid-architect”时触发。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, WebSearch, WebFetch
---

# Mermaid Architect

Mermaid 不是唯一真相源。**对象图才是唯一真相源，Mermaid 是渲染视图。**

旧模型里，`A --> B` 只是依赖事实。这个仍然成立，但只靠边集合不够，因为执行系统还需要：

- 节点编号
- 节点状态
- 节点 session claim
- 节点的前序 / 后续查询
- 节点是否可执行
- 当前 ready 集合
- 完成某节点后会解锁谁

所以这个 skill 的核心模型是：

```text
Object Graph = Node objects + Edge objects + Query functions
Mermaid = render(Object Graph)
```

## 1. 真相源

优先使用：

```text
.mermaid/current/graph.json
```

如果只有 `.mmd` 文件，没有 `graph.json`：

1. 先解析 `.mmd`
2. 立刻归一化成对象图
3. 后续所有分析、执行、并发调度都基于对象图
4. Mermaid 只作为同步输出视图

**不要只靠 `.mmd` 文本直接做执行判断。**

## 2. 节点对象模型

每个节点必须有稳定编号，编号是主键。

```json
{
  "id": "F-010",
  "title": "Implement graph query API",
  "layer": "F",
  "status": "todo",
  "session": null,
  "kind": "function",
  "file": "scripts/merge_graph.py",
  "functions": ["node_report", "ready_nodes"],
  "tdd": {
    "entry": "tests/test_merge_graph.py",
    "first_fail": "querying unknown node returns error",
    "expected": "json error payload"
  },
  "expected": "Can answer predecessor/successor/progress queries",
  "metadata": {
    "priority": "high"
  }
}
```

要求：

- `id` 必填，且唯一
- `title` 必填
- `layer` 必填，只能是 `R / D / F / U`
- `status` 必填，只能是 `todo / doing / blocked / done`
- `session` 可空，用于并发 claim
- `tdd` 建议必填
- 其他字段可扩展，但不能破坏上面这些基础字段

编号规则：

- `R-001` 需求层
- `D-001` 数据层
- `F-001` 文件/函数层
- `U-001` UI 层

## 3. 边对象模型

```json
{
  "from": "D-006",
  "to": "F-010",
  "type": "-.->",
  "reason": "data contract maps to implementation surface"
}
```

约束：

- `-->` 同层依赖
- `-.->` 跨层映射
- `==>` 保留给强约束或门禁

## 4. 必须具备的查询函数

任何实现这个 skill 的工具层，都必须能回答下面的问题：

1. `get_node(node_id)`
2. `direct_predecessors(node_id)`
3. `all_predecessors(node_id)`
4. `direct_successors(node_id)`
5. `all_successors(node_id)`
6. `blockers(node_id)`
7. `can_execute(node_id)`
8. `ready_nodes()`
9. `next_after(node_id)`
10. `progress()`

这 10 个函数是执行模式的最小接口。

### 4.1 决策含义

- “执行到了 `F-010`”：
  - 用 `get_node(F-010)`
- “它前面依赖有哪些”：
  - 用 `direct_predecessors(F-010)` 和 `all_predecessors(F-010)`
- “是否能执行”：
  - 用 `blockers(F-010)` 和 `can_execute(F-010)`
- “下一个该做什么”：
  - 用 `ready_nodes()`；如果 `F-010` 刚完成，再看 `next_after(F-010)`
- “现在整体进度如何”：
  - 用 `progress()`

## 5. 工具契约

优先使用 bundled script：

```bash
python3 scripts/merge_graph.py --serve .mermaid/current/ --port 9000
python3 scripts/merge_graph.py --node F-010 .mermaid/current/
python3 scripts/merge_graph.py --ready .mermaid/current/
python3 scripts/merge_graph.py --next F-010 .mermaid/current/
python3 scripts/merge_graph.py --progress .mermaid/current/
python3 scripts/merge_graph.py --normalize .mermaid/current/
python3 scripts/merge_graph.py --validate .mermaid/current/
```

当 skill 被触发，默认先启动本地查询服务：

```bash
python3 scripts/merge_graph.py --serve .mermaid/current/ --port 9000
```

约定：

- 默认监听 `127.0.0.1:9000`
- 如果用户没指定端口，就固定用 `9000`
- 后续查询优先走本地服务，再回退到 CLI

HTTP 接口：

- `GET /health`
- `GET /summary`
- `GET /node/<id>`
- `GET /ready`
- `GET /next/<id>`
- `GET /progress`
- `GET /analyze`
- `GET /validate`
- `POST /normalize`

规则：

- `--serve` 必须启动对象图查询服务，默认端口 `9000`
- `--node` 必须返回节点对象、前序、后续、blockers、能否执行
- `--ready` 必须返回当前可执行节点集合
- `--next` 必须返回某节点完成后会解锁的节点
- `--progress` 必须返回每层进度和 ready 集合
- `--normalize` 必须输出对象图 JSON
- `--validate` 必须检查 DAG、孤立节点、跨层断裂、重复编号

## 6. 两种模式

```text
Plan/Update  <->  Execution
```

### 模式 A: Plan/Update

何时进入：

- 新需求
- 用户要求设计 / 拆解 / 架构
- 发现依赖矛盾
- 图不完整
- 需要调研后再定图

允许：

- WebSearch / WebFetch 调研
- 读代码和文档
- 修改对象图
- 生成 Mermaid diff 和完整视图
- 做多方案拓扑对比
- 锁定 TDD 接口

不允许：

- 写实现代码
- 跳过图直接开工

#### Plan/Update 流程

1. 启动服务：`python3 scripts/merge_graph.py --serve .mermaid/current/ --port 9000`
2. 读取 `graph.json`；若不存在则先 `normalize`
2. 输出当前摘要：节点数、边数、ready 数、关键路径
3. 写需求理解
4. 生成四层 DAG diff
5. 做高杠杆分析
6. 给至少 2 套拓扑方案
7. 锁定新增节点的 TDD
8. 用户确认后写回对象图
9. 渲染更新后的完整 Mermaid

### 模式 B: Execution

何时进入：

- 对象图已确认
- 当前节点已具备完整依赖信息

允许：

- 严格按对象图执行
- 写测试
- 写实现
- 更新节点状态
- 更新 session claim

不允许：

- 执行图里不存在的工作
- 跳过未完成依赖
- 私自改 DAG 结构

#### Execution 流程

1. 确认服务运行在 `127.0.0.1:9000`
2. 读取 `ready_nodes()`
2. 选择未被 claim 的 ready 节点
3. 用 `blockers(node_id)` 二次确认
4. claim 节点：`status=doing`，写入 `session`
5. 跑 TDD 的首个失败用例
6. 实现
7. 验证
8. 标记 `done`
9. 查看 `next_after(node_id)` 和新的 `ready_nodes()`

## 7. Sub-agent 并发协议

并发不是“大家一起改”，而是“大家只拿 ready 节点”。

调度规则：

1. 先拿 `ready_nodes()`
2. 去掉已被其他 session claim 的节点
3. 每个 sub-agent 只拿一个节点或一组互不依赖的 ready 节点
4. sub-agent 开工前必须拿到：
   - 节点对象
   - 直接前序
   - 传递前序摘要
   - blockers
   - TDD 入口
   - expected
5. sub-agent 结束后只回传：
   - 节点状态变化
   - 新增 / 删除边
   - 新增 / 修改节点对象

如果执行中发现矛盾：

1. 停止当前节点
2. 记录矛盾
3. 切回 Plan/Update
4. 改对象图
5. 重新计算 ready 集合

## 8. 输出要求

每次图发生变化后，必须持久化两类产物：

1. 对象图
   - `graph.json`
2. 渲染视图
   - `requirements.mmd`
   - `data.mmd`
   - `files-functions.mmd`
   - `ui.mmd`

对话中的输出不必每次贴全图，但必须至少给：

- 当前版本
- 当前节点数 / 边数
- ready 节点
- 当前执行节点
- blockers
- 下一个推荐节点

## 9. 质量门禁

- [ ] 每个节点都有唯一编号
- [ ] 每个节点都能对象化
- [ ] 每个节点都能查询前序和后续
- [ ] `can_execute(node)` 不是猜的，而是由 blockers 计算出来
- [ ] ready 集合可直接用于 sub-agent 调度
- [ ] 无环
- [ ] 无孤立节点，除非明确声明
- [ ] 跨层链路不断裂：`R -> D -> F -> U`
- [ ] 新增节点都有 TDD

## 10. 快速判断

当用户问这些话时，默认进入对应动作：

- “设计一下新需求”
  - Plan/Update
- “这个节点现在能做吗”
  - `GET /node/<id>`，回退 `--node <id>`
- “现在进度如何”
  - `GET /progress`，回退 `--progress`
- “接下来做什么”
  - `GET /ready`，回退 `--ready`
- “做完 F-010 后谁会被解锁”
  - `GET /next/F-010`，回退 `--next F-010`
- “找几个 sub agents 并行干”
  - 先取 `ready_nodes()`，再按 claim 状态分配

## 11. 可视化（DAG UI）

**每次触发 /mermaid-architect 时，第一步必须启动 DAG 可视化。**

### 启动命令

```bash
# 方式一：直接启动完整 UI（默认端口 5173，自动打开浏览器）
python3 ~/.claude/skills/mermaid-architect/scripts/merge_graph.py \
  --serve .mermaid/current/

# 方式二：自定义端口
python3 ~/.claude/skills/mermaid-architect/scripts/merge_graph.py \
  --serve .mermaid/current/ --port 5174

# 方式三：仅 API 模式（开发时使用）
python3 ~/.claude/skills/mermaid-architect/scripts/merge_graph.py \
  --api .mermaid/current/ --port 9001
```

### 功能说明

| 端点 | 说明 |
|------|------|
| `GET /api/graph?dir=...` | 获取合并后的 graph（含归档节点） |
| `GET /api/graph/sse?dir=...` | SSE 推送，graph.json 变化后 1s 内自动刷新 |
| `GET /health` | 健康检查 |

### UI 功能

- **实时更新**：graph.json 变化后 1s 内自动刷新
- **过滤视图**：All / Milestone / Layer / Focus Node
- **归档显示**：归档节点半透明、虚线边框
- **交互**：tldraw 画布，支持拖拽、缩放

### 触发后输出格式

> DAG 可视化已启动 → http://localhost:5173
> （若端口被占用，使用 --port 5174）

### 停止服务

`Ctrl+C` 终止 Python 进程。
