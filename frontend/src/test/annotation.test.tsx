import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { AnnotationPage } from '../pages/AnnotationPage'

const project = { id: 'p1', name: 'Dataset A', catalog_id: 'c1', image_count: 1, annotation_count: 1, reviewed_count: 0, thumbnail_url: null, created_at: '', updated_at: '' }
const images = { items: [{ id: 'i1', relative_path: 'images/a.png', width: 100, height: 80, annotation_count: 1, reviewed_count: 0, error_message: null, media_url: '/media/images/i1' }], limit: 100, offset: 0 }
const detail = { ...images.items[0], annotations: [{ id: 'a1', line_index: 0, source_class_id: 999, source_class_name: 'Unknown source class 999', current_class_id: 999, coordinates: { x_center: 0.5, y_center: 0.5, width: 0.2, height: 0.4 }, decision: null, annotator_name: null, version: 0 }], problems: [] }
const classes = { items: [{ class_id: 7, name: 'Omega', thumbnail_url: '/media/catalogs/c1/classes/7' }], limit: 50, offset: 0 }

function renderPage(fetchImpl: typeof fetch) {
  vi.stubGlobal('fetch', fetchImpl)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/projects/p1/annotate']}>
        <Routes><Route path="/projects/:projectId/annotate" element={<AnnotationPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function jsonResponse(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }))
}

test('optimistically relabels with exactly one mutation request', async () => {
  const requests: Array<[string, RequestInit | undefined]> = []
  renderPage(((input, init) => {
    const url = String(input)
    requests.push([url, init])
    if (url === '/api/v1/projects/p1') return jsonResponse(project)
    if (url.includes('/images?')) return jsonResponse(images)
    if (url.endsWith('/images/i1')) return jsonResponse(detail)
    if (url.includes('/catalogs/c1/classes')) return jsonResponse(classes)
    if (url.endsWith('/annotations/a1')) return jsonResponse({ ...detail.annotations[0], current_class_id: 7, decision: 'relabel', version: 1, updated_at: '' })
    return jsonResponse({}, 404)
  }) as typeof fetch)
  const user = userEvent.setup()

  await user.click(await screen.findByRole('button', { name: /omega/i }))

  expect(screen.getByLabelText(/current target 7/i)).toBeInTheDocument()
  await waitFor(() => expect(requests.filter(([url]) => url.endsWith('/annotations/a1'))).toHaveLength(1))
})


test('rolls back a failed optimistic relabel and offers retry', async () => {
  renderPage(((input) => {
    const url = String(input)
    if (url === '/api/v1/projects/p1') return jsonResponse(project)
    if (url.includes('/images?')) return jsonResponse(images)
    if (url.endsWith('/images/i1')) return jsonResponse(detail)
    if (url.includes('/catalogs/c1/classes')) return jsonResponse(classes)
    if (url.endsWith('/annotations/a1')) return jsonResponse({ error: { code: 'save_failed', message: 'Try again', details: {} } }, 503)
    return jsonResponse({}, 404)
  }) as typeof fetch)
  const user = userEvent.setup()

  await user.click(await screen.findByRole('button', { name: /omega/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Try again')
  expect(screen.getByLabelText(/current target 999/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
})
