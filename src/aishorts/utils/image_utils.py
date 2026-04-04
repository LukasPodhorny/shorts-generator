from PIL import Image, ImageDraw, ImageFilter, ImageColor, ImageChops
import os
from pydantic import BaseModel
import math


class ImageStyle(BaseModel):
    corner_radius: int = 0
    shadow_blur: int = 0
    shadow_offset: tuple[int, int] = (0, 0)
    shadow_color: str = "#000000"
    shadow_opacity: float = 0.5


def crop_to_aspect_ratio(
    input_path: str,
    output_path: str,
    target_ratio: tuple[int, int] = (16, 9),
) -> str:
    """
    Crops an image to the specified aspect ratio by center-cropping.

    Args:
        input_path: Path to the source image.
        output_path: Path where the cropped image will be saved.
        target_ratio: Target aspect ratio as (width, height) tuple. Default is 16:9.

    Returns:
        The output_path.
    """
    with Image.open(input_path) as img:
        img = img.convert("RGBA")

        current_width, current_height = img.size
        target_width, target_height = target_ratio

        # Calculate target aspect ratio
        target_aspect = target_width / target_height
        current_aspect = current_width / current_height

        if current_aspect > target_aspect:
            # Image is wider than target - crop width
            new_width = int(current_height * target_aspect)
            new_height = current_height
        else:
            # Image is taller than target - crop height
            new_width = current_width
            new_height = int(current_width / target_aspect)

        # Calculate crop position (center crop)
        left = (current_width - new_width) // 2
        top = (current_height - new_height) // 2
        right = left + new_width
        bottom = top + new_height

        # Crop and save
        cropped = img.crop((left, top, right, bottom))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        cropped.save(output_path)

    return output_path


def crop_to_16_9(input_path: str, output_path: str) -> str:
    """Convenience function to crop to 16:9 aspect ratio."""
    return crop_to_aspect_ratio(input_path, output_path, (16, 9))


def style_image(
    input_path: str,
    output_path: str,
    image_style: ImageStyle | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
) -> str:
    """
    Applies styling to an image: rounded corners and drop shadow.

    Args:
        input_path: Path to the source image.
        output_path: Path where the processed image will be saved.
        max_width: Maximum width of the output image.
        max_height: Maximum height of the output image.
        corner_radius: Radius of the rounded corners in pixels.
        shadow_blur: Blur radius for the drop shadow.
        shadow_offset: Tuple (x, y) for shadow offset.
        shadow_color: Color of the shadow (hex code or name).
        shadow_opacity: Opacity of the shadow (0.0 to 1.0).

    Returns:
        The output_path.
    """
    if image_style is None:
        image_style = ImageStyle()

    with Image.open(input_path) as img:
        img = img.convert("RGBA")

        if max_width and max_height:
            img.thumbnail((max_width, max_height), Image.LANCZOS)

        # 1. Apply Rounded Corners
        if image_style.corner_radius > 0:
            factor = 4
            mask = Image.new("L", (img.width * factor, img.height * factor), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle(
                [(0, 0), (img.width * factor - 1, img.height * factor - 1)],
                radius=image_style.corner_radius * factor,
                fill=255,
            )
            mask = mask.resize(img.size, Image.LANCZOS)

            # Combine with existing alpha if present to preserve transparency
            if "A" in img.getbands():
                alpha = img.split()[-1]
                combined_alpha = ImageChops.multiply(alpha, mask)
                img.putalpha(combined_alpha)
            else:
                img.putalpha(mask)

        # 2. Apply Drop Shadow
        if image_style.shadow_blur > 0 or image_style.shadow_offset != (0, 0):
            # Calculate margins needed for the shadow
            off_x, off_y = image_style.shadow_offset
            blur_margin = int(image_style.shadow_blur * 3)  # Allow space for blur decay

            # Calculate new canvas bounds
            # Original image is at (0,0) relative to itself
            # Shadow is at (off_x, off_y)
            # We need to encompass both, plus blur margins
            min_x = min(0, off_x - blur_margin)
            min_y = min(0, off_y - blur_margin)
            max_x = max(img.width, off_x + img.width + blur_margin)
            max_y = max(img.height, off_y + img.height + blur_margin)

            canvas_w = max_x - min_x
            canvas_h = max_y - min_y

            # Create canvas
            canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

            # Create shadow layer
            shadow_shape = img.getchannel("A")
            shadow_rgb = ImageColor.getrgb(image_style.shadow_color)
            shadow_layer = Image.new("RGBA", img.size, shadow_rgb)
            shadow_layer.putalpha(shadow_shape)

            # Position for shadow on canvas
            shadow_pos = (-min_x + off_x, -min_y + off_y)

            # Create a separate canvas for shadow to blur it cleanly
            shadow_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            shadow_canvas.paste(shadow_layer, shadow_pos, shadow_layer)

            if image_style.shadow_blur > 0:
                shadow_canvas = shadow_canvas.filter(
                    ImageFilter.GaussianBlur(image_style.shadow_blur)
                )

            # Apply opacity to shadow
            if image_style.shadow_opacity < 1.0:
                r, g, b, a = shadow_canvas.split()
                a = a.point(lambda i: int(i * image_style.shadow_opacity))
                shadow_canvas.putalpha(a)

            # Paste original image on top
            img_pos = (-min_x, -min_y)
            shadow_canvas.paste(img, img_pos, img)

            img = shadow_canvas

        # Save result
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path)

    return output_path
