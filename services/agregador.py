from .tienda_local import obtener_productos as local
from .tienda_externa1 import obtener_productos as externa1

def obtener_todos_los_productos():
    productos = []
    productos.extend(local())
    productos.extend(externa1())
    # Normalización si es necesario
    return productos
