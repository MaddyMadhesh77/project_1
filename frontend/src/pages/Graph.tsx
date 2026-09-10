import { Link, useParams } from 'react-router-dom'
import GraphView from '../components/GraphView'
import { SkeletonBlock } from '../components/Skeleton'
import { useMemory, useMemoryGraph } from '../lib/queries'

export default function Graph() {
  const { memoryId } = useParams<{ memoryId: string }>()
  const { data: memory } = useMemory(memoryId)
  const { data: graph, isLoading, isError } = useMemoryGraph(memoryId)

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonBlock className="h-8 w-1/2" />
        <SkeletonBlock className="h-[480px]" />
      </div>
    )
  }
  if (isError || !graph) return <p className="text-sm text-red-500">Failed to load dependency graph.</p>

  return (
    <div className="space-y-4">
      <div>
        <Link
          to={`/admin/memories/${memoryId}`}
          className="text-sm text-neutral-500 hover:underline dark:text-neutral-400"
        >
          &larr; Back to memory
        </Link>
        <h1 className="mt-1 text-xl font-semibold text-neutral-800 dark:text-neutral-100">
          Dependency graph{memory?.text ? ` — ${memory.text}` : ''}
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          Ancestors (memories this one was derived from) and descendants (memories derived using this one as
          context). Dashed borders are superseded versions; solid are each memory's current version.
        </p>
      </div>

      {graph.nodes.length <= 1 ? (
        <p className="text-sm text-neutral-400">
          No dependency edges yet — this memory has no recorded ancestors or descendants.
        </p>
      ) : (
        <GraphView nodes={graph.nodes} edges={graph.edges} rootVersionId={graph.root_version_id} height={480} />
      )}
    </div>
  )
}
