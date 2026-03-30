import dagre from '@dagrejs/dagre'
import { Editor, toRichText } from 'tldraw'

import type { Graph, GraphEdge, GraphNode } from './types'

const NODE_WIDTH = 240
const NODE_HEIGHT = 104
const GRAPH_NODE_SHAPE_PREFIX = 'shape:graph-node:'
const GRAPH_EDGE_SHAPE_PREFIX = 'shape:graph-edge:'

export type GraphViewMode = 'all' | 'milestone' | 'layer' | 'node'

export interface GraphViewFilter {
  mode: GraphViewMode
  value: string | null
}

interface PositionedNode {
  node: GraphNode
  x: number
  y: number
}

interface GraphBindingRecord {
  type: 'arrow'
  fromId: string
  toId: string
  props: {
    terminal: 'start' | 'end'
    isExact: boolean
    isPrecise: boolean
    normalizedAnchor: {
      x: number
      y: number
    }
  }
}

const LAYER_COLORS: Record<GraphNode['layer'], 'green' | 'blue' | 'yellow' | 'red'> = {
  R: 'green',
  D: 'blue',
  F: 'yellow',
  U: 'red',
}

function getNodeLabel(node: GraphNode) {
  const prefix = node.archived ? '✓ ' : ''
  return `${prefix}${node.id}\n${node.title.slice(0, 44)}\n[${node.status}]`
}

function getNodeColor(node: GraphNode): 'green' | 'blue' | 'yellow' | 'red' {
  return LAYER_COLORS[node.layer]
}

function getNodeShapeId(nodeId: string) {
  return `${GRAPH_NODE_SHAPE_PREFIX}${nodeId}`
}

function getEdgeShapeId(edge: GraphEdge) {
  return `${GRAPH_EDGE_SHAPE_PREFIX}${edge.from}:${edge.to}`
}

function isManagedGraphShapeId(shapeId: string) {
  return shapeId.startsWith(GRAPH_NODE_SHAPE_PREFIX) || shapeId.startsWith(GRAPH_EDGE_SHAPE_PREFIX)
}

function getNodeFill(node: GraphNode) {
  if (node.archived) {
    return 'semi'
  }

  switch (node.status) {
    case 'done':
      return 'semi'
    case 'doing':
      return 'solid'
    default:
      return 'none'
  }
}

function getNodeDash(node: GraphNode) {
  if (node.archived) {
    return 'dotted'
  }
  return node.status === 'blocked' ? 'dashed' : 'solid'
}

function getNodeOpacity(node: GraphNode) {
  if (node.archived) {
    return 0.42
  }

  switch (node.status) {
    case 'doing':
      return 1
    case 'done':
      return 0.78
    default:
      return 0.92
  }
}

function getViewNodeIds(graph: Graph, filter: GraphViewFilter) {
  if (filter.mode === 'all' || !filter.value) {
    return new Set(graph.nodes.map(node => node.id))
  }

  if (filter.mode === 'milestone') {
    return new Set(graph.nodes.filter(node => node.milestone === filter.value).map(node => node.id))
  }

  if (filter.mode === 'layer') {
    return new Set(graph.nodes.filter(node => node.layer === filter.value).map(node => node.id))
  }

  const relatedNodeIds = new Set<string>([filter.value])
  graph.edges.forEach(edge => {
    if (edge.from === filter.value || edge.to === filter.value) {
      relatedNodeIds.add(edge.from)
      relatedNodeIds.add(edge.to)
    }
  })
  return relatedNodeIds
}

export function filterGraph(graph: Graph, filter: GraphViewFilter): Graph {
  const nodeIds = getViewNodeIds(graph, filter)
  const nodes = graph.nodes.filter(node => nodeIds.has(node.id))
  const edges = graph.edges.filter(edge => nodeIds.has(edge.from) && nodeIds.has(edge.to))

  return {
    ...graph,
    nodes,
    edges,
  }
}

export function getGraphSyncKey(graph: Graph) {
  const nodeKey = graph.nodes
    .map(node => `${node.id}:${node.status}:${node.session ?? ''}:${node.archived ? 'a' : 'l'}`)
    .join('|')
  const edgeKey = graph.edges
    .map(edge => `${edge.from}->${edge.to}:${edge.type}`)
    .join('|')

  return `${graph.version}::${nodeKey}::${edgeKey}`
}

function layoutGraph(graph: Graph) {
  const layout = new dagre.graphlib.Graph()

  layout.setGraph({
    rankdir: 'LR',
    nodesep: 56,
    ranksep: 120,
    marginx: 48,
    marginy: 48,
  })
  layout.setDefaultEdgeLabel(() => ({}))

  graph.nodes.forEach(node => {
    layout.setNode(node.id, {
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      layer: node.layer,
    })
  })

  graph.edges.forEach(edge => {
    if (edge.type === '-.->')  return
    layout.setEdge(edge.from, edge.to, {
      minlen: edge.type === '==>' ? 2 : 1,
      weight: edge.type === '-->' ? 2 : 1,
    })
  })

  dagre.layout(layout)

  return new Map<string, PositionedNode>(
    graph.nodes.map(node => {
      const position = layout.node(node.id)
      return [
        node.id,
        {
          node,
          x: position.x - NODE_WIDTH / 2,
          y: position.y - NODE_HEIGHT / 2,
        },
      ]
    })
  )
}

function createNodeShape({ node, x, y }: PositionedNode) {
  return {
    id: getNodeShapeId(node.id),
    type: 'geo' as const,
    x,
    y,
    opacity: getNodeOpacity(node),
    props: {
      geo: 'rectangle' as const,
      w: NODE_WIDTH,
      h: NODE_HEIGHT,
      color: getNodeColor(node),
      labelColor: 'black' as const,
      fill: getNodeFill(node),
      dash: getNodeDash(node),
      size: 's' as const,
      font: 'mono' as const,
      align: 'middle' as const,
      verticalAlign: 'middle' as const,
      richText: toRichText(getNodeLabel(node)),
      url: '',
      growY: 0,
      scale: 1,
    },
    meta: {
      graphManaged: true,
      nodeId: node.id,
      layer: node.layer,
      status: node.status,
      milestone: node.milestone ?? null,
      archived: node.archived ?? false,
    },
  }
}

function getAnchor(from: PositionedNode, to: PositionedNode, terminal: 'start' | 'end') {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const horizontal = Math.abs(dx) >= Math.abs(dy)

  if (horizontal) {
    if (terminal === 'start') {
      return dx >= 0 ? { x: 1, y: 0.5 } : { x: 0, y: 0.5 }
    }
    return dx >= 0 ? { x: 0, y: 0.5 } : { x: 1, y: 0.5 }
  }

  if (terminal === 'start') {
    return dy >= 0 ? { x: 0.5, y: 1 } : { x: 0.5, y: 0 }
  }
  return dy >= 0 ? { x: 0.5, y: 0 } : { x: 0.5, y: 1 }
}

function createEdgeShape(edge: GraphEdge, from: PositionedNode, to: PositionedNode) {
  const startAnchor = getAnchor(from, to, 'start')
  const endAnchor = getAnchor(from, to, 'end')
  const startX = from.x + NODE_WIDTH * startAnchor.x
  const startY = from.y + NODE_HEIGHT * startAnchor.y
  const isArchived = Boolean(from.node.archived || to.node.archived)
  const edgeColor = isArchived
    ? 'grey'
    : edge.type === '==>'
      ? 'red'
      : edge.type === '-.->'
        ? 'blue'
        : 'black'

  return {
    id: getEdgeShapeId(edge),
    type: 'arrow' as const,
    x: startX,
    y: startY,
    opacity: isArchived ? 0.28 : edge.type === '-->' ? 0.72 : 0.62,
    props: {
      kind: 'elbow' as const,
      color: edgeColor,
      labelColor: isArchived ? 'grey' as const : 'black' as const,
      fill: 'none' as const,
      dash: isArchived ? 'dotted' as const : edge.type === '-.->' ? 'dashed' as const : 'solid' as const,
      size: 's' as const,
      arrowheadStart: 'none' as const,
      arrowheadEnd: edge.type === '==>' ? 'triangle' as const : 'arrow' as const,
      font: 'mono' as const,
      start: { x: 0, y: 0 },
      end: { x: 0, y: 0 },
      bend: 0,
      richText: toRichText(edge.reason ?? ''),
      labelPosition: 0.5,
      scale: 1,
      elbowMidPoint: 0.5,
    },
    meta: {
      graphManaged: true,
      edgeFrom: edge.from,
      edgeTo: edge.to,
      edgeType: edge.type,
      archived: isArchived,
    },
  }
}

function createEdgeBindings(edge: GraphEdge, from: PositionedNode, to: PositionedNode) {
  const edgeShapeId = getEdgeShapeId(edge)
  const fromShapeId = getNodeShapeId(edge.from)
  const toShapeId = getNodeShapeId(edge.to)

  return [
    {
      type: 'arrow' as const,
      fromId: edgeShapeId,
      toId: fromShapeId,
      props: {
        terminal: 'start' as const,
        isExact: false,
        isPrecise: false,
        normalizedAnchor: getAnchor(from, to, 'start'),
      },
    },
    {
      type: 'arrow' as const,
      fromId: edgeShapeId,
      toId: toShapeId,
      props: {
        terminal: 'end' as const,
        isExact: false,
        isPrecise: false,
        normalizedAnchor: getAnchor(from, to, 'end'),
      },
    },
  ] satisfies GraphBindingRecord[]
}

export function buildTldrawGraph(graph: Graph) {
  const positionedNodes = layoutGraph(graph)
  const shapes = graph.nodes.map(node => createNodeShape(positionedNodes.get(node.id)!))
  const edgeShapes = graph.edges.flatMap(edge => {
    const from = positionedNodes.get(edge.from)
    const to = positionedNodes.get(edge.to)

    if (!from || !to) {
      return []
    }

    return [createEdgeShape(edge, from, to)]
  })
  const bindings = graph.edges.flatMap(edge => {
    const from = positionedNodes.get(edge.from)
    const to = positionedNodes.get(edge.to)

    if (!from || !to) {
      return []
    }

    return createEdgeBindings(edge, from, to)
  })

  return {
    shapes: [...shapes, ...edgeShapes],
    bindings,
  }
}

function areAnchorsEqual(
  a: GraphBindingRecord['props']['normalizedAnchor'],
  b: GraphBindingRecord['props']['normalizedAnchor'],
) {
  return a.x === b.x && a.y === b.y
}

function areBindingRecordsEqual(current: any, next: GraphBindingRecord) {
  return (
    current.type === next.type &&
    current.fromId === next.fromId &&
    current.toId === next.toId &&
    current.props.terminal === next.props.terminal &&
    current.props.isExact === next.props.isExact &&
    current.props.isPrecise === next.props.isPrecise &&
    areAnchorsEqual(current.props.normalizedAnchor, next.props.normalizedAnchor)
  )
}

function areShapeRecordsEqual(current: any, next: any) {
  return (
    current.type === next.type &&
    current.x === next.x &&
    current.y === next.y &&
    JSON.stringify(current.props) === JSON.stringify(next.props) &&
    JSON.stringify(current.meta ?? null) === JSON.stringify(next.meta ?? null)
  )
}

function syncBindings(editor: Editor, bindings: GraphBindingRecord[]) {
  const desiredBindingsByArrow = new Map<string, GraphBindingRecord[]>()

  bindings.forEach(binding => {
    const items = desiredBindingsByArrow.get(binding.fromId) ?? []
    items.push(binding)
    desiredBindingsByArrow.set(binding.fromId, items)
  })

  const managedArrowIds = Array.from(editor.getCurrentPageShapeIds())
    .map(shapeId => String(shapeId))
    .filter(shapeId => shapeId.startsWith(GRAPH_EDGE_SHAPE_PREFIX))

  managedArrowIds.forEach(arrowId => {
    const desiredBindings = desiredBindingsByArrow.get(arrowId) ?? []
    const desiredByTerminal = new Map(desiredBindings.map(binding => [binding.props.terminal, binding]))
    const existingBindings = editor.getBindingsFromShape(arrowId, 'arrow')
    const existingByTerminal = new Map(existingBindings.map(binding => [binding.props.terminal, binding]))

    const bindingsToDelete = existingBindings
      .filter(binding => !desiredByTerminal.has(binding.props.terminal))
      .map(binding => binding.id)

    if (bindingsToDelete.length > 0) {
      editor.deleteBindings(bindingsToDelete)
    }

    const bindingsToCreate: GraphBindingRecord[] = []
    const bindingsToUpdate: Array<GraphBindingRecord & { id: string }> = []

    desiredBindings.forEach(binding => {
      const existing = existingByTerminal.get(binding.props.terminal)
      if (!existing) {
        bindingsToCreate.push(binding)
        return
      }

      if (!areBindingRecordsEqual(existing, binding)) {
        bindingsToUpdate.push({ id: existing.id, ...binding })
      }
    })

    if (bindingsToCreate.length > 0) {
      editor.createBindings(bindingsToCreate)
    }

    if (bindingsToUpdate.length > 0) {
      editor.updateBindings(bindingsToUpdate)
    }
  })
}

export function syncGraphToEditor(editor: Editor, graph: Graph, zoomToFit = false) {
  const { shapes, bindings } = buildTldrawGraph(graph)
  const currentManagedShapes = editor.getCurrentPageShapes()
    .filter(shape => isManagedGraphShapeId(String(shape.id)))
  const currentShapeIds = new Set(currentManagedShapes.map(shape => String(shape.id)))
  const nextShapesById = new Map(shapes.map(shape => [String(shape.id), shape]))
  const shapesToCreate = shapes.filter(shape => !currentShapeIds.has(String(shape.id)))
  const shapesToUpdate = currentManagedShapes
    .map(shape => {
      const nextShape = nextShapesById.get(String(shape.id))
      if (!nextShape || areShapeRecordsEqual(shape, nextShape)) {
        return null
      }
      return nextShape
    })
    .filter(Boolean)
  const shapeIdsToDelete = currentManagedShapes
    .map(shape => String(shape.id))
    .filter(shapeId => !nextShapesById.has(shapeId))

  editor.run(() => {
    if (shapeIdsToDelete.length > 0) {
      editor.deleteShapes(shapeIdsToDelete)
    }

    if (shapesToCreate.length > 0) {
      editor.createShapes(shapesToCreate)
    }

    if (shapesToUpdate.length > 0) {
      editor.updateShapes(shapesToUpdate)
    }

    syncBindings(editor, bindings)

    if (zoomToFit && shapes.length > 0) {
      editor.zoomToFit({ animation: { duration: 0 } })
    }
  }, { history: 'ignore' })
}
