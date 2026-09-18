import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { listProjects } from '../api/projects'
import { ProjectSidebar } from './ProjectSidebar'

export function AppShell() {
  const location = useLocation()
  const projectId = location.pathname.match(/^\/projects\/([^/]+)\/annotate/)?.[1]
  const [collapsed, setCollapsed] = useState(false)
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => listProjects() })
  return (
    <div className="app-shell">
      <ProjectSidebar projects={projects.data?.items ?? []} activeProjectId={projectId ?? null} collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />
      <main className="main-content">
        {projects.isError && <div role="alert" className="error-notice">Could not load projects.</div>}
        <Outlet />
      </main>
    </div>
  )
}
