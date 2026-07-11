"use client";

import { useCallback, useMemo } from "react";
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type DefaultEdgeOptions,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { FlowEdge, FlowGraph, FlowNode, WorkflowNodeType } from "@/lib/api/workflows";
import { REACT_FLOW_NODE_TYPES } from "./node-types";

/** Mono, subtly-arrowed default edges — the SHELL stays monochrome. */
const DEFAULT_EDGE_OPTIONS: DefaultEdgeOptions = {
  type: "smoothstep",
  style: { stroke: "var(--border-strong)", strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "var(--border-strong)", width: 16, height: 16 },
};

export interface NodeTypeDef {
  type: WorkflowNodeType;
  label: string;
  defaultData: Record<string, unknown>;
}

export interface FlowCanvasProps {
  graph: FlowGraph;
  onGraphChange: (graph: FlowGraph) => void;
  nodeTypeDefs: NodeTypeDef[];
  readOnly?: boolean;
  /** Called with the clicked node's id — used to drive the node inspector panel. */
  onNodeClick?: (nodeId: string) => void;
}

function toReactFlowNodes(nodes: FlowNode[]): Node[] {
  return nodes.map((n, index) => ({
    id: n.id,
    type: n.type,
    position: n.position ?? { x: 120, y: 120 + index * 100 },
    data: { ...n.data, label: n.data.label ?? n.type },
  }));
}

function toReactFlowEdges(edges: FlowEdge[]): Edge[] {
  return edges.map((e) => ({
    id: `${e.source}-${e.target}-${e.condition ?? "default"}`,
    source: e.source,
    target: e.target,
    label: e.condition,
  }));
}

export function FlowCanvas({
  graph,
  onGraphChange,
  nodeTypeDefs,
  readOnly,
  onNodeClick,
}: FlowCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(toReactFlowNodes(graph.nodes));
  const [edges, setEdges, onEdgesChange] = useEdgesState(toReactFlowEdges(graph.edges));

  const emitChange = useCallback(
    (nextNodes: Node[], nextEdges: Edge[]) => {
      onGraphChange({
        nodes: nextNodes.map((n) => ({
          id: n.id,
          type: n.type as WorkflowNodeType,
          data: n.data as Record<string, unknown>,
          position: n.position,
        })),
        edges: nextEdges.map((e) => ({
          source: e.source,
          target: e.target,
          condition: typeof e.label === "string" ? e.label : undefined,
        })),
      });
    },
    [onGraphChange],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      const next = addEdge(connection, edges);
      setEdges(next);
      emitChange(nodes, next);
    },
    [edges, nodes, setEdges, emitChange],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/workflow-node-type") as WorkflowNodeType;
      const def = nodeTypeDefs.find((d) => d.type === type);
      if (!def) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      const newNode: Node = {
        id: `${type}-${crypto.randomUUID().slice(0, 8)}`,
        type,
        position: { x: event.clientX - bounds.left, y: event.clientY - bounds.top },
        data: { ...def.defaultData, label: def.label },
      };
      const next = [...nodes, newNode];
      setNodes(next);
      emitChange(next, edges);
    },
    [nodeTypeDefs, nodes, edges, setNodes, emitChange],
  );

  const nodeTypes = useMemo(() => REACT_FLOW_NODE_TYPES, []);

  return (
    <div
      className="h-[560px] min-h-[560px] w-full overflow-hidden rounded-xl border border-border bg-[var(--bg-subtle)]"
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      data-testid="flow-canvas"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        onNodesChange={readOnly ? undefined : onNodesChange}
        onEdgesChange={readOnly ? undefined : onEdgesChange}
        onConnect={readOnly ? undefined : handleConnect}
        onNodeClick={onNodeClick ? (_, node) => onNodeClick(node.id) : undefined}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--border-default)" />
        <Controls
          showInteractive={false}
          className="!rounded-lg !border !border-border !bg-card !shadow-[var(--shadow-sm)]"
        />
      </ReactFlow>
    </div>
  );
}
