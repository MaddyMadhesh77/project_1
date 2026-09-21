import { useEffect, useMemo, useState } from 'react'
import { Background, Controls, ReactFlow, ReactFlowProvider, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { default as ELK } from 'elkjs/lib/elk.bundled.js'
import type { GraphEdge, GraphNode } from '../../lib/api'

// Same fixed status palette as lib/status.ts, as hex -- react-flow node
// borders are inline-styled (computed from the layout engine per render), so
// they can't go through Tailwind's dark: variant the way the rest of the app
// does.
const STATUS_COLORS: Record<string, string> = {
  trusted: '#0ca30c',
  low_trust: '#fab219',
  quarantined: '#d03b3b',
  rolled_back: '#ec835a',
}
const FALLBACK_COLOR = '#a3a3a3'

const NODE_WIDTH = 220
const NODE_HEIGHT = 56

// elkjs, not dagre (dagre's last release was 2020 -- unmaintained).
// elk.bundled.js runs layout synchronously in-thread instead of spinning up
// a web worker -- the right build for a small, render-blocking graph like
// this one (xyflow's own elkjs layout example uses the same import). Loaded
// via dynamic import rather than a static one: elkjs alone is ~1.3MB
// unminified, and GraphView only renders on the two dependency-graph views
// -- eagerly bundling it into the main chunk would have doubled the app's
// total JS for pages that never show a graph.
let elkPromise: Promise<InstanceType<typeof ELK>> | null = null

function getElk(): Promise<InstanceType<typeof ELK>> {
  if (!elkPromise) {
    elkPromise = import('elkjs/lib/elk.bundled.js').then((mod) => new mod.default())
  }
  return elkPromise
}

async function layoutPositions(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Promise<Map<string, { x: number; y: number }>> {
  const elk = await getElk()
  const laidOut = await elk.layout({
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.spacing.nodeNode': '32',
      'elk.layered.spacing.nodeNodeBetweenLayers': '64',
    },
    children: nodes.map((node) => ({ id: node.version_id, width: NODE_WIDTH, height: NODE_HEIGHT })),
    edges: edges.map((edge) => ({
      id: `${edge.parent_version_id}-${edge.child_version_id}`,
      sources: [edge.parent_version_id],
      targets: [edge.child_version_id],
    })),
  })

  return new Map((laidOut.children ?? []).map((child) => [child.id, { x: child.x ?? 0, y: child.y ?? 0 }]))
}

interface GraphViewProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  rootVersionId: string
  height?: number
}

export default function GraphView({ nodes, edges, rootVersionId, height = 320 }: GraphViewProps) {
  // elkjs computes layout asynchronously (unlike dagre's synchronous call) --
  // positions land in state once the layout promise resolves, which is
  // typically well within a frame for graphs this small.
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map())

  useEffect(() => {
    let cancelled = false
    layoutPositions(nodes, edges).then((result) => {
      if (!cancelled) setPositions(result)
    })
    return () => {
      cancelled = true
    }
  }, [nodes, edges])

  const { flowNodes, flowEdges } = useMemo(() => {
    const flowNodes: Node[] = nodes.map((node) => {
      const position = positions.get(node.version_id) ?? { x: 0, y: 0 }
      const color = STATUS_COLORS[node.status] ?? FALLBACK_COLOR
      const isRoot = node.version_id === rootVersionId

      return {
        id: node.version_id,
        position,
        className: 'rm-graph-node',
        data: {
          label: (
            <div className="text-xs">
              <div className="truncate font-medium">{node.text}</div>
              <div className="mt-0.5 flex items-center gap-1 text-[10px] opacity-70">
                <span>{node.trust_score.toFixed(1)}</span>
                {isRoot && <span>&middot; viewing</span>}
                {!isRoot && node.is_current && <span>&middot; current</span>}
              </div>
            </div>
          ),
        },
        style: {
          width: NODE_WIDTH,
          borderRadius: 8,
          border: `${isRoot ? 3 : 2}px solid ${color}`,
          borderStyle: node.is_current ? 'solid' : 'dashed',
          padding: 8,
        },
      }
    })

    const flowEdges: Edge[] = edges.map((edge) => ({
      id: `${edge.parent_version_id}-${edge.child_version_id}`,
      source: edge.parent_version_id,
      target: edge.child_version_id,
      animated: true,
      style: { stroke: FALLBACK_COLOR },
    }))

    return { flowNodes, flowEdges }
  }, [nodes, edges, rootVersionId, positions])

  return (
    <div style={{ height }} className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
      <ReactFlowProvider>
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          colorMode="system"
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  )
}
