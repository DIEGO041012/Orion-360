import requests

BASE_URL = "https://fakestoreapi.com/"

def obtener_productos():
    try:
        r = requests.get(f"{BASE_URL}/productos")
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print("Error al obtener productos de tienda externa:", e)
        return []
