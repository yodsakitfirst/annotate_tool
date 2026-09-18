import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { updateAnnotation, type AnnotationAction } from '../api/annotations'
import { getImage, getProject, listImages } from '../api/projects'
import type { ImageDetail } from '../types'
import { BoundingBoxOverlay } from '../components/BoundingBoxOverlay'
import { ErrorNotice } from '../components/ErrorNotice'
import { ImageNavigator } from '../components/ImageNavigator'
import { ObjectInspector } from '../components/ObjectInspector'
import { ReferenceClassBrowser } from '../components/ReferenceClassBrowser'

export function AnnotationPage() {
  const { projectId = '' } = useParams()
  const queryClient = useQueryClient()
  const [imageIndex, setImageIndex] = useState(() => Number(localStorage.getItem(`lastImage:${projectId}`) ?? 0))
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [failedAction, setFailedAction] = useState<AnnotationAction | null>(null)
  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => getProject(projectId), enabled: !!projectId })
  const images = useQuery({ queryKey: ['images', projectId], queryFn: () => listImages(projectId), enabled: !!projectId })
  useEffect(() => {
    if (images.data && imageIndex >= images.data.items.length) setImageIndex(0)
    else localStorage.setItem(`lastImage:${projectId}`, String(imageIndex))
  }, [imageIndex, images.data, projectId])
  const currentImage = images.data?.items[imageIndex]
  const imageKey = ['image', projectId, currentImage?.id]
  const detail = useQuery({ queryKey: imageKey, queryFn: () => getImage(projectId, currentImage!.id), enabled: !!currentImage })
  useEffect(() => {
    if (!detail.data?.annotations.length) { setSelectedId(null); return }
    if (!detail.data.annotations.some((item) => item.id === selectedId)) setSelectedId(detail.data.annotations[0].id)
  }, [detail.data, selectedId])
  const selectedIndex = Math.max(0, detail.data?.annotations.findIndex((item) => item.id === selectedId) ?? 0)
  const selected = detail.data?.annotations[selectedIndex]
  const mutation = useMutation({
    mutationFn: updateAnnotation,
    onMutate: async (action) => {
      setFailedAction(null)
      await queryClient.cancelQueries({ queryKey: imageKey })
      const previous = queryClient.getQueryData<ImageDetail>(imageKey)
      queryClient.setQueryData<ImageDetail>(imageKey, (old) => old ? { ...old, annotations: old.annotations.map((item) => item.id === action.annotationId ? { ...item, current_class_id: action.targetClassId ?? item.current_class_id, decision: action.action } : item) } : old)
      return { previous }
    },
    onError: (_error, action, context) => { queryClient.setQueryData(imageKey, context?.previous); setFailedAction(action) },
    onSuccess: (saved) => { queryClient.setQueryData<ImageDetail>(imageKey, (old) => old ? { ...old, annotations: old.annotations.map((item) => item.id === saved.id ? { ...item, ...saved } : item) } : old); queryClient.invalidateQueries({ queryKey: ['projects'] }); queryClient.invalidateQueries({ queryKey: ['project', projectId] }) },
  })
  const annotatorName = localStorage.getItem('annotatorName') ?? ''
  const act = (action: AnnotationAction['action'], targetClassId?: number) => selected && mutation.mutate({ annotationId: selected.id, action, targetClassId, annotatorName })
  const errorMessage = mutation.error instanceof Error ? mutation.error.message : 'Save failed'
  const progress = useMemo(() => project.data ? `${project.data.reviewed_count}/${project.data.annotation_count} reviewed` : '', [project.data])
  if (project.isLoading || images.isLoading) return <p>Loading project…</p>
  if (project.isError || images.isError) return <ErrorNotice message="Could not load this project." />
  if (!images.data?.items.length) return <section className="empty-state"><h1>{project.data?.name}</h1><p>This project has no images.</p></section>
  return <div className="annotation-page">
    <header className="workspace-header"><div><p className="eyebrow">Project</p><h1>{project.data?.name}</h1><p>{progress}</p></div><a className="button" href={`/api/v1/projects/${projectId}/export`}>Export labels</a></header>
    <ImageNavigator label="Image" index={imageIndex} count={images.data.items.length} onPrevious={() => setImageIndex((value) => Math.max(0, value - 1))} onNext={() => setImageIndex((value) => Math.min(images.data!.items.length - 1, value + 1))} />
    {detail.isLoading && <p>Loading image…</p>}
    {detail.data && detail.data.width && detail.data.height && <div className="workspace-grid"><div>
      <BoundingBoxOverlay imageUrl={detail.data.media_url} width={detail.data.width} height={detail.data.height} annotations={detail.data.annotations} selectedId={selectedId} onSelect={setSelectedId} />
      <ImageNavigator label="Object" index={selectedIndex} count={detail.data.annotations.length} onPrevious={() => setSelectedId(detail.data!.annotations[Math.max(0, selectedIndex - 1)]?.id ?? null)} onNext={() => setSelectedId(detail.data!.annotations[Math.min(detail.data!.annotations.length - 1, selectedIndex + 1)]?.id ?? null)} />
      {selected && <ObjectInspector annotation={selected} imageUrl={detail.data.media_url} imageWidth={detail.data.width} imageHeight={detail.data.height} onCorrect={() => act('correct')} onSkip={() => act('skip')} saving={mutation.isPending} />}
      {mutation.isError && <ErrorNotice message={errorMessage} onRetry={failedAction ? () => mutation.mutate(failedAction) : undefined} />}
    </div>{selected && project.data && <ReferenceClassBrowser catalogId={project.data.catalog_id} selectedClassId={selected.current_class_id} onSelect={(id) => act('relabel', id)} disabled={mutation.isPending} />}</div>}
  </div>
}
