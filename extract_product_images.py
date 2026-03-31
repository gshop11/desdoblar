from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageOps

try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except Exception:
    cv2 = None
    np = None
    CV_AVAILABLE = False

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_PDF_PATH = Path(r"C:\Users\Norte Publicitario 1\Desktop\MouseWithoutBorders\CATÁLOGO JOMA 01.26.pdf")
DEFAULT_OUTPUT_DIR = Path("product-images")
DEFAULT_RENDER_DPI = 150   # DPI for page rendering in the CV fallback
DEFAULT_MERGE_KERNEL = 12  # Dilation kernel size (px) to merge nearby elements
DEFAULT_MIN_AREA = 0.02    # Minimum region area as fraction of page (2 %)
DEFAULT_MAX_WIDTH_RATIO = 0.80  # Skip regions wider than this fraction of the page (headers/footers)
DEFAULT_WHITE_THRESHOLD = 250  # Pixels brighter than this value are treated as background (0-255)
DEFAULT_EDGE_MARGIN = 0.05    # Fraction of page height to mask at top and bottom (headers/footers)
DEFAULT_REMOVE_BG = True      # Whether to remove the image background with rembg


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateImage:
    xref: int
    width: int
    height: int
    ext: str
    data: bytes

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class RegionBox:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ExtractionSummary:
    pages_processed: int
    images_saved: int
    pages_without_candidates: list[int]
    cv_fallback_pages: list[int]   # pages handled by the CV fallback


# ---------------------------------------------------------------------------
# Helpers — shared
# ---------------------------------------------------------------------------

def parse_hex_color(value: str) -> tuple[int, int, int]:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6:
        raise ValueError("Background color must be a 6-digit hex value like 'efefef'.")
    return tuple(int(normalized[index:index + 2], 16) for index in (0, 2, 4))


def remove_background(img: Image.Image) -> Image.Image:
    """Remove the background from a PIL image using rembg. Returns RGBA."""
    if rembg_remove is None:
        return img.convert("RGBA")
    return rembg_remove(img.convert("RGBA"))


def render_on_canvas(
    image_data: bytes,
    canvas_size: int,
    background_color: tuple[int, int, int],
    remove_bg: bool = False,
) -> Image.Image:
    """Fit an image inside a square canvas (used for embedded images)."""
    with Image.open(io.BytesIO(image_data)) as source_image:
        try:
            source_image = ImageOps.exif_transpose(source_image)
        except Exception:
            pass
        try:
            image = remove_background(source_image) if remove_bg else source_image.convert("RGBA")
        except Exception:
            image = source_image.convert("RGBA")
        scale = min(canvas_size / image.width, canvas_size / image.height)
        resized_size = (
            max(1, round(image.width * scale)),
            max(1, round(image.height * scale)),
        )
        resized = image.resize(resized_size, Image.Resampling.LANCZOS)

    background = Image.new("RGBA", (canvas_size, canvas_size), background_color + (255,))
    offset = (
        (canvas_size - resized.width) // 2,
        (canvas_size - resized.height) // 2,
    )
    background.paste(resized, offset, resized)
    return background.convert("RGB")


# ---------------------------------------------------------------------------
# Path A — embedded image extraction
# ---------------------------------------------------------------------------

def collect_page_candidates(
    doc: fitz.Document,
    page_index: int,
    min_size: int,
) -> list[CandidateImage]:
    seen_xrefs: set[int] = set()
    candidates: list[CandidateImage] = []

    for image_ref in doc.get_page_images(page_index, full=True):
        xref = image_ref[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        try:
            info = doc.extract_image(xref)
        except Exception:
            continue

        width = info["width"]
        height = info["height"]

        if width < min_size or height < min_size:
            continue

        candidates.append(
            CandidateImage(
                xref=xref,
                width=width,
                height=height,
                ext=info["ext"],
                data=info["image"],
            )
        )

    return sorted(candidates, key=lambda c: c.area, reverse=True)


# ---------------------------------------------------------------------------
# Path B — CV fallback (render page → detect regions)
# ---------------------------------------------------------------------------

def render_page_as_array(
    doc: fitz.Document,
    page_index: int,
    dpi: int,
) -> np.ndarray:
    """Renders a single PDF page to a numpy RGB array at the given DPI."""
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    try:
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
    except Exception:
        # Si falla con el colorspace original, renderizar sin corrección de color
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pix = pix.convert("rgb")
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)


def detect_product_regions(
    page_img: np.ndarray,
    min_area_ratio: float,
    merge_kernel: int,
    max_width_ratio: float = DEFAULT_MAX_WIDTH_RATIO,
    white_threshold: int = DEFAULT_WHITE_THRESHOLD,
    edge_margin: float = DEFAULT_EDGE_MARGIN,
) -> list[RegionBox]:
    """
    Finds rectangular product regions in a rendered page image.

    Strategy:
    1. Threshold to isolate non-white pixels.
    2. Dilate so nearby elements (image, title, price) within the same
       product merge into one blob, but adjacent products stay separate.
    3. Filter contours by area and aspect ratio to remove headers / footers.
    4. Return bounding boxes sorted top-to-bottom, left-to-right.
    """
    h, w = page_img.shape[:2]
    min_area = w * h * min_area_ratio
    max_area = w * h * 0.85

    gray = cv2.cvtColor(page_img, cv2.COLOR_RGB2GRAY)

    # Mask top and bottom bands so headers/footers don't merge with product cards
    margin_px = int(h * edge_margin)
    gray[:margin_px, :] = 255       # top band → white
    gray[h - margin_px:, :] = 255  # bottom band → white

    _, binary = cv2.threshold(gray, white_threshold, 255, cv2.THRESH_BINARY_INV)

    # Merge nearby elements within a product without bridging the gap to the
    # next product (keep kernel smaller than the inter-product spacing).
    kernel = np.ones((merge_kernel, merge_kernel), np.uint8)
    dilated = cv2.dilate(binary, kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes: list[RegionBox] = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)

        # Skip blobs outside the area range
        if not (min_area <= bw * bh <= max_area):
            continue

        # Skip horizontal banners (headers / footers) — very wide relative to height
        if bw > w * max_width_ratio:
            continue

        boxes.append(RegionBox(x=x, y=y, width=bw, height=bh))

    # Sort reading-order: rows first (band of 10 % page height), then columns
    row_band = max(1, h // 10)
    return sorted(boxes, key=lambda b: (b.y // row_band, b.x))


def crop_region_to_canvas(
    page_img: np.ndarray,
    region: RegionBox,
    canvas_size: int,
    background_color: tuple[int, int, int],
    remove_bg: bool = False,
) -> Image.Image:
    """Crops a detected region and centres it on a square canvas."""
    crop = page_img[
        region.y: region.y + region.height,
        region.x: region.x + region.width,
    ]
    pil_img = Image.fromarray(crop, "RGB")

    if remove_bg:
        pil_img = remove_background(pil_img)
    else:
        pil_img = pil_img.convert("RGBA")

    scale = min(canvas_size / pil_img.width, canvas_size / pil_img.height)
    new_size = (
        max(1, round(pil_img.width * scale)),
        max(1, round(pil_img.height * scale)),
    )
    resized = pil_img.resize(new_size, Image.Resampling.LANCZOS)

    background = Image.new("RGBA", (canvas_size, canvas_size), background_color + (255,))
    offset = (
        (canvas_size - resized.width) // 2,
        (canvas_size - resized.height) // 2,
    )
    background.paste(resized, offset, resized)
    return background.convert("RGB")


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

@dataclass
class ExtractedImage:
    filename: str
    image: Image.Image
    page: int
    index: int


def _has_content(image: Image.Image, background_color: tuple[int, int, int], min_content_ratio: float = 0.03) -> bool:
    """Devuelve True si la imagen tiene suficiente contenido no-fondo."""
    rgb = image.convert("RGB")
    bg_r, bg_g, bg_b = background_color
    total_pixels = rgb.width * rgb.height
    if total_pixels == 0:
        return False
    content_pixels = 0
    for r, g, b in rgb.getdata():
        if abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b) > 30:
            content_pixels += 1
    return (content_pixels / total_pixels) >= min_content_ratio


def extract_images_to_list(
    pdf_path: Path,
    start_page: int = 1,
    end_page: int | None = None,
    min_size: int = 500,
    max_per_page: int | None = None,
    canvas_size: int = 800,
    background_color: tuple[int, int, int] = (239, 239, 239),
    render_dpi: int = DEFAULT_RENDER_DPI,
    merge_kernel: int = DEFAULT_MERGE_KERNEL,
    min_area_ratio: float = DEFAULT_MIN_AREA,
    max_width_ratio: float = DEFAULT_MAX_WIDTH_RATIO,
    white_threshold: int = DEFAULT_WHITE_THRESHOLD,
    edge_margin: float = DEFAULT_EDGE_MARGIN,
    remove_bg: bool = DEFAULT_REMOVE_BG,
    use_cv_fallback: bool = True,
) -> tuple[list[ExtractedImage], ExtractionSummary]:
    """Extrae imágenes de un PDF y las retorna como objetos PIL en memoria."""
    extracted: list[ExtractedImage] = []
    pages_without_candidates: list[int] = []
    cv_fallback_pages: list[int] = []

    with fitz.open(pdf_path) as doc:
        final_page = min(end_page, len(doc)) if end_page is not None else len(doc)
        if start_page < 1 or final_page < start_page:
            raise ValueError("El rango de páginas no es válido.")

        for page_number in range(start_page, final_page + 1):
            page_index = page_number - 1

            # ── Path A: embedded images ─────────────────────────────────────
            candidates = collect_page_candidates(doc, page_index, min_size)

            if candidates:
                if max_per_page is not None:
                    candidates = candidates[:max_per_page]

                for candidate in candidates:
                    composed = render_on_canvas(
                        image_data=candidate.data,
                        canvas_size=canvas_size,
                        background_color=background_color,
                        remove_bg=remove_bg,
                    )
                    if not _has_content(composed, background_color):
                        continue
                    img_index = len([e for e in extracted if e.page == page_number]) + 1
                    filename = f"{page_number:03d}-img-{img_index:02d}"
                    extracted.append(ExtractedImage(
                        filename=filename,
                        image=composed,
                        page=page_number,
                        index=img_index,
                    ))
                continue

            # ── Path B: CV fallback ─────────────────────────────────────────
            if not use_cv_fallback or not CV_AVAILABLE:
                pages_without_candidates.append(page_number)
                continue

            page_img = render_page_as_array(doc, page_index, render_dpi)
            regions = detect_product_regions(
                page_img, min_area_ratio, merge_kernel,
                max_width_ratio, white_threshold, edge_margin,
            )

            if not regions:
                pages_without_candidates.append(page_number)
                continue

            cv_fallback_pages.append(page_number)

            if max_per_page is not None:
                regions = regions[:max_per_page]

            for region in regions:
                composed = crop_region_to_canvas(
                    page_img=page_img,
                    region=region,
                    canvas_size=canvas_size,
                    background_color=background_color,
                    remove_bg=remove_bg,
                )
                if not _has_content(composed, background_color):
                    continue
                img_index = len([e for e in extracted if e.page == page_number]) + 1
                filename = f"{page_number:03d}-img-{img_index:02d}"
                extracted.append(ExtractedImage(
                    filename=filename,
                    image=composed,
                    page=page_number,
                    index=img_index,
                ))

    pages_processed = final_page - start_page + 1
    summary = ExtractionSummary(
        pages_processed=pages_processed,
        images_saved=len(extracted),
        pages_without_candidates=pages_without_candidates,
        cv_fallback_pages=cv_fallback_pages,
    )
    return extracted, summary


def extract_candidate_images(
    pdf_path: Path,
    output_dir: Path,
    start_page: int,
    end_page: int | None,
    min_size: int,
    max_per_page: int | None,
    canvas_size: int,
    background_color: tuple[int, int, int],
    render_dpi: int,
    merge_kernel: int,
    min_area_ratio: float,
    max_width_ratio: float,
    white_threshold: int,
    edge_margin: float,
    remove_bg: bool,
    use_cv_fallback: bool,
) -> ExtractionSummary:
    output_dir.mkdir(parents=True, exist_ok=True)
    images_saved = 0
    pages_without_candidates: list[int] = []
    cv_fallback_pages: list[int] = []

    with fitz.open(pdf_path) as doc:
        final_page = min(end_page, len(doc)) if end_page is not None else len(doc)
        if start_page < 1 or final_page < start_page:
            raise ValueError("Page range is invalid.")

        for page_number in range(start_page, final_page + 1):
            page_index = page_number - 1

            # ── Path A: embedded images ────────────────────────────────────
            candidates = collect_page_candidates(doc, page_index, min_size)

            if candidates:
                if max_per_page is not None:
                    candidates = candidates[:max_per_page]

                for img_index, candidate in enumerate(candidates, start=1):
                    filename = f"{page_number:03d}-img-{img_index:02d}.jpg"
                    composed = render_on_canvas(
                        image_data=candidate.data,
                        canvas_size=canvas_size,
                        background_color=background_color,
                        remove_bg=remove_bg,
                    )
                    composed.save(output_dir / filename, format="JPEG", quality=95)
                    images_saved += 1
                continue

            # ── Path B: CV fallback ────────────────────────────────────────
            if not use_cv_fallback or not CV_AVAILABLE:
                pages_without_candidates.append(page_number)
                continue

            page_img = render_page_as_array(doc, page_index, render_dpi)
            regions = detect_product_regions(
                page_img, min_area_ratio, merge_kernel,
                max_width_ratio, white_threshold, edge_margin,
            )

            if not regions:
                pages_without_candidates.append(page_number)
                continue

            cv_fallback_pages.append(page_number)

            if max_per_page is not None:
                regions = regions[:max_per_page]

            for img_index, region in enumerate(regions, start=1):
                filename = f"{page_number:03d}-img-{img_index:02d}.jpg"
                composed = crop_region_to_canvas(
                    page_img=page_img,
                    region=region,
                    canvas_size=canvas_size,
                    background_color=background_color,
                    remove_bg=remove_bg,
                )
                composed.save(output_dir / filename, format="JPEG", quality=95)
                images_saved += 1

    pages_processed = final_page - start_page + 1
    return ExtractionSummary(
        pages_processed=pages_processed,
        images_saved=images_saved,
        pages_without_candidates=pages_without_candidates,
        cv_fallback_pages=cv_fallback_pages,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract product images from a PDF catalog.\n"
            "First tries to pull embedded image objects; if none are found on a page,\n"
            "falls back to rendering the page and detecting regions with OpenCV."
        )
    )
    parser.add_argument(
        "pdf",
        type=Path,
        nargs="?",
        default=DEFAULT_PDF_PATH,
        help="Path to the source PDF file.",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Directory where images will be written.",
    )
    parser.add_argument(
        "--start-page", type=int, default=1,
        help="First page to inspect (1-indexed).",
    )
    parser.add_argument(
        "--end-page", type=int, default=None,
        help="Last page to inspect (1-indexed). Defaults to end of document.",
    )
    parser.add_argument(
        "--min-size", type=int, default=500,
        help="Minimum width/height in pixels for embedded candidate images.",
    )
    parser.add_argument(
        "--max-per-page", type=int, default=None,
        help="Maximum images to save per page. Defaults to no limit.",
    )
    parser.add_argument(
        "--canvas-size", type=int, default=800,
        help="Square output size in pixels for each exported image.",
    )
    parser.add_argument(
        "--background-color", type=str, default="efefef",
        help="Canvas background color as a 6-digit hex value (default: efefef).",
    )
    # CV fallback arguments
    parser.add_argument(
        "--no-cv-fallback", action="store_true",
        help="Disable the OpenCV fallback (only use embedded image extraction).",
    )
    parser.add_argument(
        "--render-dpi", type=int, default=DEFAULT_RENDER_DPI,
        help=f"DPI for page rendering in the CV fallback (default: {DEFAULT_RENDER_DPI}).",
    )
    parser.add_argument(
        "--merge-kernel", type=int, default=DEFAULT_MERGE_KERNEL,
        help=(
            f"Dilation kernel size in pixels for merging nearby elements (default: {DEFAULT_MERGE_KERNEL}). "
            "Increase if multiple parts of the same product are detected separately; "
            "decrease if adjacent products are merged together."
        ),
    )
    parser.add_argument(
        "--min-area", type=float, default=DEFAULT_MIN_AREA,
        help=(
            f"Minimum region area as a fraction of the page (default: {DEFAULT_MIN_AREA}). "
            "E.g. 0.02 means a region must cover at least 2%% of the page."
        ),
    )
    parser.add_argument(
        "--max-width-ratio", type=float, default=DEFAULT_MAX_WIDTH_RATIO,
        help=(
            f"Max region width as a fraction of page width (default: {DEFAULT_MAX_WIDTH_RATIO}). "
            "Regions wider than this are considered headers/footers and are skipped."
        ),
    )
    parser.add_argument(
        "--white-threshold", type=int, default=DEFAULT_WHITE_THRESHOLD,
        help=(
            f"Grayscale value above which a pixel is considered background (default: {DEFAULT_WHITE_THRESHOLD}). "
            "Lower values detect darker backgrounds; raise it to catch near-white product cards."
        ),
    )
    parser.add_argument(
        "--edge-margin", type=float, default=DEFAULT_EDGE_MARGIN,
        help=(
            f"Fraction of page height to mask at top/bottom before detection (default: {DEFAULT_EDGE_MARGIN}). "
            "Prevents header/footer bands from merging with product cards at page edges."
        ),
    )
    parser.add_argument(
        "--remove-bg", action="store_true",
        default=DEFAULT_REMOVE_BG,
        help="Remove image backgrounds with rembg and replace them with the canvas background color.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    background_color = parse_hex_color(args.background_color)

    summary = extract_candidate_images(
        pdf_path=args.pdf,
        output_dir=args.output,
        start_page=args.start_page,
        end_page=args.end_page,
        min_size=args.min_size,
        max_per_page=args.max_per_page,
        canvas_size=args.canvas_size,
        background_color=background_color,
        render_dpi=args.render_dpi,
        merge_kernel=args.merge_kernel,
        min_area_ratio=args.min_area,
        max_width_ratio=args.max_width_ratio,
        white_threshold=args.white_threshold,
        edge_margin=args.edge_margin,
        remove_bg=args.remove_bg,
        use_cv_fallback=not args.no_cv_fallback,
    )

    print(f"Pages processed      : {summary.pages_processed}")
    print(f"Images saved         : {summary.images_saved}")

    if summary.cv_fallback_pages:
        joined = ", ".join(str(p) for p in summary.cv_fallback_pages)
        print(f"CV fallback pages    : {joined}")
    else:
        print("CV fallback pages    : none")

    if summary.pages_without_candidates:
        joined = ", ".join(str(p) for p in summary.pages_without_candidates)
        print(f"Pages with no result : {joined}")
    else:
        print("Pages with no result : none")

    print(f"Canvas size          : {args.canvas_size}x{args.canvas_size}")
    print(f"Background color     : #{args.background_color.lower().lstrip('#')}")
    print(f"Output directory     : {args.output.resolve()}")


if __name__ == "__main__":
    main()
