"""
Script para subir productos del catálogo JOMA a Plus Sport via Payload CMS API.
"""
import requests
import json
import sys
import io
from pathlib import Path

# Forzar UTF-8 en Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_URL = "https://plus-sport-mkar.vercel.app/api"
JOMA_DIR = Path(__file__).parent / "output-joma"

# ─────────────────────────────────────────────
# Datos extraídos del PDF: imagen → (codigo, precio, retail, tallas, segmento)
# ─────────────────────────────────────────────
PRODUCTOS = {
    "005-img-01.jpg": ("TOUW2528IN",  309, 399, "39 AL 43.5", "unisex"),
    "006-img-01.jpg": ("TOUW250IN",   309, 399, "39 AL 43.5", "unisex"),
    "007-img-01.jpg": ("TORW2529TF",  299, 372, "39 AL 43.5", "unisex"),
    "008-img-01.jpg": ("TORW2503TF",  299, 372, "39 AL 43.5", "unisex"),
    "009-img-01.jpg": ("FS2501IN",    290, 380, "39 AL 43.5", "unisex"),
    "010-img-01.jpg": ("GAMW2523IN",  229, 269, "39 AL 43.5", "unisex"),
    "011-img-01.jpg": ("GAMW2501IN",  229, 249, "39 AL 43.5", "unisex"),
    "012-img-01.jpg": ("TORW2501IN",  299, 372, "39 AL 43.5", "unisex"),
    "013-img-01.jpg": ("TORW2507IN",  299, 372, "39 AL 43.5", "unisex"),
    "014-img-01.jpg": ("TORW2517IN",  299, 372, "39 AL 43.5", "unisex"),
    "015-img-01.jpg": ("TORW2509IN",  299, 372, "39 AL 43.5", "unisex"),
    "016-img-01.jpg": ("TOPW2576IN",  249, 310, "39 AL 43.5", "unisex"),
    "017-img-01.jpg": ("TOPS2121IN",  249, 310, "39 AL 43.5", "unisex"),
    "018-img-01.jpg": ("BSCRES2502IN",219, 249, "38 AL 41",   "unisex"),
    "019-img-01.jpg": ("MUNW2503TF",  199, 249, "39 AL 43.5", "unisex"),
    "020-img-01.jpg": ("MUNW2504TF",  199, 249, "39 AL 43.5", "unisex"),
    "021-img-01.jpg": ("2303TF",      149, 179, "39 AL 43.5", "unisex"),
    "022-img-01.jpg": ("MAXW2409TF",  149, 179, "39 AL 43.5", "unisex"),
    "023-img-01.jpg": ("2501TF",      149, 179, "39 AL 43.5", "unisex"),
    "024-img-01.jpg": ("MAXS2502TF",  149, 179, "39 AL 43.5", "unisex"),
    "026-img-01.jpg": ("MAXS2527TF",  149, 249, "39 AL 43.5", "unisex"),
    "027-img-01.jpg": ("2520IN",      149, 249, "39 AL 43.5", "unisex"),
    "028-img-01.jpg": ("2508TF",      149, 249, "39 AL 43.5", "unisex"),
    "029-img-01.jpg": ("2509TF",      149, 249, "39 AL 43.5", "unisex"),
    "030-img-01.jpg": ("MAX2433",     149, 179, "41",          "unisex"),
    "031-img-01.jpg": ("2304TF",      159, 189, "40 AL 43",   "unisex"),
    "032-img-01.jpg": ("2503TF",      159, 189, "40 AL 43",   "unisex"),
    "033-img-01.jpg": ("2509IN",      159, 249, "39 AL 43.5", "unisex"),
    "034-img-01.jpg": ("2535TF",      169, 249, "39 AL 43.5", "unisex"),
    "035-img-01.jpg": ("CANW2505T",   159, 249, "39 AL 43.5", "unisex"),
    "036-img-01.jpg": ("CANW2502IN",  159, 249, "39 AL 43.5", "unisex"),
    "037-img-01.jpg": ("DRIW2503TF",  159, 178, "39 AL 43.5", "unisex"),
    "038-img-01.jpg": ("DRIW2501TF",  159, 178, "39 AL 43.5", "unisex"),
    "039-img-01.jpg": ("DRIW2527IN",  159, 178, "39 AL 43.5", "unisex"),
    "040-img-01.jpg": ("DRIW2502TF",  159, 178, "39 AL 43.5", "unisex"),
    "041-img-01.jpg": ("DRIW2510IN",  159, 178, "39 AL 43.5", "unisex"),
    "042-img-01.jpg": ("DRI2501TF",   159, 178, "39 AL 43.5", "unisex"),
    "043-img-01.jpg": ("AGUS2507",    139, 169, "40 AL 43",   "unisex"),
    "044-img-01.jpg": ("AGUS2504TF",  139, 169, "39 AL 43.5", "unisex"),
    "045-img-01.jpg": ("2503TF_AGU",  139, 169, "39 AL 43.5", "unisex"),
    "046-img-01.jpg": ("2501TF_AGU",  139, 169, "39 AL 43.5", "unisex"),
    "047-img-01.jpg": ("2321TF",      139, 169, "39 AL 43.5", "unisex"),
    "048-img-01.jpg": ("2502TF_AGU",  139, 169, "39 AL 43.5", "unisex"),
    "049-img-01.jpg": ("AGU2504",     139, 169, "39 AL 43.5", "unisex"),
    # Niños
    "052-img-01.jpg": ("TOJ2502TF",   119, 149, "31 AL 38",   "ninos"),
    "053-img-01.jpg": ("TOJ2501TF",   119, 149, "31 AL 38",   "ninos"),
    "054-img-01.jpg": ("EVJW2501TF",  119, 189, "34 AL 39",   "ninos"),
    "055-img-01.jpg": ("TOJ2505TF",   119, 149, "31 AL 38",   "ninos"),
    "056-img-01.jpg": ("EVJW2503TF",  119, 189, "34 AL 39",   "ninos"),
    "057-img-01.jpg": ("EVJW2503IN",  119, 189, "34 AL 39",   "ninos"),
    "058-img-01.jpg": ("EVJW2532IN",  119, 189, "34 Y 36",    "ninos"),
    "059-img-01.jpg": ("TOJW2503",    119, 149, "31 AL 38",   "ninos"),
}


def parse_tallas(tallas_str: str) -> list[dict]:
    """Convierte '39 AL 43.5' en lista de tallas con stock 0."""
    tallas = []
    tallas_str = tallas_str.strip().upper()

    if "AL" in tallas_str:
        parts = tallas_str.split("AL")
        try:
            inicio = float(parts[0].strip())
            fin = float(parts[1].strip())
            t = inicio
            while t <= fin + 0.01:
                tallas.append({"talla": str(int(t) if t == int(t) else t), "stock": 0})
                t += 0.5
        except Exception:
            tallas.append({"talla": tallas_str, "stock": 0})
    elif "Y" in tallas_str:
        for t in tallas_str.split("Y"):
            t = t.strip()
            if t:
                tallas.append({"talla": t, "stock": 0})
    else:
        tallas.append({"talla": tallas_str, "stock": 0})

    return tallas


def make_richtext(text: str) -> dict:
    return {
        "root": {
            "type": "root",
            "children": [
                {
                    "type": "paragraph",
                    "version": 1,
                    "children": [{"type": "text", "text": text, "version": 1}],
                    "direction": "ltr",
                    "format": "",
                    "indent": 0,
                }
            ],
            "direction": "ltr",
            "format": "",
            "indent": 0,
            "version": 1,
        }
    }


def login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/usuarios/login", json={"email": email, "password": password})
    if r.status_code == 200:
        token = r.json().get("token")
        print(f"✓ Login exitoso como {email}")
        return token
    print(f"✗ Login falló: {r.status_code} {r.text[:200]}")
    return None


def first_register(email: str, password: str, nombre: str) -> str:
    r = requests.post(
        f"{BASE_URL}/usuarios/first-register",
        json={"email": email, "password": password, "nombre": nombre, "rol": "admin"},
    )
    if r.status_code in (200, 201):
        token = r.json().get("token")
        print(f"✓ Usuario admin creado: {email}")
        return token
    print(f"  first-register: {r.status_code} {r.text[:200]}")
    return None


def create_marca(token: str, nombre: str, slug: str) -> str | None:
    r = requests.post(
        f"{BASE_URL}/marcas",
        headers={"Authorization": f"JWT {token}"},
        json={"nombre": nombre, "slug": slug, "activa": True},
    )
    if r.status_code in (200, 201):
        id_ = r.json()["doc"]["id"]
        print(f"✓ Marca creada: {nombre} (id={id_})")
        return id_
    # Puede que ya exista
    r2 = requests.get(f"{BASE_URL}/marcas?where[slug][equals]={slug}", headers={"Authorization": f"JWT {token}"})
    docs = r2.json().get("docs", [])
    if docs:
        print(f"  Marca ya existe: {nombre} (id={docs[0]['id']})")
        return docs[0]["id"]
    print(f"✗ Error creando marca: {r.text[:200]}")
    return None


def create_categoria(token: str, nombre: str, slug: str, orden: int = 0) -> str | None:
    r = requests.post(
        f"{BASE_URL}/categorias",
        headers={"Authorization": f"JWT {token}"},
        json={"nombre": nombre, "slug": slug, "activa": True, "orden": orden},
    )
    if r.status_code in (200, 201):
        id_ = r.json()["doc"]["id"]
        print(f"✓ Categoría creada: {nombre} (id={id_})")
        return id_
    r2 = requests.get(f"{BASE_URL}/categorias?where[slug][equals]={slug}", headers={"Authorization": f"JWT {token}"})
    docs = r2.json().get("docs", [])
    if docs:
        print(f"  Categoría ya existe: {nombre} (id={docs[0]['id']})")
        return docs[0]["id"]
    print(f"✗ Error creando categoría: {r.text[:200]}")
    return None


def upload_image(token: str, image_path: Path) -> str | None:
    with open(image_path, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/media",
            headers={"Authorization": f"JWT {token}"},
            files={"file": (image_path.name, f, "image/jpeg")},
            data={"alt": image_path.stem},
        )
    if r.status_code in (200, 201):
        id_ = r.json()["doc"]["id"]
        return id_
    print(f"  ✗ Error subiendo {image_path.name}: {r.status_code} {r.text[:150]}")
    return None


def create_producto(token: str, data: dict) -> bool:
    r = requests.post(
        f"{BASE_URL}/productos",
        headers={"Authorization": f"JWT {token}", "Content-Type": "application/json"},
        json=data,
    )
    if r.status_code in (200, 201):
        return True
    print(f"  ✗ Error creando producto {data.get('sku')}: {r.status_code} {r.text[:200]}")
    return False


def main():
    # ── 1. Autenticación ──────────────────────────────────────────────────────
    ADMIN_EMAIL = "gshop.trujillo@gmail.com"
    ADMIN_PASS  = "C@mbio2024."
    ADMIN_NAME  = "Admin Plus Sport"

    print("\n=== AUTENTICACIÓN ===")
    token = login(ADMIN_EMAIL, ADMIN_PASS)
    if not token:
        print("Intentando crear primer usuario admin...")
        token = first_register(ADMIN_EMAIL, ADMIN_PASS, ADMIN_NAME)
    if not token:
        print("ERROR: No se pudo autenticar. Verifica que el sitio esté activo.")
        sys.exit(1)

    # ── 2. Crear marca y categorías ───────────────────────────────────────────
    print("\n=== MARCA Y CATEGORÍAS ===")
    joma_id  = create_marca(token, "JOMA", "joma")
    cat_adulto_id = create_categoria(token, "Zapatillas Adulto", "zapatillas-adulto", 1)
    cat_ninos_id  = create_categoria(token, "Zapatillas Niños",  "zapatillas-ninos",  2)

    if not joma_id or not cat_adulto_id or not cat_ninos_id:
        print("ERROR: No se pudieron crear marca/categorías.")
        sys.exit(1)

    # ── 3. Subir imágenes y crear productos ───────────────────────────────────
    print(f"\n=== SUBIENDO {len(PRODUCTOS)} PRODUCTOS ===")
    ok = 0
    fail = 0

    for filename, (codigo, precio, retail, tallas_str, segmento) in PRODUCTOS.items():
        img_path = JOMA_DIR / filename
        if not img_path.exists():
            print(f"  ⚠ Imagen no encontrada: {filename}")
            fail += 1
            continue

        # Subir imagen
        media_id = upload_image(token, img_path)
        if not media_id:
            fail += 1
            continue

        # Determinar categoría y nombre
        cat_id = cat_ninos_id if segmento == "ninos" else cat_adulto_id
        nombre = f"Joma {codigo}"
        slug   = f"joma-{codigo.lower().replace('_', '-')}"

        # Crear producto
        data = {
            "nombre":         nombre,
            "slug":           slug,
            "sku":            codigo,
            "precio":         precio,
            "precioAnterior": retail,
            "marca":          joma_id,
            "categoria":      cat_id,
            "segmento":       segmento,
            "imagenPrincipal": media_id,
            "tallas":         parse_tallas(tallas_str),
            "etiqueta":       "nuevo",
            "nuevoIngreso":   True,
            "activo":         True,
            "descripcion":    make_richtext(
                f"Zapatilla JOMA modelo {codigo}. Tallas disponibles: {tallas_str}."
            ),
        }

        if create_producto(token, data):
            print(f"  ✓ {nombre} | S/{precio} | {tallas_str}")
            ok += 1
        else:
            fail += 1

    print(f"\n=== RESULTADO: {ok} productos subidos, {fail} errores ===")


if __name__ == "__main__":
    main()
