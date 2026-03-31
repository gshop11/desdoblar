"""
Sube imágenes JOMA directo a Vercel Blob e inserta registros en Neon (PostgreSQL).
Evita el endpoint /api/media de Payload que falla en Vercel serverless.
"""
import io
import sys
import uuid
import json
import requests
import psycopg2
from pathlib import Path
from PIL import Image
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Configuración ────────────────────────────────────────────────────────────
BLOB_TOKEN  = "vercel_blob_rw_6Nu9xV9pTtJECMvj_oeDZorVsVXRYzFf8zQg45kDooaBVv4"
DB_URL      = "postgresql://neondb_owner:npg_NZAMG3z0cqif@ep-lucky-band-ac4d7oxd.sa-east-1.aws.neon.tech/neondb?sslmode=require"
JOMA_DIR    = Path(__file__).parent / "output-joma"
API_BASE    = "https://plus-sport-mkar.vercel.app/api"
ADMIN_EMAIL = "gshop.trujillo@gmail.com"
ADMIN_PASS  = "C@mbio2024."

# ── Datos del catálogo JOMA ──────────────────────────────────────────────────
# imagen → (codigo, precio, retail, tallas_str, segmento)
PRODUCTOS = {
    "005-img-01.jpg": ("TOUW2528IN",   309, 399, "39 AL 43.5", "unisex"),
    "006-img-01.jpg": ("TOUW250IN",    309, 399, "39 AL 43.5", "unisex"),
    "007-img-01.jpg": ("TORW2529TF",   299, 372, "39 AL 43.5", "unisex"),
    "008-img-01.jpg": ("TORW2503TF",   299, 372, "39 AL 43.5", "unisex"),
    "009-img-01.jpg": ("FS2501IN",     290, 380, "39 AL 43.5", "unisex"),
    "010-img-01.jpg": ("GAMW2523IN",   229, 269, "39 AL 43.5", "unisex"),
    "011-img-01.jpg": ("GAMW2501IN",   229, 249, "39 AL 43.5", "unisex"),
    "012-img-01.jpg": ("TORW2501IN",   299, 372, "39 AL 43.5", "unisex"),
    "013-img-01.jpg": ("TORW2507IN",   299, 372, "39 AL 43.5", "unisex"),
    "014-img-01.jpg": ("TORW2517IN",   299, 372, "39 AL 43.5", "unisex"),
    "015-img-01.jpg": ("TORW2509IN",   299, 372, "39 AL 43.5", "unisex"),
    "016-img-01.jpg": ("TOPW2576IN",   249, 310, "39 AL 43.5", "unisex"),
    "017-img-01.jpg": ("TOPS2121IN",   249, 310, "39 AL 43.5", "unisex"),
    "018-img-01.jpg": ("BSCRES2502IN", 219, 249, "38 AL 41",   "unisex"),
    "019-img-01.jpg": ("MUNW2503TF",   199, 249, "39 AL 43.5", "unisex"),
    "020-img-01.jpg": ("MUNW2504TF",   199, 249, "39 AL 43.5", "unisex"),
    "021-img-01.jpg": ("2303TF",       149, 179, "39 AL 43.5", "unisex"),
    "022-img-01.jpg": ("MAXW2409TF",   149, 179, "39 AL 43.5", "unisex"),
    "023-img-01.jpg": ("2501TF",       149, 179, "39 AL 43.5", "unisex"),
    "024-img-01.jpg": ("MAXS2502TF",   149, 179, "39 AL 43.5", "unisex"),
    "026-img-01.jpg": ("MAXS2527TF",   149, 249, "39 AL 43.5", "unisex"),
    "027-img-01.jpg": ("2520IN",       149, 249, "39 AL 43.5", "unisex"),
    "028-img-01.jpg": ("2508TF",       149, 249, "39 AL 43.5", "unisex"),
    "029-img-01.jpg": ("2509TF",       149, 249, "39 AL 43.5", "unisex"),
    "030-img-01.jpg": ("MAX2433",      149, 179, "41",          "unisex"),
    "031-img-01.jpg": ("2304TF",       159, 189, "40 AL 43",   "unisex"),
    "032-img-01.jpg": ("2503TF",       159, 189, "40 AL 43",   "unisex"),
    "033-img-01.jpg": ("2509IN",       159, 249, "39 AL 43.5", "unisex"),
    "034-img-01.jpg": ("2535TF",       169, 249, "39 AL 43.5", "unisex"),
    "035-img-01.jpg": ("CANW2505T",    159, 249, "39 AL 43.5", "unisex"),
    "036-img-01.jpg": ("CANW2502IN",   159, 249, "39 AL 43.5", "unisex"),
    "037-img-01.jpg": ("DRIW2503TF",   159, 178, "39 AL 43.5", "unisex"),
    "038-img-01.jpg": ("DRIW2501TF",   159, 178, "39 AL 43.5", "unisex"),
    "039-img-01.jpg": ("DRIW2527IN",   159, 178, "39 AL 43.5", "unisex"),
    "040-img-01.jpg": ("DRIW2502TF",   159, 178, "39 AL 43.5", "unisex"),
    "041-img-01.jpg": ("DRIW2510IN",   159, 178, "39 AL 43.5", "unisex"),
    "042-img-01.jpg": ("DRI2501TF",    159, 178, "39 AL 43.5", "unisex"),
    "043-img-01.jpg": ("AGUS2507",     139, 169, "40 AL 43",   "unisex"),
    "044-img-01.jpg": ("AGUS2504TF",   139, 169, "39 AL 43.5", "unisex"),
    "045-img-01.jpg": ("2503TF_B",     139, 169, "39 AL 43.5", "unisex"),
    "046-img-01.jpg": ("2501TF_B",     139, 169, "39 AL 43.5", "unisex"),
    "047-img-01.jpg": ("2321TF",       139, 169, "39 AL 43.5", "unisex"),
    "048-img-01.jpg": ("2502TF_B",     139, 169, "39 AL 43.5", "unisex"),
    "049-img-01.jpg": ("AGU2504",      139, 169, "39 AL 43.5", "unisex"),
    # Niños
    "052-img-01.jpg": ("TOJ2502TF",    119, 149, "31 AL 38",   "ninos"),
    "053-img-01.jpg": ("TOJ2501TF",    119, 149, "31 AL 38",   "ninos"),
    "054-img-01.jpg": ("EVJW2501TF",   119, 189, "34 AL 39",   "ninos"),
    "055-img-01.jpg": ("TOJ2505TF",    119, 149, "31 AL 38",   "ninos"),
    "056-img-01.jpg": ("EVJW2503TF",   119, 189, "34 AL 39",   "ninos"),
    "057-img-01.jpg": ("EVJW2503IN",   119, 189, "34 AL 39",   "ninos"),
    "058-img-01.jpg": ("EVJW2532IN",   119, 189, "34 Y 36",    "ninos"),
    "059-img-01.jpg": ("TOJW2503",     119, 149, "31 AL 38",   "ninos"),
}


def parse_tallas(s: str) -> list[tuple[str, int]]:
    s = s.strip().upper()
    result = []
    if "AL" in s:
        parts = s.split("AL")
        try:
            t = float(parts[0].strip())
            end = float(parts[1].strip())
            while t <= end + 0.01:
                label = str(int(t)) if t == int(t) else str(t)
                result.append((label, 0))
                t += 0.5
        except Exception:
            result.append((s, 0))
    elif "Y" in s:
        for part in s.split("Y"):
            part = part.strip()
            if part:
                result.append((part, 0))
    else:
        result.append((s, 0))
    return result


def upload_blob(path: Path, slug: str) -> tuple[str, int, int, int] | None:
    """Sube archivo a Vercel Blob. Retorna (url, width, height, filesize)."""
    with open(path, "rb") as f:
        data = f.read()
    img = Image.open(path)
    w, h = img.size
    r = requests.put(
        f"https://blob.vercel-storage.com/{slug}.jpg",
        headers={
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "x-content-type": "image/jpeg",
            "x-add-random-suffix": "1",
        },
        data=data,
    )
    if r.status_code == 200:
        url = r.json()["url"]
        return url, w, h, len(data)
    print(f"  ERROR blob {path.name}: {r.status_code} {r.text[:100]}")
    return None


def insert_media(cur, url: str, filename: str, w: int, h: int, size: int, alt: str) -> int:
    now = datetime.now(timezone.utc)
    cur.execute("""
        INSERT INTO media (alt, updated_at, created_at, url, thumbnail_u_r_l, filename,
            mime_type, filesize, width, height,
            sizes_thumbnail_url, sizes_thumbnail_width, sizes_thumbnail_height,
            sizes_thumbnail_mime_type, sizes_thumbnail_filesize, sizes_thumbnail_filename,
            sizes_card_url, sizes_card_width, sizes_card_height,
            sizes_card_mime_type, sizes_card_filesize, sizes_card_filename,
            sizes_banner_url, sizes_banner_width, sizes_banner_height,
            sizes_banner_mime_type, sizes_banner_filesize, sizes_banner_filename)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        alt, now, now, url, url, filename,
        "image/jpeg", size, w, h,
        url, 400, 400, "image/jpeg", size, filename,
        url, 800, 800, "image/jpeg", size, filename,
        url, 1920, 600, "image/jpeg", size, filename,
    ))
    return cur.fetchone()[0]


def insert_producto(cur, nombre, slug, sku, precio, retail, cat_id, marca_id,
                    segmento, media_id, tallas, descripcion_text):
    now = datetime.now(timezone.utc)
    desc = {
        "root": {
            "type": "root", "version": 1, "direction": "ltr", "format": "", "indent": 0,
            "children": [{
                "type": "paragraph", "version": 1, "direction": "ltr", "format": "", "indent": 0,
                "children": [{"type": "text", "text": descripcion_text, "version": 1}]
            }]
        }
    }
    cur.execute("""
        INSERT INTO productos
            (nombre, slug, descripcion, sku, precio, precio_anterior,
             categoria_id, marca_id, segmento, imagen_principal_id,
             stock, etiqueta, destacado, nuevo_ingreso, activo,
             updated_at, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        nombre, slug, json.dumps(desc), sku, precio, retail,
        cat_id, marca_id, segmento, media_id,
        0, "nuevo", False, True, True,
        now, now,
    ))
    prod_id = cur.fetchone()[0]

    # Insertar tallas
    for order, (talla, stock) in enumerate(tallas, start=1):
        cur.execute("""
            INSERT INTO productos_tallas (_order, _parent_id, id, talla, stock)
            VALUES (%s, %s, %s, %s, %s)
        """, (order, prod_id, str(uuid.uuid4()), talla, stock))

    return prod_id


def get_or_create(cur, conn, table, slug_col, nombre, slug, extra=None):
    cur.execute(f"SELECT id FROM {table} WHERE {slug_col}=%s", (slug,))
    row = cur.fetchone()
    if row:
        return row[0]
    now = datetime.now(timezone.utc)
    fields = {"nombre": nombre, slug_col: slug, "updated_at": now, "created_at": now, "activa": True}
    if extra:
        fields.update(extra)
    cols = ", ".join(fields.keys())
    vals = ", ".join(["%s"] * len(fields))
    cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals}) RETURNING id", list(fields.values()))
    conn.commit()
    return cur.fetchone()[0]


def main():
    print("=== CONECTANDO A NEON ===")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("=== MARCA Y CATEGORÍAS ===")
    joma_id       = get_or_create(cur, conn, "marcas",    "slug", "JOMA",              "joma")
    cat_adulto_id = get_or_create(cur, conn, "categorias","slug", "Zapatillas Adulto", "zapatillas-adulto")
    cat_ninos_id  = get_or_create(cur, conn, "categorias","slug", "Zapatillas Ninos",  "zapatillas-ninos")
    print(f"  JOMA id={joma_id} | Adulto id={cat_adulto_id} | Ninos id={cat_ninos_id}")

    print(f"\n=== SUBIENDO {len(PRODUCTOS)} PRODUCTOS ===")
    ok = fail = 0

    for filename, (codigo, precio, retail, tallas_str, segmento) in PRODUCTOS.items():
        img_path = JOMA_DIR / filename
        if not img_path.exists():
            print(f"  WARN imagen no encontrada: {filename}")
            fail += 1
            continue

        slug_img = f"joma-{codigo.lower().replace('_', '-')}"
        result = upload_blob(img_path, slug_img)
        if not result:
            fail += 1
            continue
        blob_url, w, h, size = result

        try:
            media_id = insert_media(cur, blob_url, f"{slug_img}.jpg", w, h, size, f"Joma {codigo}")
            conn.commit()

            cat_id = cat_ninos_id if segmento == "ninos" else cat_adulto_id
            nombre = f"Joma {codigo}"
            slug   = f"joma-{codigo.lower().replace('_', '-')}"
            desc   = f"Zapatilla JOMA {codigo}. Tallas: {tallas_str}."
            tallas = parse_tallas(tallas_str)

            prod_id = insert_producto(cur, nombre, slug, codigo, precio, retail,
                                      cat_id, joma_id, segmento, media_id, tallas, desc)
            conn.commit()

            print(f"  OK  {nombre} | S/{precio} | {tallas_str} | media={media_id} prod={prod_id}")
            ok += 1
        except Exception as e:
            conn.rollback()
            print(f"  ERROR {filename}: {e}")
            fail += 1

    cur.close()
    conn.close()
    print(f"\n=== RESULTADO: {ok} productos subidos, {fail} errores ===")


if __name__ == "__main__":
    main()
