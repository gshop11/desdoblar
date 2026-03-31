from __future__ import annotations

import io
import re

import os
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

try:
    from huggingface_hub import InferenceClient
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

# Colores HTML por nombre en español/inglés
_COLORS: dict[str, tuple[int, int, int]] = {
    "blanco": (255, 255, 255), "white": (255, 255, 255),
    "negro": (0, 0, 0), "black": (0, 0, 0),
    "rojo": (220, 50, 50), "red": (220, 50, 50),
    "verde": (50, 180, 50), "green": (50, 180, 50),
    "azul": (50, 100, 220), "blue": (50, 100, 220),
    "amarillo": (255, 220, 0), "yellow": (255, 220, 0),
    "naranja": (255, 140, 0), "orange": (255, 140, 0),
    "rosado": (255, 150, 180), "rosa": (255, 150, 180), "pink": (255, 150, 180),
    "gris": (180, 180, 180), "gray": (180, 180, 180), "grey": (180, 180, 180),
    "morado": (150, 50, 200), "violeta": (150, 50, 200), "purple": (150, 50, 200),
    "celeste": (135, 206, 235), "cyan": (0, 200, 200),
    "beige": (245, 220, 185), "crema": (255, 253, 208),
    "transparente": None, "transparent": None,
}


def _pil_to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def enhance_image(image: Image.Image) -> Image.Image:
    """Mejora la calidad de imagen localmente con PIL (nitidez, contraste, color)."""
    result = image.convert("RGB")
    result = result.filter(ImageFilter.SHARPEN)
    result = result.filter(ImageFilter.SHARPEN)
    result = ImageEnhance.Contrast(result).enhance(1.2)
    result = ImageEnhance.Color(result).enhance(1.15)
    result = ImageEnhance.Brightness(result).enhance(1.05)
    return result


def _apply_background(image: Image.Image, color: tuple[int, int, int] | None) -> Image.Image:
    """Remueve el fondo y aplica color sólido."""
    try:
        from rembg import remove
        no_bg = remove(image.convert("RGBA"))
    except Exception:
        no_bg = image.convert("RGBA")

    if color is None:
        return no_bg

    bg = Image.new("RGBA", no_bg.size, color + (255,))
    bg.paste(no_bg, mask=no_bg.split()[3])
    return bg.convert("RGB")


def edit_image(image: Image.Image, prompt: str) -> Image.Image:
    """Edita imagen interpretando el prompt con transformaciones PIL."""
    p = prompt.lower().strip()
    result = image.convert("RGB")

    # ── Fondo de color ──────────────────────────────────────────────────────
    for name, color in _COLORS.items():
        if name in p and ("fondo" in p or "background" in p or "bg" in p):
            return _apply_background(image, color)

    # ── Voltear / flip ──────────────────────────────────────────────────────
    if any(w in p for w in ["voltear", "flip", "espejo", "mirror", "horizontal"]):
        if "vertical" in p:
            return ImageOps.flip(result)
        return ImageOps.mirror(result)

    if "vertical" in p and any(w in p for w in ["girar", "rotar", "rotate"]):
        return ImageOps.flip(result)

    # ── Rotación ────────────────────────────────────────────────────────────
    angle_match = re.search(r"(\d+)\s*(?:grados?|degrees?|°)", p)
    if angle_match:
        angle = int(angle_match.group(1))
        if any(w in p for w in ["izquierda", "left", "anti"]):
            angle = -angle
        return result.rotate(angle, expand=True)

    if any(w in p for w in ["90", "derecha", "right"]):
        return result.rotate(-90, expand=True)
    if any(w in p for w in ["270", "izquierda", "left"]):
        return result.rotate(90, expand=True)
    if any(w in p for w in ["180", "invertir", "invert"]) and "color" not in p:
        return result.rotate(180, expand=True)

    # ── Blanco y negro / sepia ───────────────────────────────────────────────
    if any(w in p for w in ["blanco y negro", "grayscale", "escala de grises", "gris", "bn", "b&n", "b/n"]):
        return ImageOps.grayscale(result).convert("RGB")

    if "sepia" in p:
        gray = ImageOps.grayscale(result)
        sepia = Image.new("RGB", gray.size)
        for x in range(gray.width):
            for y in range(gray.height):
                v = gray.getpixel((x, y))
                sepia.putpixel((x, y), (min(255, int(v * 1.08)), int(v * 0.86), int(v * 0.67)))
        return sepia

    # ── Brillo ──────────────────────────────────────────────────────────────
    if any(w in p for w in ["más brillo", "mas brillo", "más brillante", "brighter", "aumentar brillo"]):
        return ImageEnhance.Brightness(result).enhance(1.4)
    if any(w in p for w in ["menos brillo", "más oscuro", "mas oscuro", "darker", "oscurecer"]):
        return ImageEnhance.Brightness(result).enhance(0.65)

    # ── Contraste ───────────────────────────────────────────────────────────
    if any(w in p for w in ["más contraste", "mas contraste", "aumentar contraste"]):
        return ImageEnhance.Contrast(result).enhance(1.5)
    if any(w in p for w in ["menos contraste", "reducir contraste"]):
        return ImageEnhance.Contrast(result).enhance(0.7)

    # ── Nitidez ─────────────────────────────────────────────────────────────
    if any(w in p for w in ["nitidez", "sharpen", "enfocar", "más nítido"]):
        result = result.filter(ImageFilter.SHARPEN)
        return result.filter(ImageFilter.SHARPEN)

    # ── Recortar / centrar producto ─────────────────────────────────────────
    if any(w in p for w in ["recortar", "crop", "centrar", "center", "ajustar"]):
        bbox = result.getbbox()
        if bbox:
            pad = 20
            w, h = result.size
            x1 = max(0, bbox[0] - pad)
            y1 = max(0, bbox[1] - pad)
            x2 = min(w, bbox[2] + pad)
            y2 = min(h, bbox[3] + pad)
            return result.crop((x1, y1, x2, y2))

    # ── Mejorar (fallback) ───────────────────────────────────────────────────
    if any(w in p for w in ["mejorar", "enhance", "calidad", "quality"]):
        return enhance_image(image)

    raise RuntimeError(
        f"No entendí el comando: '{prompt}'. "
        "Prueba: 'fondo blanco', 'fondo rojo', 'voltear', 'rotar 90°', "
        "'blanco y negro', 'más brillo', 'más contraste', 'recortar'."
    )


def is_configured() -> bool:
    """Siempre disponible (edición PIL no requiere API key)."""
    return True
