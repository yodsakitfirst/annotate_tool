import type { ImageAnnotation } from '../types'

interface Props {
  imageUrl: string
  width: number
  height: number
  annotations: ImageAnnotation[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function BoundingBoxOverlay({ imageUrl, width, height, annotations, selectedId, onSelect }: Props) {
  return (
    <div className="image-stage">
      <img src={imageUrl} alt="Current annotation image" />
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" aria-label="Bounding boxes">
        {annotations.map((annotation, index) => {
          const box = annotation.coordinates
          return <g key={annotation.id}>
            <rect role="button" aria-label={`Object ${index + 1}`} tabIndex={0}
              className={`annotation-box ${selectedId === annotation.id ? 'is-selected' : ''}`}
              x={(box.x_center - box.width / 2) * width} y={(box.y_center - box.height / 2) * height}
              width={box.width * width} height={box.height * height}
              onClick={() => onSelect(annotation.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onSelect(annotation.id) }} />
            <text x={(box.x_center - box.width / 2) * width + 2} y={(box.y_center - box.height / 2) * height + 10}>{index + 1}</text>
          </g>
        })}
      </svg>
    </div>
  )
}

