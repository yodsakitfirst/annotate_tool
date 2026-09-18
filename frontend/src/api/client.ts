export class ApiClientError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    let payload: { error?: { code?: string; message?: string } } = {}
    try { payload = await response.json() } catch { /* non-JSON server failure */ }
    throw new ApiClientError(
      response.status,
      payload.error?.code ?? 'request_failed',
      payload.error?.message ?? `Request failed (${response.status})`,
    )
  }
  return response.json() as Promise<T>
}

export function queryString(values: Record<string, string | number>): string {
  return new URLSearchParams(Object.entries(values).map(([key, value]) => [key, String(value)])).toString()
}

