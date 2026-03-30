/**
 * types.ts — graph.json schema (D-005)
 *
 * TypeScript 类型定义，对应 graph.json 结构
 */

export interface GraphNode {
  id: string;
  title: string;
  layer: 'R' | 'D' | 'F' | 'U';
  status: 'todo' | 'doing' | 'blocked' | 'done';
  session: string | null;
  milestone?: string;
  archived?: boolean;
  expected?: string;
  file?: string;
  functions?: string[];
  tdd?: {
    entry: string;
    first_fail: string;
    expected: string;
  };
  metadata?: Record<string, unknown>;
}

export interface GraphEdge {
  from: string;
  to: string;
  type: '-->' | '-.->' | '==>';
  reason?: string;
}

export interface Graph {
  version: string;
  createdAt?: string;
  description?: string;
  milestones?: Record<string, string>;
  nodes: GraphNode[];
  edges: GraphEdge[];
}
