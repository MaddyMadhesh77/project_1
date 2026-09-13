import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

// bugs.md #15: an unhandled error thrown during render previously crashed
// the whole React tree to a blank white screen with no recovery path.
// Error boundaries only catch render/lifecycle errors -- not errors inside
// event handlers or async code (e.g. a rejected fetch), which is why this
// doesn't replace the per-page isError checks already in every page.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto flex h-screen max-w-md flex-col items-center justify-center gap-3 p-4 text-center">
          <h1 className="text-lg font-semibold text-neutral-800 dark:text-neutral-100">Something went wrong</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">{this.state.error.message}</p>
          <button
            onClick={() => {
              this.setState({ error: null })
              window.location.assign('/')
            }}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
