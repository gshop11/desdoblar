"""Script de diagnóstico: lista modelos Gemini disponibles con tu API key."""
import os
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: Ejecuta: pip install google-genai")
    exit(1)

api_key = os.getenv("GEMINI_API_KEY", "").strip()
if not api_key:
    print("ERROR: GEMINI_API_KEY no encontrada en .env")
    exit(1)

def list_models(label, client):
    print(f"\n=== {label} ===")
    try:
        models = list(client.models.list())
        for m in models:
            name = m.name
            methods = getattr(m, "supported_generation_methods", [])
            if any(k in name.lower() for k in ["flash", "image", "imagen", "pro"]):
                print(f"  {name}")
                if methods:
                    print(f"    Métodos: {methods}")
    except Exception as e:
        print(f"  Error: {e}")

client_beta = genai.Client(api_key=api_key)
client_alpha = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version="v1alpha"))

list_models("v1beta (predeterminado)", client_beta)
list_models("v1alpha", client_alpha)
print("\nDone.")
