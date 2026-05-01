/**
 * TypeScript interfaces matching the Pydantic models defined in
 * signal-flow-graph-backend/app/models/graph.py
 */

// ─── REQUEST MODELS ───────────────────────────────────────────────────────────

export interface BranchInput {
  from: string | number;
  to: string | number;
  gain: string | number;
}

export interface GraphInput {
  nodes: (string | number)[];
  branches: BranchInput[];
  source: string | number;
  sink: string | number;
}

// ─── RESPONSE MODELS ──────────────────────────────────────────────────────────

export interface BranchOutput {
  from: string | number;
  to: string | number;
  gain: string;
}

export interface ForwardPath {
  index: number;
  nodes: (string | number)[];
  gain: string;
}

export interface Loop {
  index: number;
  nodes: (string | number)[];
  gain: string;
}

export interface NonTouchingGroup {
  size: number;
  loop_indices: number[];
  gain: string;
}

export interface DeltaK {
  path_index: number;
  value: string;
  latex: string;
}

export interface NodeLayout {
  id: string | number;
  x: number;
  y: number;
  label: string;
}

export interface EdgeLayout {
  from: string | number;
  to: string | number;
  gain: string;
  is_self_loop: boolean;
  is_back_edge: boolean;
  control_x: number | null;
  control_y: number | null;
}

export interface GraphLayout {
  nodes: NodeLayout[];
  edges: EdgeLayout[];
}

export interface GraphSummary {
  nodes: (string | number)[];
  source: string | number;
  sink: string | number;
  branches: BranchOutput[];
}

export interface GraphAnalysisResult {
  graph_summary: GraphSummary;
  forward_paths: ForwardPath[];
  loops: Loop[];
  non_touching_groups: NonTouchingGroup[];
  delta: string;
  delta_latex: string;
  delta_k: DeltaK[];
  transfer_function: string;
  transfer_function_latex: string;
  layout: GraphLayout;
}

export interface ErrorResponse {
  detail: string;
  code: string;
}
