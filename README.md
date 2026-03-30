[English](README.md) | [中文](README_CN.md)

# Mermaid Architect

**Structure beats capability. Give your AI a map.**

I kept running into the same wall: Claude Code would lose context halfway through 
a big project, start contradicting itself, or just forget what it had already done.
Switching to a stronger model helped a little. Adding a DAG helped a lot more.

That's what this is.

---

## What it actually does

Your project becomes a graph. Every task is a node. Dependencies are edges.
When you ask Claude Code "what should I work on next?" — it calls mermaid-architect,
gets back the current ready nodes, claims one, and starts working. No context dumping.
No "here's everything I know about this project" preambles.

The weird finding: this helps weaker models more than stronger ones. A well-structured
graph gives a weaker model enough context to stay on track. Without it, even strong
models drift.

---

## Quick start
```bash
# Install
pip install -e .

# Add to Claude Code (one time)
claude mcp add mermaid-architect mermaid-arch mcp .mermaid/current

# Generate a project graph
export ANTHROPIC_API_KEY="your-key"
mermaid-arch init "your project description"

# Start the visual dashboard (optional)
python3 -m mermaid_architect.cli --api .mermaid/current/ --port 9001
cd graph-ui && npm install && npm run dev
```

Then just talk to Claude Code normally:
```
"What should I work on next?"
"Claim F-003 for me and show me what it needs"
"Mark F-003 as done, took me 8 minutes"
```

---

## The 5 MCP tools Claude Code gets

| Tool | What it does |
|---|---|
| `get_progress` | How far along is the project |
| `get_ready_nodes` | What can be worked on right now |
| `get_context` | Full task brief for a specific node |
| `claim_node` | Lock a node to a session (no conflicts) |
| `complete_node` | Mark done, update velocity stats |

---

## The four-layer model

Every project gets broken into:
- **R** — what users can do (requirements)
- **D** — data shapes and interfaces  
- **F** — actual implementation files
- **U** — entry points (CLI, UI)

The DAG enforces the order. You can't implement F before D is defined.
Multiple agents can work on independent F nodes simultaneously without stomping on each other.

---

## Visual dashboard (optional)

There's a tldraw-based UI that shows the live state of your graph.
Nodes turn green as they complete. New nodes unlock in real time.
You don't need it — the CLI and MCP tools work without it — but it's
useful when you want to see what's happening across a big project.

---

## CLI reference
```bash
mermaid-arch init "description"     # generate graph from natural language
mermaid-arch work                   # interactive task loop
mermaid-arch context F-001          # get task brief for a node  
mermaid-arch complete F-001 180     # mark done, 180 seconds
mermaid-arch velocity               # completion stats by layer
mermaid-arch log                    # last 20 graph changes
```

---

## Why not just use task-master?

task-master is great for linear task lists. mermaid-architect is for when you want
multiple agents working in parallel without conflicts. The DAG topology handles
the scheduling — you don't have to think about it.

They're complementary, not competing. task-master for the task breakdown,
mermaid-architect for the concurrent execution layer on top.

---

Built by [Jinx](https://github.com/Zooeyii) while trying to make Claude Code 
work on projects bigger than a weekend hack.

MIT License
