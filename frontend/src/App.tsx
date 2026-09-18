import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AnnotationPage } from './pages/AnnotationPage'
import { CatalogDetailPage } from './pages/CatalogDetailPage'
import { CatalogListPage } from './pages/CatalogListPage'
import { NewCatalogPage } from './pages/NewCatalogPage'
import { NewProjectPage } from './pages/NewProjectPage'

function Home() { const id = localStorage.getItem('lastProjectId'); return id ? <Navigate to={`/projects/${id}/annotate`} replace /> : <section className="empty-state"><h1>Choose a project</h1><p>Select an existing project or create a new one.</p></section> }
export function App() { return <Routes><Route element={<AppShell />}><Route path="/" element={<Home />} /><Route path="/projects/new" element={<NewProjectPage />} /><Route path="/projects/:projectId/annotate" element={<AnnotationPage />} /><Route path="/catalogs" element={<CatalogListPage />} /><Route path="/catalogs/new" element={<NewCatalogPage />} /><Route path="/catalogs/:catalogId" element={<CatalogDetailPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes> }

