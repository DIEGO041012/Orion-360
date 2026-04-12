# tiendas.py
import time
import requests

# APIs de prueba y locales
APIS_TIENDAS = {
    "fakestore": "https://fakestoreapi.com/products",
    "dummyjson": "https://dummyjson.com/products",
    "TheMealDB": "https://www.themealdb.com/api/json/v1/1/filter.php?c=Dessert",
    "tiendablue": "http://localhost:8000/api/productos/"
}

# --- Variables de caché ---
CACHE_PRODUCTOS = {}
CACHE_TIEMPO = 0
CACHE_EXPIRACION = 600  # 10 minutos

# -------------------
# API LOCAL: Tienda Blue
# -------------------
def obtener_productos_tiendablue():
    try:
        r = requests.get(APIS_TIENDAS["tiendablue"], timeout=5)
        r.raise_for_status()
        data = r.json()
        return [
            {
                "nombre": p.get("nombre"),
                "descripcion": p.get("descripcion"),
                "precio": p.get("precio"),
                "imagen": p.get("imagen"),
                "categoria": p.get("categoria", {}).get("nombre", "Sin categoría"),
                "tienda": "Tienda Blue"
            }
            for p in data
        ]
    except Exception as e:
        print("Error en Tienda Blue:", e)
        return []

# -------------------
# API EXTERNA: FakeStore
# -------------------
def obtener_productos_fakestore():
    try:
        r = requests.get(APIS_TIENDAS["fakestore"], timeout=5)
        r.raise_for_status()
        data = r.json()
        return [
            {
                "nombre": p["title"],
                "descripcion": p["description"],
                "precio": p["price"],
                "imagen": p["image"],
                "categoria": p.get("category", "Sin categoría"),
                "tienda": "FakeStore"
            }
            for p in data
        ]
    except Exception as e:
        print("Error en FakeStore:", e)
        return []

# -------------------
# API EXTERNA: DummyJSON
# -------------------
def obtener_productos_dummyjson():
    try:
        r = requests.get(APIS_TIENDAS["dummyjson"], timeout=5)
        r.raise_for_status()
        data = r.json().get("products", [])
        return [
            {
                "nombre": p["title"],
                "descripcion": p["description"],
                "precio": p["price"],
                "imagen": p["thumbnail"],
                "categoria": p.get("category", "Sin categoría"),
                "tienda": "DummyJSON"
            }
            for p in data
        ]
    except Exception as e:
        print("Error en DummyJSON:", e)
        return []

# -------------------
# API EXTERNA: TheMealDB
# -------------------
def obtener_productos_comidas():
    try:
        r = requests.get(APIS_TIENDAS["TheMealDB"], timeout=5)
        r.raise_for_status()
        comidas = r.json().get("meals", [])
        resultado = []
        for comida in comidas[:10]:
            try:
                detalle_url = f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={comida['idMeal']}"
                detalle = requests.get(detalle_url, timeout=5)
                detalle.raise_for_status()
                data = detalle.json().get("meals", [])[0]
                resultado.append({
                    "nombre": data.get("strMeal", "Sin nombre"),
                    "descripcion": data.get("strInstructions", "Sin descripción")[:150] + "...",
                    "precio": 9.99,
                    "imagen": data.get("strMealThumb", ""),
                    "categoria": data.get("strCategory", "Comida"),
                    "tienda": "TheMealDB"
                })
            except Exception as e:
                print(f"Error en detalle comida: {e}")
        return resultado
    except Exception as e:
        print("Error en TheMealDB:", e)
        return []

# -------------------
# API EXTERNA: Plataformas Streaming (TMDb)
# -------------------
TMDB_API_KEY = "8d6bf47cd051a6111e8401dfdb2d1ee3"  # Reemplaza por tu API Key llaamada TMDb
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"

def obtener_plataformas_streaming():
    url = f"{TMDB_BASE_URL}/watch/providers/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "es-ES",
        "watch_region": "CO"
    }
    try:
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json().get("results", [])
        
        return [
            {
                "nombre": p.get("provider_name"),
                "descripcion": "Plataforma de streaming",
                "precio": None,
                "imagen": TMDB_IMAGE_BASE + p.get("logo_path", ""),
                "categoria": "Streaming",
                "tienda": "Plataformas Streaming"
            }
            for p in data if p.get("logo_path")
        ]
    except Exception as e:
        print("Error en Plataformas Streaming:", e)
        return []

# -------------------
# Combinar todo con caché
# -------------------
def obtener_productos_por_tienda():
    global CACHE_PRODUCTOS, CACHE_TIEMPO
    ahora = time.time()

    # Si hay caché válido, usarlo
    if CACHE_PRODUCTOS and (ahora - CACHE_TIEMPO) < CACHE_EXPIRACION:
        print("Usando caché de productos")
        return CACHE_PRODUCTOS

    print("Recargando datos desde las APIs...")
    productos = {
        "Tienda Blue": obtener_productos_tiendablue(),
        "FakeStore": obtener_productos_fakestore(),
        "DummyJSON": obtener_productos_dummyjson(),
        "TheMealDB": obtener_productos_comidas(),
        "Plataformas Streaming": obtener_plataformas_streaming()
    }

    CACHE_PRODUCTOS = productos
    CACHE_TIEMPO = ahora
    return productos
