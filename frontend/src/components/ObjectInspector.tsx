import type { ImageAnnotation } from '../types'

interface Props { annotation: ImageAnnotation; imageUrl: string; imageWidth: number; imageHeight: number; onCorrect: () => void; onSkip: () => void; saving: boolean }
export function ObjectInspector({ annotation, imageUrl, imageWidth, imageHeight, onCorrect, onSkip, saving }: Props) {
  const box = annotation.coordinates
  const style = { backgroundImage: `url(${imageUrl})`, backgroundSize: `${imageWidth / box.width}px ${imageHeight / box.height}px`, backgroundPosition: `${-(box.x_center - box.width / 2) * imageWidth}px ${-(box.y_center - box.height / 2) * imageHeight}px` }
  return <section className="inspector" aria-label="Selected object">
    <div className="crop-preview" style={style} aria-label="Selected object crop" />
    <dl><div><dt>Source</dt><dd>{annotation.source_class_id} · {annotation.source_class_name}</dd></div><div><dt>Current target</dt><dd aria-label={`Current target ${annotation.current_class_id}`}>{annotation.current_class_id}</dd></div><div><dt>Status</dt><dd>{annotation.decision ?? 'Unreviewed'}</dd></div></dl>
    <div className="action-row"><button type="button" onClick={onCorrect} disabled={saving}>Correct</button><button type="button" onClick={onSkip} disabled={saving}>Skip</button></div>
  </section>
}
