import base64
from io import BytesIO

from PIL import Image
import streamlit as st

from annotate_tool.models import Annotation
from annotate_tool.workflow import ObjectKey
from annotate_tool.yolo import box_pixels


COMPONENT_HTML = """
<div class="clickable-image">
  <img alt="Annotated source image" />
  <svg aria-label="Clickable annotation boxes"></svg>
</div>
"""

COMPONENT_CSS = """
.clickable-image { position: relative; width: 100%; line-height: 0; }
.clickable-image img { display: block; width: 100%; height: auto; border-radius: 0.5rem; }
.clickable-image svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.clickable-image rect { fill: transparent; stroke: #ff3131; stroke-width: 2; vector-effect: non-scaling-stroke; cursor: pointer; pointer-events: all; }
.clickable-image rect:hover { fill: rgba(255, 49, 49, 0.18); stroke-width: 3; }
.clickable-image rect.selected { stroke: #00d4ff; stroke-width: 4; }
.clickable-image text { fill: white; stroke: #b00000; stroke-width: 3px; paint-order: stroke; font: bold 13px sans-serif; pointer-events: none; }
"""

COMPONENT_JS = """
export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector('.clickable-image');
  const image = root.querySelector('img');
  const svg = root.querySelector('svg');
  image.src = `data:image/png;base64,${data.image_base64}`;
  svg.setAttribute('viewBox', `0 0 ${data.width} ${data.height}`);
  svg.replaceChildren();
  const namespace = 'http://www.w3.org/2000/svg';
  data.boxes.forEach((box) => {
    const rectangle = document.createElementNS(namespace, 'rect');
    rectangle.setAttribute('x', box.x);
    rectangle.setAttribute('y', box.y);
    rectangle.setAttribute('width', box.width);
    rectangle.setAttribute('height', box.height);
    rectangle.setAttribute('rx', 2);
    if (box.selected) rectangle.classList.add('selected');
    rectangle.onclick = (event) => {
      event.stopPropagation();
      setTriggerValue('selected', box.line_index);
    };
    svg.appendChild(rectangle);

    const label = document.createElementNS(namespace, 'text');
    label.setAttribute('x', box.x + 3);
    label.setAttribute('y', Math.max(13, box.y + 13));
    label.textContent = String(box.number);
    svg.appendChild(label);
  });
}
"""


def clickable_box_image(**mount_arguments):
    renderer = st.components.v2.component(
        "clickable_box_image",
        html=COMPONENT_HTML,
        css=COMPONENT_CSS,
        js=COMPONENT_JS,
    )
    return renderer(**mount_arguments)


def build_clickable_image_payload(
    image: Image.Image,
    annotations: tuple[Annotation, ...],
    selected_line_index: int | None,
) -> dict[str, object]:
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    boxes = []
    for number, annotation in enumerate(annotations, start=1):
        left, top, right, bottom = box_pixels(annotation, image.size)
        boxes.append(
            {
                "line_index": annotation.line_index,
                "number": number,
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top,
                "selected": annotation.line_index == selected_line_index,
            }
        )
    return {
        "image_base64": base64.b64encode(output.getvalue()).decode("ascii"),
        "width": image.width,
        "height": image.height,
        "boxes": boxes,
    }


def clicked_object_index(
    objects: tuple[ObjectKey, ...],
    image_index: int,
    line_index: int,
) -> int | None:
    return next(
        (
            index
            for index, item in enumerate(objects)
            if item.image_index == image_index and item.line_index == line_index
        ),
        None,
    )
