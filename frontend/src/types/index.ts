export interface ProjectSummary {
  id: string
  name: string
  catalog_id: string
  image_count: number
  annotation_count: number
  reviewed_count: number
  thumbnail_url: string | null
  created_at: string
  updated_at: string
}

export interface CatalogSummary {
  id: string
  name: string
  class_count: number
  created_at: string
  preview_url: string | null
}

export interface CatalogClass {
  class_id: number
  name: string
  thumbnail_url: string
}

export interface ImageSummary {
  id: string
  relative_path: string
  width: number | null
  height: number | null
  annotation_count: number
  reviewed_count: number
  error_message: string | null
  media_url: string
}

export interface ImageAnnotation {
  id: string
  line_index: number
  source_class_id: number
  source_class_name: string
  current_class_id: number
  coordinates: { x_center: number; y_center: number; width: number; height: number }
  decision: 'correct' | 'relabel' | 'skip' | null
  annotator_name: string | null
  version: number
}

export interface ImageDetail extends ImageSummary {
  annotations: ImageAnnotation[]
  problems: Array<{ relative_path: string; line_index: number | null; message: string }>
}

export interface Page<T> {
  items: T[]
  limit: number
  offset: number
}

