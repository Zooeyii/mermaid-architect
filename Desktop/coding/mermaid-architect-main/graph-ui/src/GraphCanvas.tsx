import { Tldraw, defaultUserPreferences, useTldrawUser, type Editor, type TLShapeId } from 'tldraw'
import { useEffect, useMemo, useRef, useState } from 'react'

import { filterGraph, getGraphSyncKey, syncGraphToEditor, type GraphViewMode } from './graphShapes'
import type { Graph } from './types'

interface EventEntry {
  id: number
  time: string
  color: string
  text: string
  nodeId?: string
  agentColor?: string
}

function formatElapsed(ms: number) {
  const total = Math.floor(ms / 1000)
  const m = String(Math.floor(total / 60)).padStart(2, '0')
  const s = String(total % 60).padStart(2, '0')
  return `${m}:${s}`
}

function assignAgentColor(session: string, map: Map<string, string>): string {
  if (!map.has(session)) {
    map.set(session, AGENT_COLORS[map.size % AGENT_COLORS.length])
  }
  return map.get(session)!
}

const AGENT_COLORS = ['#4A9EFF', '#FF6B6B', '#51CF66', '#FAB005', '#CC5DE8']

// API 基础路径 (通过 vite proxy)
const API_BASE = '/api'

// 已知项目列表
const KNOWN_PROJECTS = [
  { id: 'mini', path: '.mermaid/current', label: 'mini (当前项目)' },
  // 添加更多项目: { id: 'happy', path: '../happy/.mermaid/current', label: 'happy' },
]

const LAYER_LEGEND = [
  { id: 'R', label: 'R', color: '#2f9e44' },
  { id: 'D', label: 'D', color: '#1c7ed6' },
  { id: 'F', label: 'F', color: '#e0a800' },
  { id: 'U', label: 'U', color: '#e03131' },
]

export function GraphCanvas() {
  const [graph, setGraph] = useState<Graph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [project, setProject] = useState(KNOWN_PROJECTS[0])
  const [viewMode, setViewMode] = useState<GraphViewMode>('all')
  const [viewValue, setViewValue] = useState<string>('')
  const editorRef = useRef<Editor | null>(null)
  const [editor, setEditor] = useState<Editor | null>(null)
  const prevGraphRef = useRef<Graph | null>(null)
  const eventIdRef = useRef(0)
  const claimedAtRef = useRef<Map<string, number>>(new Map())
  const stuckWarnedRef = useRef<Set<string>>(new Set())
  const sessionColorMapRef = useRef<Map<string, string>>(new Map())
  const [events, setEvents] = useState<EventEntry[]>([])
  const [tick, setTick] = useState(0)
  const lastProjectIdRef = useRef(project.id)
  const lastRenderedKeyRef = useRef('')
  const lastGraphVersionRef = useRef<string | null>(null)
  const lastViewportModeRef = useRef(`${project.id}:${viewMode}:${viewValue}`)
  const user = useTldrawUser({
    userPreferences: {
      ...defaultUserPreferences,
      locale: 'en',
    },
  })

  // 加载 graph
  useEffect(() => {
    setGraph(null)
    setError(null)
    fetch(`${API_BASE}/graph?dir=${encodeURIComponent(project.path)}`)
      .then(res => res.json())
      .then(data => {
        if (data.ok) {
          setGraph(data.graph)
        } else {
          setError(data.error || 'Failed to load graph')
        }
      })
      .catch(err => setError(err.message))
  }, [project])

  // SSE 订阅
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/graph/sse?dir=${encodeURIComponent(project.path)}`)
    es.onmessage = e => {
      const data = JSON.parse(e.data)
      if (data.graph) {
        setGraph(data.graph)
      }
    }
    es.onerror = () => {}
    return () => es.close()
  }, [project])

  // 状态变化检测
  useEffect(() => {
    if (!graph) return

    const prev = prevGraphRef.current
    const now = Date.now()

    if (!prev) {
      // 初始加载：追踪已在 doing 状态的节点
      const time = new Date().toTimeString().slice(0, 8)
      const initialEntries: EventEntry[] = []
      for (const node of graph.nodes) {
        if (node.status === 'doing') {
          claimedAtRef.current.set(node.id, now)
          const agentColor = node.session ? assignAgentColor(node.session, sessionColorMapRef.current) : undefined
          initialEntries.push({ id: ++eventIdRef.current, time, color: '#1c7ed6', text: `▶ claimed ${node.id}`, nodeId: node.id, agentColor })
        }
      }
      if (initialEntries.length > 0) {
        setEvents(initialEntries)
      }
    } else {
      const prevById = new Map(prev.nodes.map(n => [n.id, n]))
      const time = new Date().toTimeString().slice(0, 8)
      const newEntries: EventEntry[] = []

      for (const node of graph.nodes) {
        const prevNode = prevById.get(node.id)
        if (!prevNode || prevNode.status === node.status) continue

        if ((prevNode.status === 'todo' || prevNode.status === 'blocked') && node.status === 'doing') {
          claimedAtRef.current.set(node.id, now)
          const agentColor = node.session ? assignAgentColor(node.session, sessionColorMapRef.current) : undefined
          newEntries.push({ id: ++eventIdRef.current, time, color: '#1c7ed6', text: `▶ claimed ${node.id}`, nodeId: node.id, agentColor })
        } else if (prevNode.status === 'doing' && node.status === 'done') {
          claimedAtRef.current.delete(node.id)
          stuckWarnedRef.current.delete(node.id)
          newEntries.push({ id: ++eventIdRef.current, time, color: '#2f9e44', text: `✓ done ${node.id}` })
        } else if (prevNode.status === 'doing' && node.status === 'todo') {
          claimedAtRef.current.delete(node.id)
          stuckWarnedRef.current.delete(node.id)
          newEntries.push({ id: ++eventIdRef.current, time, color: '#e03131', text: `✗ failed ${node.id}` })
        }
      }

      if (newEntries.length > 0) {
        setEvents(prev => [...newEntries, ...prev].slice(0, 50))
      }
    }

    prevGraphRef.current = graph
  }, [graph])

  // 每秒 tick + 超时检测
  useEffect(() => {
    const id = setInterval(() => {
      setTick(t => t + 1)

      const now = Date.now()
      const time = new Date().toTimeString().slice(0, 8)
      const newEntries: EventEntry[] = []

      claimedAtRef.current.forEach((claimedAt, nodeId) => {
        if (!stuckWarnedRef.current.has(nodeId) && now - claimedAt >= 20 * 60 * 1000) {
          stuckWarnedRef.current.add(nodeId)
          newEntries.push({ id: ++eventIdRef.current, time, color: '#fd7e14', text: `⚠️ ${nodeId} stuck 20min` })
        }
      })

      if (newEntries.length > 0) {
        setEvents(prev => [...newEntries, ...prev].slice(0, 50))
      }
    }, 1000)
    return () => clearInterval(id)
  }, [])

  const [showArchived, setShowArchived] = useState(true)

  const graphView = useMemo(() => {
    if (!graph) {
      return null
    }

    const filtered = filterGraph(graph, {
      mode: viewMode,
      value: viewMode === 'all' ? null : viewValue || null,
    })

    if (showArchived) {
      return filtered
    }

    return {
      ...filtered,
      nodes: filtered.nodes.filter(n => !n.archived),
      edges: filtered.edges.filter(e => {
        const archivedIds = new Set(filtered.nodes.filter(n => n.archived).map(n => n.id))
        return !archivedIds.has(e.from) && !archivedIds.has(e.to)
      }),
    }
  }, [graph, viewMode, viewValue, showArchived])

  const graphSyncKey = useMemo(() => (
    graphView ? `${project.id}:${viewMode}:${viewValue}:${showArchived}:${getGraphSyncKey(graphView)}` : ''
  ), [graphView, project.id, viewMode, viewValue, showArchived])

  const doingShapeId = useMemo(() => {
    const doingNode = graphView?.nodes.find(n => n.status === 'doing' && !n.archived)
    return doingNode ? `shape:graph-node:${doingNode.id}` as TLShapeId : null
  }, [graphView])

  const [overlayBox, setOverlayBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null)

  useEffect(() => {
    if (!editor || !doingShapeId) {
      setOverlayBox(null)
      return
    }

    const updateBox = () => {
      const bounds = editor.getShapePageBounds(doingShapeId)
      if (!bounds) {
        setOverlayBox(null)
        return
      }
      const tl = editor.pageToViewport({ x: bounds.x, y: bounds.y })
      const zoom = editor.getZoomLevel()
      setOverlayBox({ x: tl.x, y: tl.y, w: bounds.w * zoom, h: bounds.h * zoom })
    }

    updateBox()
    return editor.store.listen(updateBox)
  }, [editor, doingShapeId])

  const filterOptions = useMemo(() => {
    if (!graph) {
      return []
    }

    switch (viewMode) {
      case 'milestone': {
        const labels = new Map<string, string>(Object.entries(graph.milestones ?? {}))
        graph.nodes.forEach(node => {
          if (node.milestone && !labels.has(node.milestone)) {
            labels.set(node.milestone, node.milestone)
          }
        })
        return Array.from(labels.entries()).map(([id, label]) => ({ id, label }))
      }
      case 'layer':
        return ['R', 'D', 'F', 'U'].map(layer => ({ id: layer, label: layer }))
      case 'node':
        return graph.nodes.map(node => ({ id: node.id, label: `${node.id} · ${node.title}` }))
      default:
        return []
    }
  }, [graph, viewMode])

  useEffect(() => {
    if (viewMode === 'all') {
      return
    }

    if (filterOptions.length === 0) {
      setViewValue('')
      return
    }

    if (!filterOptions.some(option => option.id === viewValue)) {
      setViewValue(filterOptions[0].id)
    }
  }, [filterOptions, viewMode, viewValue])

  useEffect(() => {
    if (!graphView || !editorRef.current) {
      return
    }

    if (lastRenderedKeyRef.current === graphSyncKey) {
      return
    }

    const viewportModeKey = `${project.id}:${viewMode}:${viewValue}`
    const shouldZoom = (
      lastProjectIdRef.current !== project.id ||
      lastGraphVersionRef.current !== graphView.version ||
      lastViewportModeRef.current !== viewportModeKey
    )
    syncGraphToEditor(editorRef.current, graphView, shouldZoom)
    lastProjectIdRef.current = project.id
    lastGraphVersionRef.current = graphView.version
    lastViewportModeRef.current = viewportModeKey
    lastRenderedKeyRef.current = graphSyncKey
  }, [graphSyncKey, graphView, project.id, viewMode, viewValue])

  if (error) {
    return (
      <div style={{ padding: 20, color: 'red' }}>
        Error: {error}
        <button onClick={() => setProject(KNOWN_PROJECTS[0])} style={{ marginLeft: 10 }}>
          Retry
        </button>
      </div>
    )
  }

  if (!graph || !graphView) {
    return <div style={{ padding: 20 }}>Loading {project.label}...</div>
  }

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>
      {/* 项目选择器 */}
      <div style={{
        position: 'absolute',
        top: 10,
        left: 10,
        zIndex: 1000,
        background: 'white',
        padding: '8px 12px',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}>
        <label>项目:</label>
        <select
          value={project.id}
          onChange={e => {
            const found = KNOWN_PROJECTS.find(p => p.id === e.target.value)
            if (found) setProject(found)
          }}
          style={{ padding: '4px 8px' }}
        >
          {KNOWN_PROJECTS.map(p => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
        <label>视图:</label>
        <select
          value={viewMode}
          onChange={e => {
            const nextMode = e.target.value as GraphViewMode
            setViewMode(nextMode)
            setViewValue('')
          }}
          style={{ padding: '4px 8px' }}
        >
          <option value="all">All</option>
          <option value="milestone">Milestone</option>
          <option value="layer">Layer</option>
          <option value="node">Focus Node</option>
        </select>
        {viewMode !== 'all' && filterOptions.length > 0 ? (
          <select
            value={viewValue}
            onChange={e => setViewValue(e.target.value)}
            style={{ padding: '4px 8px', maxWidth: 280 }}
          >
            {filterOptions.map(option => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
        ) : null}
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={e => setShowArchived(e.target.checked)}
          />
          归档
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#666' }}>
          {LAYER_LEGEND.map(item => (
            <span key={item.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{
                width: 8,
                height: 8,
                borderRadius: 999,
                background: item.color,
                display: 'inline-block',
              }} />
              {item.label}
            </span>
          ))}
          <span style={{ marginLeft: 4 }}>archive=淡色虚线</span>
        </div>
        <span style={{ color: '#666', fontSize: 12 }}>
          {graph.version} · {graphView.nodes.length}/{graph.nodes.length} nodes
        </span>
      </div>

      <Tldraw
        key={project.id}
        user={user}
        onMount={editor => {
          editorRef.current = editor
          setEditor(editor)
          lastRenderedKeyRef.current = ''
          syncGraphToEditor(editor, graphView, true)
          lastProjectIdRef.current = project.id
          lastGraphVersionRef.current = graphView.version
          lastViewportModeRef.current = `${project.id}:${viewMode}:${viewValue}`
          lastRenderedKeyRef.current = graphSyncKey
        }}
      />

      {overlayBox && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
        }}>
          <div style={{
            position: 'absolute',
            left: overlayBox.x,
            top: overlayBox.y,
            width: overlayBox.w,
            height: overlayBox.h,
            background: 'rgba(255, 0, 0, 0.35)',
            border: '2px solid red',
            boxSizing: 'border-box',
          }} />
        </div>
      )}

      {/* 事件面板 */}
      <div style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: 280,
        height: '100%',
        background: 'rgba(255,255,255,0.96)',
        borderLeft: '1px solid #e0e0e0',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 900,
        pointerEvents: 'auto',
      }}>
        <div style={{
          padding: '10px 14px',
          borderBottom: '1px solid #e0e0e0',
          fontWeight: 600,
          fontSize: 13,
          color: '#333',
          flexShrink: 0,
        }}>
          Events
        </div>
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '6px 0',
        }}>
          {events.length === 0 ? (
            <div style={{ padding: '12px 14px', fontSize: 12, color: '#aaa' }}>
              等待状态变化...
            </div>
          ) : (
            events.map(entry => (
              <div key={entry.id} style={{
                padding: '5px 14px',
                display: 'flex',
                gap: 10,
                alignItems: 'baseline',
                fontSize: 12,
              }}>
                <span style={{ color: '#aaa', flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
                  {entry.time}
                </span>
                <span style={{ color: entry.color, fontWeight: 500, flex: 1, display: 'flex', alignItems: 'center', gap: 5 }}>
                  {entry.agentColor && (
                    <span style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: entry.agentColor,
                      flexShrink: 0,
                      display: 'inline-block',
                      marginRight: 6,
                    }} />
                  )}
                  {entry.text}
                </span>
                {entry.nodeId && claimedAtRef.current.has(entry.nodeId) && (
                  <span style={{ color: '#888', flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
                    {formatElapsed(Date.now() - claimedAtRef.current.get(entry.nodeId)!)}
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
