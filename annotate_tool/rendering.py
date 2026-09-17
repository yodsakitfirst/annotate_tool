import math

from PIL import Image, ImageDraw, ImageFont

from annotate_tool.models import Annotation, ClassInfo
from annotate_tool.yolo import box_pixels


def draw_numbered_boxes(
    image: Image.Image,
    annotations: tuple[Annotation, ...],
    selected_index: int | None,
) -> Image.Image:
    rendered = image.convert("RGB").copy()
    draw = ImageDraw.Draw(rendered)
    font = ImageFont.load_default(size=16)
    for object_index, annotation in enumerate(annotations):
        left, top, right, bottom = box_pixels(annotation, rendered.size)
        color = "#FACC15" if object_index == selected_index else "#EF4444"
        draw.rectangle((left, top, max(left, right - 1), max(top, bottom - 1)), outline=color, width=3)
        label = str(object_index + 1)
        text_box = draw.textbbox((0, 0), label, font=font)
        badge_width = text_box[2] - text_box[0] + 10
        badge_height = text_box[3] - text_box[1] + 8
        badge_top = max(0, top - badge_height)
        draw.rectangle((left, badge_top, left + badge_width, badge_top + badge_height), fill=color)
        draw.text((left + 5, badge_top + 3), label, fill="black", font=font)
    return rendered


def crop_annotation(
    image: Image.Image,
    annotation: Annotation,
    padding_ratio: float = 0.15,
) -> Image.Image:
    if padding_ratio < 0:
        raise ValueError("padding ratio cannot be negative")
    left, top, right, bottom = box_pixels(annotation, image.size)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise ValueError("annotation has no visible crop area")
    x_padding = math.ceil(width * padding_ratio)
    y_padding = math.ceil(height * padding_ratio)
    crop_box = (
        max(0, left - x_padding),
        max(0, top - y_padding),
        min(image.width, right + x_padding),
        min(image.height, bottom + y_padding),
    )
    return image.crop(crop_box).convert("RGB")


def reference_placeholder(class_info: ClassInfo) -> Image.Image:
    image = Image.new("RGB", (240, 180), "#E5E7EB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    draw.multiline_text(
        (16, 55),
        f"No reference image\nID {class_info.class_id}\n{class_info.name}",
        fill="#374151",
        font=font,
        spacing=7,
    )
    return image
