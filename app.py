from __future__ import annotations

import io
import os
import uuid
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file, session

load_dotenv()

from extract_product_images import (
    DEFAULT_EDGE_MARGIN,
    DEFAULT_MERGE_KERNEL,
    DEFAULT_MIN_AREA,
    DEFAULT_MAX_WIDTH_RATIO,
    DEFAULT_REMOVE_BG,
    DEFAULT_RENDER_DPI,
    DEFAULT_WHITE_THRESHOLD,
    ExtractedImage,
    extract_images_to_list,
    parse_hex_color,
)
import gemini_client

app = Flask(__name__)
app.secret_key = os.urandom(24)

if os.getenv("VERCEL"):
    TEMP_DIR = Path("/tmp/desdoblar-temp")
else:
    TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# Almacenamiento en memoria de imágenes por sesión
_session_images: dict[str, list[ExtractedImage]] = {}


# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", gemini_configured=gemini_client.is_configured())


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No se recibió ningún archivo PDF."}), 400

    pdf_file = request.files["pdf"]
    if not pdf_file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "El archivo debe ser un PDF."}), 400

    session_id = str(uuid.uuid4())
    pdf_path = TEMP_DIR / f"{session_id}.pdf"
    pdf_file.save(str(pdf_path))

    session["session_id"] = session_id
    session["pdf_path"] = str(pdf_path)

    return jsonify({"session_id": session_id, "filename": pdf_file.filename})


# ---------------------------------------------------------------------------
# Procesar PDF
# ---------------------------------------------------------------------------

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json() or {}
    session_id = data.get("session_id") or session.get("session_id")

    if not session_id:
        return jsonify({"error": "No hay sesión activa. Sube un PDF primero."}), 400

    pdf_path = TEMP_DIR / f"{session_id}.pdf"
    if not pdf_path.exists():
        return jsonify({"error": "PDF no encontrado. Vuelve a subir el archivo."}), 404

    try:
        bg_hex = data.get("background_color", "efefef")
        background_color = parse_hex_color(bg_hex)

        extracted, summary = extract_images_to_list(
            pdf_path=pdf_path,
            start_page=int(data.get("start_page", 1)),
            end_page=data.get("end_page") or None,
            min_size=int(data.get("min_size", 500)),
            max_per_page=data.get("max_per_page") or None,
            canvas_size=int(data.get("canvas_size", 800)),
            background_color=background_color,
            render_dpi=int(data.get("render_dpi", DEFAULT_RENDER_DPI)),
            merge_kernel=int(data.get("merge_kernel", DEFAULT_MERGE_KERNEL)),
            min_area_ratio=float(data.get("min_area", DEFAULT_MIN_AREA)),
            max_width_ratio=float(data.get("max_width_ratio", DEFAULT_MAX_WIDTH_RATIO)),
            white_threshold=int(data.get("white_threshold", DEFAULT_WHITE_THRESHOLD)),
            edge_margin=float(data.get("edge_margin", DEFAULT_EDGE_MARGIN)),
            remove_bg=bool(data.get("remove_bg", DEFAULT_REMOVE_BG)),
            use_cv_fallback=not bool(data.get("no_cv_fallback", False)),
        )

        _session_images[session_id] = extracted

        images_info = [
            {"filename": img.filename, "page": img.page, "index": img.index}
            for img in extracted
        ]

        return jsonify({
            "session_id": session_id,
            "images": images_info,
            "summary": {
                "pages_processed": summary.pages_processed,
                "images_found": summary.images_saved,
                "cv_fallback_pages": summary.cv_fallback_pages,
                "pages_without_candidates": summary.pages_without_candidates,
            },
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Servir imagen individual (thumbnail)
# ---------------------------------------------------------------------------

@app.route("/image/<session_id>/<filename>")
def serve_image(session_id: str, filename: str):
    images = _session_images.get(session_id, [])
    for img in images:
        if img.filename == filename:
            buf = io.BytesIO()
            img.image.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            return send_file(buf, mimetype="image/jpeg")
    return jsonify({"error": "Imagen no encontrada."}), 404


# ---------------------------------------------------------------------------
# Descargar imágenes seleccionadas
# ---------------------------------------------------------------------------

@app.route("/download", methods=["POST"])
def download():
    data = request.get_json() or {}
    session_id = data.get("session_id") or session.get("session_id")
    selected = data.get("selected", [])  # lista de filenames
    fmt = data.get("format", "jpg").lower()

    if fmt not in ("jpg", "jpeg", "png"):
        fmt = "jpg"

    images = _session_images.get(session_id, [])
    if not images:
        return jsonify({"error": "No hay imágenes procesadas."}), 404

    to_export = [img for img in images if img.filename in selected] if selected else images

    if len(to_export) == 1:
        img = to_export[0]
        buf = io.BytesIO()
        if fmt == "png":
            img.image.save(buf, format="PNG")
            mimetype = "image/png"
            ext = "png"
        else:
            img.image.save(buf, format="JPEG", quality=95)
            mimetype = "image/jpeg"
            ext = "jpg"
        buf.seek(0)
        return send_file(buf, mimetype=mimetype, download_name=f"{img.filename}.{ext}")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in to_export:
            img_buf = io.BytesIO()
            if fmt == "png":
                img.image.save(img_buf, format="PNG")
                ext = "png"
            else:
                img.image.save(img_buf, format="JPEG", quality=95)
                ext = "jpg"
            zf.writestr(f"{img.filename}.{ext}", img_buf.getvalue())

    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip", download_name="imagenes-productos.zip", as_attachment=True)


# ---------------------------------------------------------------------------
# Gemini: mejorar imagen
# ---------------------------------------------------------------------------

@app.route("/gemini/enhance", methods=["POST"])
def gemini_enhance():
    data = request.get_json() or {}
    session_id = data.get("session_id") or session.get("session_id")
    filename = data.get("filename")

    images = _session_images.get(session_id, [])
    target = next((img for img in images if img.filename == filename), None)
    if not target:
        return jsonify({"error": "Imagen no encontrada."}), 404

    try:
        enhanced = gemini_client.enhance_image(target.image)
        # Reemplazar la imagen en la sesión
        idx = images.index(target)
        _session_images[session_id][idx] = ExtractedImage(
            filename=target.filename,
            image=enhanced,
            page=target.page,
            index=target.index,
        )
        return jsonify({"ok": True, "filename": filename})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error de Gemini: {exc}"}), 500


# ---------------------------------------------------------------------------
# Gemini: editar imagen con prompt
# ---------------------------------------------------------------------------

@app.route("/gemini/edit", methods=["POST"])
def gemini_edit():
    data = request.get_json() or {}
    session_id = data.get("session_id") or session.get("session_id")
    filename = data.get("filename")
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Debes ingresar un prompt de edición."}), 400

    images = _session_images.get(session_id, [])
    target = next((img for img in images if img.filename == filename), None)
    if not target:
        return jsonify({"error": "Imagen no encontrada."}), 404

    try:
        edited = gemini_client.edit_image(target.image, prompt)
        idx = images.index(target)
        _session_images[session_id][idx] = ExtractedImage(
            filename=target.filename,
            image=edited,
            page=target.page,
            index=target.index,
        )
        return jsonify({"ok": True, "filename": filename})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error de Gemini: {exc}"}), 500


# ---------------------------------------------------------------------------
# Configurar API key de Gemini en runtime
# ---------------------------------------------------------------------------

@app.route("/gemini/set-key", methods=["POST"])
def set_gemini_key():
    data = request.get_json() or {}
    key = data.get("api_key", "").strip()
    if not key:
        return jsonify({"error": "La clave no puede estar vacía."}), 400
    os.environ["GEMINI_API_KEY"] = key
    return jsonify({"ok": True, "configured": gemini_client.is_configured()})


# ---------------------------------------------------------------------------
# Estado de Gemini
# ---------------------------------------------------------------------------

@app.route("/gemini/status")
def gemini_status():
    return jsonify({"configured": gemini_client.is_configured()})


# ---------------------------------------------------------------------------
# Limpiar sesión
# ---------------------------------------------------------------------------

@app.route("/clear", methods=["POST"])
def clear_session():
    data = request.get_json() or {}
    session_id = data.get("session_id") or session.get("session_id")
    if session_id:
        _session_images.pop(session_id, None)
        pdf_path = TEMP_DIR / f"{session_id}.pdf"
        if pdf_path.exists():
            pdf_path.unlink()
    session.clear()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
