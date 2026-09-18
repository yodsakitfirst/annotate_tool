import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { ProjectSummary } from '../types'

interface Props {
  projects: ProjectSummary[]
  activeProjectId: string | null
  collapsed: boolean
  onToggle: () => void
}

export function ProjectSidebar({ projects, activeProjectId, collapsed, onToggle }: Props) {
  const [query, setQuery] = useState('')
  const [annotatorName, setAnnotatorName] = useState(() => localStorage.getItem('annotatorName') ?? '')
  const matches = projects.filter((project) => project.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
  return (
    <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`} aria-label="Projects">
      <div className="brand-row"><strong>Annotation Desk</strong><button type="button" className="icon-button" onClick={onToggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? '»' : '«'}</button></div>
      {!collapsed && <>
        <label className="search-label">Search projects<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search projects" placeholder="Find a project" /></label>
        <nav className="project-list" aria-label="Project list">
          {matches.map((project) => (
            <Link key={project.id} to={`/projects/${project.id}/annotate`} className={`project-row ${activeProjectId === project.id ? 'is-active' : ''}`} onClick={() => localStorage.setItem('lastProjectId', project.id)}>
              <span className="project-thumb">{project.thumbnail_url ? <img src={project.thumbnail_url} alt="" loading="lazy" /> : project.name.slice(0, 1).toUpperCase()}</span>
              <span><b>{project.name}</b><small>{project.image_count} images · {project.reviewed_count}/{project.annotation_count} reviewed</small></span>
            </Link>
          ))}
          {!matches.length && <p className="muted">No matching projects.</p>}
        </nav>
        <label className="search-label">Display name (optional)<input value={annotatorName} onChange={(event) => { setAnnotatorName(event.target.value); localStorage.setItem('annotatorName', event.target.value) }} placeholder="For audit attribution" /></label>
        <div className="sidebar-actions"><Link className="button button--primary" to="/projects/new">New project</Link><Link className="button" to="/catalogs">Reference catalogs</Link></div>
      </>}
    </aside>
  )
}
