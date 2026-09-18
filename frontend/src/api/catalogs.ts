import { apiRequest, queryString } from './client'
import type { CatalogClass, CatalogSummary, Page } from '../types'

export const listCatalogs = (query = '') => apiRequest<Page<CatalogSummary>>(`/api/v1/catalogs?${queryString({ query, limit: 200, offset: 0 })}`)
export const getCatalog = (id: string) => apiRequest<CatalogSummary>(`/api/v1/catalogs/${id}`)
export const listCatalogClasses = (id: string, query = '', offset = 0) => apiRequest<Page<CatalogClass>>(`/api/v1/catalogs/${id}/classes?${queryString({ query, limit: 50, offset })}`)

export async function createCatalog(name: string, file: File): Promise<CatalogSummary> {
  const body = new FormData()
  body.set('name', name)
  body.set('catalog_zip', file)
  return apiRequest('/api/v1/catalogs', { method: 'POST', body })
}

