export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="error-notice" role="alert"><span>{message}</span>{onRetry && <button type="button" onClick={onRetry}>Retry</button>}</div>
}

