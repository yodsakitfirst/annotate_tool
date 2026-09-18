import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

import { ProjectSidebar } from '../components/ProjectSidebar'
import type { ProjectSummary } from '../types'

const projects: ProjectSummary[] = [
  { id: 'one', name: 'Hair Alpha', catalog_id: 'c', image_count: 2, annotation_count: 4, reviewed_count: 1, thumbnail_url: null, created_at: '', updated_at: '' },
  { id: 'two', name: 'Retail Beta', catalog_id: 'c', image_count: 3, annotation_count: 6, reviewed_count: 6, thumbnail_url: null, created_at: '', updated_at: '' },
]

function Location() {
  return <output>{useLocation().pathname}</output>
}

test('searches projects and navigates client-side', async () => {
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/']}>
      <ProjectSidebar projects={projects} activeProjectId={null} collapsed={false} onToggle={() => undefined} />
      <Routes><Route path="*" element={<Location />} /></Routes>
    </MemoryRouter>,
  )

  await user.type(screen.getByRole('searchbox', { name: /search projects/i }), 'retail')
  expect(screen.queryByText('Hair Alpha')).not.toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: /retail beta/i }))
  expect(screen.getByRole('status')).toHaveTextContent('/projects/two/annotate')
})


test('collapse control is keyboard accessible', async () => {
  const user = userEvent.setup()
  const onToggle = vi.fn()
  render(
    <MemoryRouter>
      <ProjectSidebar projects={projects} activeProjectId="one" collapsed={false} onToggle={onToggle} />
    </MemoryRouter>,
  )
  await user.click(screen.getByRole('button', { name: /collapse sidebar/i }))
  expect(onToggle).toHaveBeenCalledOnce()
})
