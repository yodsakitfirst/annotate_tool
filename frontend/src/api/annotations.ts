import { apiRequest } from './client'
import type { ImageAnnotation } from '../types'

export interface AnnotationAction {
  annotationId: string
  action: 'correct' | 'relabel' | 'skip'
  targetClassId?: number
  annotatorName?: string
}

export const updateAnnotation = ({ annotationId, action, targetClassId, annotatorName }: AnnotationAction) =>
  apiRequest<ImageAnnotation>(`/api/v1/annotations/${annotationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, target_class_id: targetClassId, annotator_name: annotatorName }),
  })

