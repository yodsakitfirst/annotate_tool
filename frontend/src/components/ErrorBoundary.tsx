import { Component, type ErrorInfo, type ReactNode } from 'react'

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(error, info) }
  render() { return this.state.failed ? <main className="fatal-error"><h1>Something went wrong</h1><p>Reload the page to try again.</p></main> : this.props.children }
}

