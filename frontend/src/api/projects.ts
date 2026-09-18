import { apiRequest, queryString } from './client'
import type { ImageDetail, ImageSummary, Page, ProjectSummary } from '../types'

export const listProjects = (query = '') => apiRequest<Page<ProjectSummary>>(`/api/v1/projects?${queryString({ query, limit: 200, offset: 0 })}`)
export const getProject = (id: string) => apiRequest<ProjectSummary>(`/api/v1/projects/${id}`)
export const listImages = (projectId: string) => apiRequest<Page<ImageSummary>>(`/api/v1/projects/${projectId}/images?${queryString({ limit: 500, offset: 0 })}`)
export const getImage = (projectId: string, imageId: string) => apiRequest<ImageDetail>(`/api/v1/projects/${projectId}/images/${imageId}`)

export async function createProject(name: string, catalogId: string, file: File): Promise<ProjectSummary> {
  const body = new FormData()
  body.set('name', name)
  body.set('catalog_id', catalogId)
  body.set('dataset_zip', file)
  return apiRequest('/api/v1/projects', { method: 'POST', body })
}

