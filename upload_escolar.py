"""
Sube productos del catálogo ESCOLAR directamente a Vercel Blob + Neon.
Marcas: Adidas (pág 5-10), Puma (pág 11-14), Convert (pág 15-23), Tigre (pág 24-27)
"""
import io, sys, uuid, json, requests, psycopg2
from pathlib import Path
from PIL import Image
from datetime import datetime, timezone
from urllib.parse import urlparse
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BLOB_TOKEN = "vercel_blob_rw_6Nu9xV9pTtJECMvj_oeDZorVsVXRYzFf8zQg45kDooaBVv4"
BLOB_BASE  = "https://6nu9xv9pttjecmvj.public.blob.vercel-storage.com"
DB_URL     = "postgresql://neondb_owner:npg_NZAMG3z0cqif@ep-lucky-band-ac4d7oxd.sa-east-1.aws.neon.tech/neondb?sslmode=require"
ESCOLAR_DIR = Path(__file__).parent / "output-escolar"

# imagen → (marca_slug, codigo, precio, retail, tallas_str, segmento)
PRODUCTOS = {
    # ADIDAS
    "005-img-01.jpg": ("adidas", "GW1987",      129, 149, "28.5 AL 35",   "ninos"),
    "006-img-01.jpg": ("adidas", "GW6440",      129, 149, "28.5 AL 35",   "ninos"),
    "007-img-01.jpg": ("adidas", "GW6422",      129, 149, "30 AL 35",     "ninos"),
    "008-img-01.jpg": ("adidas", "GW6423",      129, 149, "28.5 AL 39.5", "ninos"),
    "009-img-01.jpg": ("adidas", "IE9020",      129, 149, "28.5 AL 35",   "ninos"),
    "010-img-01.jpg": ("adidas", "IE8688",      139, 159, "35 AL 39",     "ninos"),
    # PUMA
    "011-img-01.jpg": ("puma",   "193623-01",   129, 149, "28 AL 34.5",   "ninos"),
    "012-img-01.jpg": ("puma",   "193623-02",   129, 149, "28 AL 34.5",   "ninos"),
    "013-img-01.jpg": ("puma",   "394252-08",   139, 189, "36 AL 39",     "ninos"),
    "014-img-01.jpg": ("puma",   "394252-11",   139, 189, "36 AL 39",     "ninos"),
    # CONVERT
    "015-img-01.jpg": ("convert","302630L-WHT", 129, 149, "28 AL 38",     "ninos"),
    "016-img-01.jpg": ("convert","1077BB-XS",    85, 110, "27 AL 32",     "ninos"),
    "017-img-01.jpg": ("convert","1077BB-M",    100, 120, "33 AL 39",     "ninos"),
    "018-img-01.jpg": ("convert","1077BB-XL",   120, 150, "40 AL 46",     "unisex"),
    "019-img-01.jpg": ("convert","126BB-XS",     85, 110, "27 AL 32",     "ninos"),
    "020-img-01.jpg": ("convert","126BB-M",     100, 120, "33 AL 38",     "ninos"),
    "021-img-01.jpg": ("convert","126BB-XL",    120, 150, "40 AL 46",     "unisex"),
    "022-img-01.jpg": ("convert","1109BB-XS",    89, 110, "27 AL 32",     "ninos"),
    "023-img-01.jpg": ("convert","1109BB-M",    105, 125, "33 AL 39",     "ninos"),
    # TIGRE
    "024-img-01.jpg": ("tigre",  "TI88916100",   45,  55, "27 AL 37",     "ninos"),
    "025-img-01.jpg": ("tigre",  "TI88916100-A", 49,  59, "38 AL 46",     "unisex"),
    "026-img-01.jpg": ("tigre",  "TI55916270",   30,  40, "27 AL 39",     "ninos"),
    "027-img-01.jpg": ("tigre",  "TI5591796",    30,  42, "33 AL 39",     "ninos"),
}

MARCAS = {
    "adidas":  "Adidas",
    "puma":    "Puma",
    "convert": "Convert",
    "tigre":   "Tigre",
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

    print("=== MARCAS Y CATEGORÍAS ===")
    marca_ids = {}
    for slug, nombre in MARCAS.items():
        marca_ids[slug] = get_or_create(cur, conn, "marcas", "slug", nombre, slug)
        print(f"  {nombre} id={marca_ids[slug]}")

    cat_ninos_id  = get_or_create(cur, conn, "categorias", "slug", "Zapatillas Ninos",  "zapatillas-ninos")
    cat_adulto_id = get_or_create(cur, conn, "categorias", "slug", "Zapatillas Adulto", "zapatillas-adulto")
    print(f"  Cat Ninos id={cat_ninos_id} | Cat Adulto id={cat_adulto_id}")

    print(f"\n=== SUBIENDO {len(PRODUCTOS)} PRODUCTOS ===")
    ok = fail = 0

    for filename, (marca_slug, codigo, precio, retail, tallas_str, segmento) in PRODUCTOS.items():
        img_path = ESCOLAR_DIR / filename
        if not img_path.exists():
            print(f"  WARN imagen no encontrada: {filename}")
            fail += 1
            continue

        marca_nombre = MARCAS[marca_slug]
        slug_img = f"{marca_slug}-{codigo.lower().replace('_', '-').replace('.', '-')}"
        result = upload_blob(img_path, slug_img)
        if not result:
            fail += 1
            continue
        blob_url, w, h, size = result
        real_filename = os.path.basename(urlparse(blob_url).path)

        try:
            media_id = insert_media(cur, blob_url, real_filename, w, h, size, f"{marca_nombre} {codigo}")
            conn.commit()

            cat_id = cat_ninos_id if segmento == "ninos" else cat_adulto_id
            nombre = f"{marca_nombre} {codigo}"
            slug   = slug_img
            desc   = f"Zapatilla {marca_nombre} modelo {codigo}. Tallas: {tallas_str}."
            tallas = parse_tallas(tallas_str)

            prod_id = insert_producto(cur, nombre, slug, codigo, precio, retail,
                                      cat_id, marca_ids[marca_slug], segmento,
                                      media_id, tallas, desc)
            conn.commit()

            print(f"  OK  {nombre} | S/{precio} | {tallas_str} | prod={prod_id}")
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
