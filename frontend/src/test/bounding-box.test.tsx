import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { BoundingBoxOverlay } from '../components/BoundingBoxOverlay'
import type { ImageAnnotation } from '../types'

const annotations: ImageAnnotation[] = [
  { id: 'a1', line_index: 0, source_class_id: 999, source_class_name: 'Unknown source class 999', current_class_id: 999, coordinates: { x_center: 0.5, y_center: 0.5, width: 0.2, height: 0.4 }, decision: null, annotator_name: null, version: 0 },
]

test('selects a box locally in original image coordinates', async () => {
  const user = userEvent.setup()
  const onSelect = vi.fn()
  const fetchSpy = vi.spyOn(globalThis, 'fetch')
  render(<BoundingBoxOverlay imageUrl="/image.png" width={100} height={80} annotations={annotations} selectedId={null} onSelect={onSelect} />)

  const box = screen.getByRole('button', { name: /object 1/i })
  expect(box).toHaveAttribute('x', '40')
  expect(box).toHaveAttribute('y', '24')
  expect(box.closest('svg')).toHaveAttribute('viewBox', '0 0 100 80')
  await user.click(box)

  expect(onSelect).toHaveBeenCalledWith('a1')
  expect(fetchSpy).not.toHaveBeenCalled()
  fetchSpy.mockRestore()
})
