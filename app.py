from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, current_app, jsonify
from flask_dance.contrib.google import make_google_blueprint, google
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
from flask_login import LoginManager, login_user, UserMixin, login_required, current_user, logout_user
from flask_wtf import CSRFProtect
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from io import BytesIO
from flaskform.forms import MovimientoForm, PrestamoForm, DeudaForm, ListaForm, LoginForm, DummyForm, RegistroForm, RegistroUnicoForm, CategoriaForm
from services import tiendas
from services.tiendas import obtener_productos_por_tienda
from xhtml2pdf import pisa
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from groq import Groq
from google import genai
from google.genai import types
from PIL import Image
import base64
import mimetypes
import cloudinary
import cloudinary.uploader
from config import Config
import asyncio
import os
import sys
import requests
from datetime import datetime, timezone
import pytz

load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'flaskform')))
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
sqlite3.register_adapter(Decimal, float)
print("KEY CARGADA:", os.getenv("GEMINI_API_KEY"))

# ══════════════════════════════════════════════════════════
# INICIALIZACIÓN DE LA APLICACIÓN
# ══════════════════════════════════════════════════════════

app = Flask(__name__)
app.config.from_object(Config)

# 🔥 GOOGLE LOGIN
google_bp = make_google_blueprint(
    client_id=app.config.get("GOOGLE_CLIENT_ID"),
    client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ],
    redirect_url="/login/google"
)

app.register_blueprint(google_bp, url_prefix="/login")

# 👇 LO TUYO SIGUE NORMAL
print("DATABASE_URL:", app.config.get("DATABASE_URL"))
print("CLOUDINARY_CLOUD_NAME:", app.config.get("CLOUDINARY_CLOUD_NAME"))
print("CLOUDINARY_API_KEY:", app.config.get("CLOUDINARY_API_KEY"))
print("CLOUDINARY_API_SECRET:", "OK" if app.config.get("CLOUDINARY_API_SECRET") else None)
print("API KEY CLIMA:", app.config.get("OPENWEATHER_API_KEY"))
print("GOOGLE_CLIENT_ID:", app.config.get("GOOGLE_CLIENT_ID"))
print("GOOGLE_CLIENT_SECRET:", "OK" if app.config.get("GOOGLE_CLIENT_SECRET") else None)

cloudinary.config(
    cloud_name=app.config.get("CLOUDINARY_CLOUD_NAME"),
    api_key=app.config.get("CLOUDINARY_API_KEY"),
    api_secret=app.config.get("CLOUDINARY_API_SECRET"),
    secure=True
)

CORS(app)
csrf = CSRFProtect(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

login_manager = LoginManager(app)
login_manager.login_view = 'iniciar_sesion'

# ══════════════════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════════════════

class DatabaseCursor:
    def __init__(self, cursor, use_postgres=False):
        self._cursor = cursor
        self._use_postgres = use_postgres

    def execute(self, query, params=None):
        if params is None:
            params = ()
        if self._use_postgres:
            query = query.replace('?', '%s')
        return self._cursor.execute(query, params)

    def executemany(self, query, seq_of_params):
        if self._use_postgres:
            query = query.replace('?', '%s')
        return self._cursor.executemany(query, seq_of_params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class DatabaseConnection:
    def __init__(self, conn, use_postgres=False):
        self._conn = conn
        self.is_postgres = use_postgres

    def cursor(self, *args, **kwargs):
        raw_cursor = self._conn.cursor(*args, **kwargs)
        return DatabaseCursor(raw_cursor, self.is_postgres)

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()

    def rollback(self):
        return self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
        finally:
            self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)
    
def construir_contexto_orion(usuario_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Disponible real
        cursor.execute("""
            SELECT COALESCE(SUM(
                CASE
                    WHEN tipo IN ('ingreso', 'abono_a_recibir') THEN valor
                    WHEN tipo IN ('gasto', 'abono_deuda', 'prestamo_entregado') THEN -valor
                    ELSE 0
                END
            ), 0) AS saldo
            FROM movimientos
            WHERE usuario_id = ?
        """, (usuario_id,))
        saldo = cursor.fetchone()['saldo']

        # Ingresos del mes
        if conn.is_postgres:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS total
                FROM movimientos
                WHERE usuario_id = ?
                  AND tipo = 'ingreso'
                  AND DATE_TRUNC('month', fecha) = DATE_TRUNC('month', CURRENT_DATE)
            """, (usuario_id,))
        else:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS total
                FROM movimientos
                WHERE usuario_id = ?
                  AND tipo = 'ingreso'
                  AND strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now')
            """, (usuario_id,))
        ingresos_mes = cursor.fetchone()['total']

        # Gastos / salidas del mes
        if conn.is_postgres:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS total
                FROM movimientos
                WHERE usuario_id = ?
                  AND tipo IN ('gasto', 'abono_deuda', 'prestamo_entregado')
                  AND DATE_TRUNC('month', fecha) = DATE_TRUNC('month', CURRENT_DATE)
            """, (usuario_id,))
        else:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS total
                FROM movimientos
                WHERE usuario_id = ?
                  AND tipo IN ('gasto', 'abono_deuda', 'prestamo_entregado')
                  AND strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now')
            """, (usuario_id,))
        gastos_mes = cursor.fetchone()['total']

        # Últimos movimientos
        cursor.execute("""
            SELECT fecha, descripcion, valor, tipo
            FROM movimientos
            WHERE usuario_id = ?
            ORDER BY fecha DESC, id DESC
            LIMIT 8
        """, (usuario_id,))
        movimientos = cursor.fetchall()

        # Deudas pendientes
        cursor.execute("""
            SELECT persona, descripcion, saldo, estado, fecha
            FROM deudas
            WHERE usuario_id = ?
              AND saldo > 0
            ORDER BY fecha ASC
            LIMIT 8
        """, (usuario_id,))
        deudas = cursor.fetchall()

        # Préstamos pendientes
        cursor.execute("""
            SELECT persona, descripcion, saldo, estado, fecha
            FROM prestamos
            WHERE usuario_id = ?
              AND saldo > 0
            ORDER BY fecha ASC
            LIMIT 8
        """, (usuario_id,))
        prestamos = cursor.fetchall()

        # Agenda próxima
        cursor.execute("""
            SELECT titulo, descripcion, fecha, hora
            FROM agenda
            WHERE usuario_id = ?
              AND fecha >= CURRENT_DATE
            ORDER BY fecha ASC, hora ASC
            LIMIT 8
        """, (usuario_id,))
        agenda = cursor.fetchall()

        texto_movimientos = "\n".join([
            f"- {m['fecha']} | {m['tipo']} | {m['descripcion']} | ${m['valor']}"
            for m in movimientos
        ]) or "Sin movimientos recientes."

        texto_deudas = "\n".join([
            f"- {d['persona'] or 'No especificado'} | {d['descripcion']} | saldo pendiente ${d['saldo']} | estado {d['estado']}"
            for d in deudas
        ]) or "Sin deudas pendientes."

        texto_prestamos = "\n".join([
            f"- {p['persona'] or 'No especificado'} | {p['descripcion']} | saldo por cobrar ${p['saldo']} | estado {p['estado']}"
            for p in prestamos
        ]) or "Sin préstamos pendientes."

        texto_agenda = "\n".join([
            f"- {a['fecha']} {a['hora'] or ''} | {a['titulo']} | {a['descripcion'] or 'Sin descripción'}"
            for a in agenda
        ]) or "Sin citas próximas."

        return f"""
DATOS REALES DEL USUARIO ACTUAL:

FINANZAS:
- Disponible actual: ${saldo}
- Ingresos del mes: ${ingresos_mes}
- Salidas del mes: ${gastos_mes}

ÚLTIMOS MOVIMIENTOS:
{texto_movimientos}

DEUDAS PENDIENTES:
{texto_deudas}

PRÉSTAMOS POR COBRAR:
{texto_prestamos}

AGENDA PRÓXIMA:
{texto_agenda}
"""

    finally:
        cursor.close()
        conn.close()    


def get_db_connection():
    database_url = app.config.get('DATABASE_URL')
    if database_url:
        conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.DictCursor)
        return DatabaseConnection(conn, use_postgres=True)

    db_path = os.path.join(app.root_path, 'orion.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return DatabaseConnection(conn)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    if conn.is_postgres:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                nombre_usuario TEXT NOT NULL UNIQUE,
                correo_electronico TEXT UNIQUE,
                contraseña TEXT,
                foto TEXT,
                saldo_wallet REAL DEFAULT 0,
                nit TEXT,
                direccion TEXT,
                telefono TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tarjetas_vinculadas (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                marca TEXT,
                ultimos_4 TEXT,
                fecha_exp TEXT,
                activa BOOLEAN DEFAULT TRUE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS listas (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                usuario_id INTEGER NOT NULL,
                color TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS tareas (
                id SERIAL PRIMARY KEY,
                titulo TEXT NOT NULL,
                lista_id INTEGER,
                usuario_id INTEGER NOT NULL,
                fecha_limite DATE,
                estado TEXT DEFAULT 'pendiente',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lista_id) REFERENCES listas(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS categorias (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                usuario_id INTEGER NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS movimientos (
                id SERIAL PRIMARY KEY,
                fecha DATE NOT NULL,
                descripcion TEXT,
                valor REAL NOT NULL,
                tipo TEXT,
                usuario_id INTEGER NOT NULL,
                categoria_id INTEGER,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (categoria_id) REFERENCES categorias(id)
            );

            CREATE TABLE IF NOT EXISTS deudas (
                id SERIAL PRIMARY KEY,
                descripcion TEXT,
                persona TEXT,
                usuario_id INTEGER NOT NULL,
                monto_inicial REAL,
                saldo REAL,
                frecuencia TEXT,
                estado TEXT,
                fecha DATE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tipo TEXT,
                movimiento_id INTEGER,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (movimiento_id) REFERENCES movimientos(id)
            );

            CREATE TABLE IF NOT EXISTS prestamos (
                id SERIAL PRIMARY KEY,
                descripcion TEXT,
                persona TEXT,
                usuario_id INTEGER NOT NULL,
                monto_inicial REAL,
                saldo REAL,
                frecuencia TEXT,
                estado TEXT,
                fecha DATE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                movimiento_id INTEGER,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (movimiento_id) REFERENCES movimientos(id)
            );

            CREATE TABLE IF NOT EXISTS recargas (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                metodo TEXT,
                transaccion_id TEXT UNIQUE,
                monto REAL,
                estado TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS wallet_movimientos (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                referencia_externa TEXT,
                monto REAL,
                tipo TEXT,
                estado TEXT,
                descripcion TEXT,
                medio_pago TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS ideas (
                id SERIAL PRIMARY KEY,
                titulo TEXT,
                descripcion TEXT,
                categoria TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agenda (
                id SERIAL PRIMARY KEY,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                fecha DATE NOT NULL,
                hora TEXT,
                usuario_id INTEGER NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS carrito_items (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                precio REAL NOT NULL,
                imagen TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS ahorros (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER,
                nombre TEXT,
                objetivo REAL,
                ahorrado REAL DEFAULT 0,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS negocios (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER,
                nombre TEXT,
                ingresos REAL DEFAULT 0,
                gastos REAL DEFAULT 0,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );
        """)

        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'tareas'"
        )
        columnas_tareas = [row['column_name'] for row in cursor.fetchall()]
        if 'estado' not in columnas_tareas:
            cursor.execute("ALTER TABLE tareas ADD COLUMN estado TEXT DEFAULT 'pendiente'")

    else:
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_usuario TEXT NOT NULL UNIQUE,
                correo_electronico TEXT UNIQUE,
                contraseña TEXT,
                foto TEXT,
                saldo_wallet REAL DEFAULT 0,
                nit TEXT,
                direccion TEXT,
                telefono TEXT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tarjetas_vinculadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                marca TEXT,
                ultimos_4 TEXT,
                fecha_exp TEXT,
                activa BOOLEAN DEFAULT TRUE,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS listas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario_id INTEGER NOT NULL,
                color TEXT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS tareas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                lista_id INTEGER,
                usuario_id INTEGER NOT NULL,
                fecha_limite DATE,
                estado TEXT DEFAULT 'pendiente',
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lista_id) REFERENCES listas(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario_id INTEGER NOT NULL,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATE NOT NULL,
                descripcion TEXT,
                valor REAL NOT NULL,
                tipo TEXT,
                usuario_id INTEGER NOT NULL,
                categoria_id INTEGER,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (categoria_id) REFERENCES categorias(id)
            );

            CREATE TABLE IF NOT EXISTS deudas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descripcion TEXT,
                persona TEXT,
                usuario_id INTEGER NOT NULL,
                monto_inicial REAL,
                saldo REAL,
                frecuencia TEXT,
                estado TEXT,
                fecha DATE,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                tipo TEXT,
                movimiento_id INTEGER,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (movimiento_id) REFERENCES movimientos(id)
            );

            CREATE TABLE IF NOT EXISTS prestamos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descripcion TEXT,
                persona TEXT,
                usuario_id INTEGER NOT NULL,
                monto_inicial REAL,
                saldo REAL,
                frecuencia TEXT,
                estado TEXT,
                fecha DATE,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                movimiento_id INTEGER,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (movimiento_id) REFERENCES movimientos(id)
            );

            CREATE TABLE IF NOT EXISTS recargas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                metodo TEXT,
                transaccion_id TEXT UNIQUE,
                monto REAL,
                estado TEXT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS wallet_movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                referencia_externa TEXT,
                monto REAL,
                tipo TEXT,
                estado TEXT,
                descripcion TEXT,
                medio_pago TEXT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT,
                descripcion TEXT,
                categoria TEXT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agenda (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                fecha DATE NOT NULL,
                hora TEXT,
                usuario_id INTEGER NOT NULL,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS carrito_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                precio REAL NOT NULL,
                imagen TEXT,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            );

            CREATE TABLE IF NOT EXISTS ahorros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                nombre TEXT,
                objetivo REAL,
                ahorrado REAL DEFAULT 0,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS negocios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                nombre TEXT,
                ingresos REAL DEFAULT 0,
                gastos REAL DEFAULT 0,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute('PRAGMA table_info(tareas)')
        columnas_tareas = [row[1] for row in cursor.fetchall()]
        if 'estado' not in columnas_tareas:
            cursor.execute("ALTER TABLE tareas ADD COLUMN estado TEXT DEFAULT 'pendiente'")

    conn.commit()
    cursor.close()
    conn.close()


# ══════════════════════════════════════════════════════════
# CONFIGURACIÓN GROQ
# ══════════════════════════════════════════════════════════

def inicializar_groq():
    api_key = app.config.get('GROQ_API_KEY')

    if not api_key:
        print('[WARNING] GROQ_API_KEY no configurada; la funcion de asistente no funcionara.')
        return None

    try:
        cliente = Groq(api_key=api_key)
        print('[OK] Groq API inicializada correctamente.')
        return cliente
    except Exception as e:
        print('[WARNING] No se pudo inicializar Groq:', str(e)[:180])
        return None


groq_client = inicializar_groq()


def generar_respuesta_groq(prompt, imagen_binaria=None, mime_type=None):
    if groq_client is None:
        raise RuntimeError('GROQ_API_KEY no está configurada o Groq no se inició.')

    # Modelo rápido para texto
    modelo_texto = 'llama-3.3-70b-versatile'

    # Modelo multimodal para imágenes/facturas
    modelo_vision = 'meta-llama/llama-4-maverick-17b-128e-instruct'

    if imagen_binaria and mime_type:
        imagen_base64 = base64.b64encode(imagen_binaria).decode('utf-8')

        messages = [
            {
                'role': 'system',
                'content': 'Responde siempre en español. Si se solicita JSON, responde únicamente JSON válido.'
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': prompt
                    },
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:{mime_type};base64,{imagen_base64}'
                        }
                    }
                ]
            }
        ]

        respuesta = groq_client.chat.completions.create(
            model=modelo_vision,
            messages=messages,
            temperature=0.1,
            max_completion_tokens=1024
        )

    else:
        messages = [
            {
                'role': 'system',
                'content': 'Responde siempre en español, claro y útil.'
            },
            {
                'role': 'user',
                'content': prompt
            }
        ]

        respuesta = groq_client.chat.completions.create(
            model=modelo_texto,
            messages=messages,
            temperature=0.4,
            max_completion_tokens=1200
        )

    return respuesta.choices[0].message.content

# ══════════════════════════════════════════════════════════
# CONFIGURACIÓN ARCHIVOS & FILTROS JINJA
# ══════════════════════════════════════════════════════════

CARPETA_FOTOS = 'static/uploads'
if not os.path.exists(CARPETA_FOTOS):
    os.makedirs(CARPETA_FOTOS)
app.config['CARPETA_FOTOS'] = CARPETA_FOTOS
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def archivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def escapejs_filter(value):
    if not isinstance(value, str):
        value = str(value)
    replacements = {
        '\\': '\\\\', '"': '\\"', "'": "\\'",
        '\n': '\\n', '\r': '\\r', '</': '<\\/'
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


app.jinja_env.filters['escapejs'] = escapejs_filter


# ══════════════════════════════════════════════════════════
# CONTEXT PROCESSOR — optimizado: sin consulta SQL por request
# ══════════════════════════════════════════════════════════



@app.context_processor
def inject_user_data():
    zona = pytz.timezone('America/Bogota')  # 🇨🇴 hora Colombia

    if not current_user.is_authenticated:
        return {
            'now': datetime.now(zona)  # 👈 agregar esto
        }

    foto = getattr(current_user, 'foto', None)

    if not foto:
        foto = "https://res.cloudinary.com/di9wdbb1z/image/upload/v1750640818/default_xm9gvv.jpg"
    elif not (foto.startswith('http://') or foto.startswith('https://')):
        if foto.startswith('static/'):
            foto = url_for('static', filename=foto.replace('static/', '', 1))
        else:
            foto = url_for('static', filename=f'uploads/{foto}')

    return {
        'usuario': current_user.nombre_usuario,
        'usuario_foto': foto,
        'now': datetime.now(zona)  # 👈 ESTA LÍNEA ES LA CLAVE
    }

# ══════════════════════════════════════════════════════════
# HELPERS DE FECHA
# ══════════════════════════════════════════════════════════

def to_date(val):
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return datetime.strptime(val[:10], '%Y-%m-%d').date()
        except Exception:
            return None
    return None


def to_decimal(valor):
    if valor is None:
        return Decimal('0')
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def formatear_fecha_humana(fecha):
    hoy = date.today()
    if isinstance(fecha, str):
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    elif isinstance(fecha, datetime):
        fecha_obj = fecha.date()
    elif isinstance(fecha, date):
        fecha_obj = fecha
    else:
        raise ValueError("Tipo de fecha no soportado")

    if fecha_obj == hoy:
        return "Hoy"
    elif fecha_obj == hoy - timedelta(days=1):
        return "Ayer"
    elif 0 < (hoy - fecha_obj).days < 7:
        return fecha_obj.strftime("%A").capitalize()
    else:
        return fecha_obj.strftime("%d/%m/%Y")


# ══════════════════════════════════════════════════════════
# WIDGET CLIMA
# ══════════════════════════════════════════════════════════

def mapear_icono_clima(icono_api):
    es_noche = icono_api.endswith('n')
    codigo = icono_api[:2]
    mapa = {
        '01': 'fa-moon'            if es_noche else 'fa-sun',
        '02': 'fa-cloud-moon'      if es_noche else 'fa-cloud-sun',
        '03': 'fa-cloud',
        '04': 'fa-cloud',
        '09': 'fa-cloud-showers-heavy',
        '10': 'fa-cloud-moon-rain' if es_noche else 'fa-cloud-rain',
        '11': 'fa-cloud-bolt',
        '13': 'fa-snowflake',
        '50': 'fa-smog',
    }
    return mapa.get(codigo, 'fa-cloud-sun')


def obtener_clima_actual(ciudad='Medellin,CO'):
    api_key = app.config.get('OPENWEATHER_API_KEY')
    if not api_key:
        return {
            'ciudad': 'Medellín', 'temperatura': 24, 'estado': 'Sin API configurada',
            'max': 27, 'min': 18, 'humedad': 72, 'lluvia': 0,
            'icono': 'fa-cloud-sun', 'es_noche': False,
        }
    url = 'https://api.openweathermap.org/data/2.5/weather'
    params = {'q': ciudad, 'appid': api_key, 'units': 'metric', 'lang': 'es'}
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        lluvia = 0
        if 'rain' in data:
            lluvia = data['rain'].get('1h', data['rain'].get('3h', 0))
        icono_api = data['weather'][0].get('icon', '02d')
        es_noche = icono_api.endswith('n')
        return {
            'ciudad':      data.get('name', 'Medellín'),
            'temperatura': round(data['main']['temp']),
            'estado':      data['weather'][0]['description'].capitalize(),
            'max':         round(data['main']['temp_max']),
            'min':         round(data['main']['temp_min']),
            'humedad':     data['main']['humidity'],
            'lluvia':      lluvia,
            'icono':       mapear_icono_clima(icono_api),
            'es_noche':    es_noche,
        }
    except Exception as e:
        print('Error al obtener clima real:', e)
        return {
            'ciudad': 'Medellín', 'temperatura': 24, 'estado': 'No disponible',
            'max': 27, 'min': 18, 'humedad': 72, 'lluvia': 0,
            'icono': 'fa-cloud-sun', 'es_noche': False,
        }


def obtener_pronostico(ciudad='Medellin,CO'):
    api_key = app.config.get('OPENWEATHER_API_KEY')
    if not api_key:
        return []
    url = 'https://api.openweathermap.org/data/2.5/forecast'
    params = {'q': ciudad, 'appid': api_key, 'units': 'metric', 'lang': 'es'}
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        pronostico_por_dia = {}
        for item in data.get('list', []):
            fecha_hora = item.get('dt_txt', '')
            if not fecha_hora:
                continue
            fecha, hora = fecha_hora.split(' ')
            if hora == '12:00:00':
                pronostico_por_dia[fecha] = {
                    'fecha':    fecha,
                    'temp':     round(item['main']['temp']),
                    'temp_min': round(item['main']['temp_min']),
                    'temp_max': round(item['main']['temp_max']),
                    'estado':   item['weather'][0]['description'].capitalize(),
                    'icono':    mapear_icono_clima(item['weather'][0].get('icon', '02d'))
                }
        if len(pronostico_por_dia) < 4:
            for item in data.get('list', []):
                fecha_hora = item.get('dt_txt', '')
                if not fecha_hora:
                    continue
                fecha = fecha_hora.split(' ')[0]
                if fecha not in pronostico_por_dia:
                    pronostico_por_dia[fecha] = {
                        'fecha':    fecha,
                        'temp':     round(item['main']['temp']),
                        'temp_min': round(item['main']['temp_min']),
                        'temp_max': round(item['main']['temp_max']),
                        'estado':   item['weather'][0]['description'].capitalize(),
                        'icono':    mapear_icono_clima(item['weather'][0].get('icon', '02d'))
                    }
                if len(pronostico_por_dia) >= 4:
                    break
        return list(pronostico_por_dia.values())[:4]
    except Exception as e:
        print('Error al obtener pronóstico:', e)
        return []


# ══════════════════════════════════════════════════════════
# MODELO DE USUARIO — incluye foto para evitar SQL en context_processor
# ══════════════════════════════════════════════════════════

class Usuario(UserMixin):
    def __init__(self, id, nombre_usuario, foto=None):
        self.id = id
        self.nombre_usuario = nombre_usuario
        self.foto = foto


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nombre_usuario, foto FROM usuarios WHERE id = ?', (user_id,))
    cuenta = cursor.fetchone()
    cursor.close()
    conn.close()
    if cuenta:
        return Usuario(cuenta['id'], cuenta['nombre_usuario'], cuenta['foto'])
    return None


# ══════════════════════════════════════════════════════════
# RUTAS PRINCIPALES / AUTENTICACIÓN
# ══════════════════════════════════════════════════════════

@app.route('/')
def inicio():
    return render_template('inicio.html')


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    flash("La imagen excede el tamaño máximo permitido (5 MB).", "danger")
    return redirect(request.referrer or url_for('registro'))


@app.route('/registro', methods=['GET'])
def registro():
    form = RegistroForm()
    return render_template('registrarse.html', form=form)


@app.route('/guardar_registro', methods=['POST'])
def guardar_registro():
    form = RegistroForm()
    if not form.validate_on_submit():
        flash('Error en el formulario. Revisa los campos.', 'danger')
        return redirect(url_for('registro'))

    usuario = form.usuario.data.strip()
    correo  = form.correo.data.strip().lower()
    clave   = generate_password_hash(form.clave.data)
    foto    = form.foto.data
    url_foto = "https://res.cloudinary.com/di9wdbb1z/image/upload/v1750640818/default_xm9gvv.jpg"

    if foto and foto.filename != "":
        try:
            resultado = cloudinary.uploader.upload(foto)
            url_foto  = resultado.get("secure_url") or url_foto
        except Exception as e:
            flash("Error al subir imagen. Se usará la imagen por defecto.", "warning")
            print("Error Cloudinary:", e)

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT id FROM usuarios WHERE nombre_usuario = ? OR correo_electronico = ?',
            (usuario, correo)
        )
        if cursor.fetchone():
            flash('El nombre de usuario o correo ya está en uso.', 'danger')
            return redirect(url_for('registro'))

        cursor.execute(
            'INSERT INTO usuarios (nombre_usuario, correo_electronico, contraseña, foto) VALUES (?, ?, ?, ?)',
            (usuario, correo, clave, url_foto)
        )
        conn.commit()
        flash('Registro exitoso.', 'success')
        return redirect(url_for('iniciar_sesion'))
    except Exception as e:
        conn.rollback()
        print("Error al guardar registro:", e)
        flash('Ocurrió un error al registrar el usuario.', 'danger')
        return redirect(url_for('registro'))
    finally:
        cursor.close()
        conn.close()


@app.route('/iniciar_sesion', methods=['GET', 'POST'])
def iniciar_sesion():
    form = LoginForm()
    if form.validate_on_submit():
        usuario = form.usuario.data
        clave   = form.clave.data

        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM usuarios WHERE nombre_usuario = ?', (usuario,))
        cuenta = cursor.fetchone()
        cursor.close()
        conn.close()

        if cuenta and check_password_hash(cuenta['contraseña'], clave):
            user = Usuario(cuenta['id'], cuenta['nombre_usuario'], cuenta['foto'])
            login_user(user)
            migrar_carrito_sesion_a_db(user.id)
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('panel_usuario'))

        flash('Nombre de usuario o contraseña incorrectos.', 'danger')

    return render_template('iniciar_sesion.html', form=form)


@app.route('/cerrar_sesion', methods=['POST'])
@login_required
def cerrar_sesion():
    logout_user()
    return redirect(url_for('iniciar_sesion'))


# ── Recuperación de contraseña ────────────────────────────

@app.route('/recuperar_contrasena', methods=['GET', 'POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        correo = (request.form.get('correo') or '').strip().lower()

        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM usuarios WHERE correo_electronico = ?', (correo,))
        usuario = cursor.fetchone()
        cursor.close()
        conn.close()

        if usuario:
            token  = serializer.dumps(correo, salt='recuperar-contrasena')
            enlace = url_for('resetear_contrasena', token=token, _external=True)
            msg = Message(
                subject='Recuperación de contraseña — Oryon 360',
                recipients=[correo]
            )
            msg.html = f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px;
                        background:#111;color:#ccc;border-radius:12px;">
                <h2 style="color:#fff;margin-bottom:8px;">Recuperar contraseña</h2>
                <p>Recibimos una solicitud para restablecer tu contraseña.</p>
                <a href="{enlace}"
                   style="display:inline-block;margin:20px 0;padding:12px 24px;
                          background:#fff;color:#000;border-radius:6px;font-weight:700;
                          text-decoration:none;">
                    Restablecer contraseña
                </a>
                <p style="font-size:13px;color:#888;">
                    Este enlace expira en <strong style="color:#ccc;">30 minutos</strong>.
                    Si no solicitaste esto, ignora este correo.
                </p>
            </div>
            """
            try:
                mail.send(msg)
            except Exception as e:
                print('Error al enviar correo:', e)

        flash('Si ese correo está registrado, recibirás un enlace en breve.', 'info')
        return redirect(url_for('recuperar_contrasena'))

    return render_template('recuperar_contrasena.html')


@app.route('/resetear_contrasena/<token>', methods=['GET', 'POST'])
def resetear_contrasena(token):
    try:
        correo = serializer.loads(token, salt='recuperar-contrasena', max_age=1800)
    except Exception:
        flash('El enlace es inválido o ha expirado.', 'danger')
        return redirect(url_for('recuperar_contrasena'))

    if request.method == 'POST':
        nueva    = (request.form.get('nueva_clave') or '').strip()
        confirmar = (request.form.get('confirmar_clave') or '').strip()

        if len(nueva) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
            return redirect(request.url)
        if nueva != confirmar:
            flash('Las contraseñas no coinciden.', 'danger')
            return redirect(request.url)

        clave_hash = generate_password_hash(nueva)
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE usuarios SET contraseña = ? WHERE correo_electronico = ?',
            (clave_hash, correo)
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash('Contraseña actualizada correctamente. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('iniciar_sesion'))

    return render_template('resetear_contrasena.html', token=token)


# ── Google OAuth ──────────────────────────────────────────

@app.route('/login/google')
def login_google():
    if not google.authorized:
        return redirect(url_for("google.login"))
    return redirect(url_for("panel_usuario"))


@app.route("/google/callback")
def google_callback():
    if not google.authorized:
        flash("No se pudo autenticar con Google.")
        return redirect(url_for("iniciar_sesion"))

    resp = google.get("/oauth2/v1/userinfo")
    if not resp.ok:
        flash("No se pudo obtener datos del usuario.")
        return redirect(url_for("iniciar_sesion"))

    user_info = resp.json()
    email  = user_info.get("email")
    nombre = user_info.get("name")
    foto   = user_info.get("picture")

    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE correo_electronico = ?", (email,))
    cuenta = cursor.fetchone()

    if not cuenta:
        cursor.execute(
            'INSERT INTO usuarios (nombre_usuario, correo_electronico, contraseña, foto) VALUES (?, ?, ?, ?)',
            (nombre, email, '', foto)
        )
        conn.commit()
        cursor.execute("SELECT * FROM usuarios WHERE correo_electronico = ?", (email,))
        cuenta = cursor.fetchone()

    cursor.close()
    conn.close()

    usuario_log = Usuario(cuenta['id'], cuenta['nombre_usuario'], cuenta['foto'])
    login_user(usuario_log)
    migrar_carrito_sesion_a_db(usuario_log.id)
    return redirect(url_for("panel_usuario"))


# ══════════════════════════════════════════════════════════
# PANEL PRINCIPAL — optimizado: 4 consultas en vez de 12
# ══════════════════════════════════════════════════════════

@app.route('/panel_usuario')
@login_required
def panel_usuario():
    usuario_id = current_user.id
    conn   = get_db_connection()
    cursor = conn.cursor()

    try:
        # ── 1 consulta: resumen completo del usuario ──
        cursor.execute('''
            SELECT
                u.foto,
                u.saldo_wallet,
                (SELECT COALESCE(SUM(CASE
                    WHEN tipo IN ('ingreso','abono_a_recibir')               THEN valor
                    WHEN tipo IN ('gasto','abono_deuda','prestamo_entregado') THEN -valor
                    ELSE 0 END), 0)
                 FROM movimientos WHERE usuario_id = u.id) AS saldo_neto,
                (SELECT COALESCE(SUM(valor),0) FROM movimientos
                 WHERE usuario_id = u.id AND tipo = 'ingreso') AS total_ingresos,
                (SELECT COALESCE(SUM(valor),0) FROM movimientos
                 WHERE usuario_id = u.id AND tipo = 'gasto') AS total_gastos,
                (SELECT COUNT(*) FROM tareas
                 WHERE usuario_id = u.id
                   AND COALESCE(estado,'pendiente') != 'completada') AS total_tareas_pendientes,
                (SELECT COUNT(*) FROM tareas
                 WHERE usuario_id = u.id AND estado = 'completada') AS total_tareas_completadas,
                (SELECT COUNT(*) FROM agenda
                 WHERE usuario_id = u.id AND fecha >= CURRENT_DATE) AS total_eventos_proximos,
                (SELECT COUNT(*) FROM deudas
                 WHERE usuario_id = u.id AND estado = 'pendiente') AS total_deudas_pendientes,
                (SELECT COALESCE(SUM(saldo),0) FROM deudas
                 WHERE usuario_id = u.id AND estado = 'pendiente') AS saldo_deudas_pendientes,
                (SELECT COUNT(*) FROM prestamos
                 WHERE usuario_id = u.id AND estado = 'pendiente') AS total_prestamos,
                (SELECT COALESCE(SUM(saldo),0) FROM prestamos
                 WHERE usuario_id = u.id AND estado = 'pendiente') AS saldo_prestamos
            FROM usuarios u WHERE u.id = ?
        ''', (usuario_id,))
        resumen = cursor.fetchone()

        foto           = resumen['foto'] or "https://res.cloudinary.com/di9wdbb1z/image/upload/v1750640818/default_xm9gvv.jpg"
        saldo_wallet   = float(resumen['saldo_wallet'] or 0)
        saldo_neto     = float(resumen['saldo_neto'] or 0)
        total_ingresos = float(resumen['total_ingresos'] or 0)
        total_gastos   = float(resumen['total_gastos'] or 0)
        total_tareas_pendientes  = int(resumen['total_tareas_pendientes'] or 0)
        total_tareas_completadas = int(resumen['total_tareas_completadas'] or 0)
        total_eventos_proximos   = int(resumen['total_eventos_proximos'] or 0)
        deudas_pendientes = {
            'total_deudas_pendientes': int(resumen['total_deudas_pendientes'] or 0),
            'saldo_deudas_pendientes': float(resumen['saldo_deudas_pendientes'] or 0),
        }
        prestamos_resumen = {
            'total_prestamos': int(resumen['total_prestamos'] or 0),
            'saldo_prestamos': float(resumen['saldo_prestamos'] or 0),
        }

        # ── 2 consultas: listas cortas ──
        cursor.execute('''
            SELECT fecha, descripcion, valor, tipo FROM movimientos
            WHERE usuario_id = ? ORDER BY fecha DESC, id DESC LIMIT 5
        ''', (usuario_id,))
        ultimos_movimientos = cursor.fetchall()

        cursor.execute('''
            SELECT titulo, fecha_limite, estado FROM tareas
            WHERE usuario_id = ? AND COALESCE(estado,'pendiente') != 'completada'
            ORDER BY CASE WHEN fecha_limite IS NULL THEN 1 ELSE 0 END, fecha_limite ASC
            LIMIT 5
        ''', (usuario_id,))
        tareas_pendientes_lista = cursor.fetchall()

        cursor.execute('''
            SELECT titulo, fecha, hora FROM agenda
            WHERE usuario_id = ? AND fecha >= CURRENT_DATE
            ORDER BY fecha ASC, hora ASC LIMIT 5
        ''', (usuario_id,))
        proximos_eventos = cursor.fetchall()

        # ── 3 consulta: datos para gráficas ──
        cursor.execute('''
            SELECT m.fecha, m.valor, m.tipo, c.nombre AS categoria_nombre
            FROM movimientos m
            LEFT JOIN categorias c ON m.categoria_id = c.id
            WHERE m.usuario_id = ?
            ORDER BY m.fecha ASC, m.id ASC
        ''', (usuario_id,))
        movimientos_chart = cursor.fetchall()

        cursor.execute('''
            SELECT estado, COUNT(*) AS cantidad
            FROM (
                SELECT CASE
                    WHEN estado = 'completada' THEN 'completada'
                    WHEN fecha_limite IS NOT NULL AND fecha_limite < CURRENT_DATE THEN 'vencida'
                    ELSE COALESCE(estado, 'pendiente')
                END AS estado
                FROM tareas WHERE usuario_id = ?
            ) sub GROUP BY estado
        ''', (usuario_id,))
        tareas_estado_rows = cursor.fetchall()

        # ── Procesamiento Python CORREGIDO ──
        from collections import OrderedDict
        import calendar

        hoy = date.today()

        MESES_ES = {
            1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
            7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
        }

        # Últimos 6 meses
        meses = []
        for i in range(5, -1, -1):
            y, m = hoy.year, hoy.month - i
            while m <= 0:
                m += 12
                y -= 1
            meses.append((y, m))

        month_labels = []
        ingresos_por_mes = OrderedDict()
        gastos_por_mes = OrderedDict()

        for y, m in meses:
            key = f"{y}-{m:02d}"
            month_labels.append(f"{MESES_ES[m]} {y}")  # ✅ ya no confunde 04/26
            ingresos_por_mes[key] = 0.0
            gastos_por_mes[key] = 0.0

        categoria_gastos = {}
        movimientos_por_dia = OrderedDict()
        saldo_acumulado = 0.0

        for mov in movimientos_chart:
            fecha_obj = to_date(mov['fecha'])
            if not fecha_obj:
                continue

            fecha_key = fecha_obj.strftime('%Y-%m-%d')
            fecha_label = fecha_obj.strftime('%d/%m')
            month_key = fecha_obj.strftime('%Y-%m')

            valor = float(mov['valor'] or 0)
            tipo = mov['tipo']

            if month_key in ingresos_por_mes:
                if tipo in ('ingreso', 'abono_a_recibir'):
                    ingresos_por_mes[month_key] += valor
                elif tipo in ('gasto', 'abono_deuda', 'prestamo_entregado'):
                    gastos_por_mes[month_key] += valor

            if tipo in ('gasto', 'abono_deuda', 'prestamo_entregado'):
                cat = mov['categoria_nombre'] or 'Sin categoría'
                categoria_gastos[cat] = categoria_gastos.get(cat, 0) + valor

            if tipo in ('ingreso', 'abono_a_recibir'):
                saldo_acumulado += valor
            elif tipo in ('gasto', 'abono_deuda', 'prestamo_entregado'):
                saldo_acumulado -= valor

            # ✅ Agrupa por día, pero conserva el saldo real acumulado al cierre del día
            movimientos_por_dia[fecha_key] = {
                'label': fecha_label,
                'saldo': saldo_acumulado
            }

        saldo_items = list(movimientos_por_dia.values())[-8:]

        task_map = {'pendiente': 0, 'en progreso': 0, 'completada': 0, 'vencida': 0}
        for row in tareas_estado_rows:
            estado = row['estado'] or 'pendiente'
            task_map[estado] = int(row['cantidad'] or 0)

        chart_data = {
            'incomeExpense': {
                'labels': month_labels,
                'ingresos': [round(v, 2) for v in ingresos_por_mes.values()],
                'gastos': [round(v, 2) for v in gastos_por_mes.values()],
            },
            'categoryExpense': {
                'labels': list(categoria_gastos.keys()) or ['Sin datos'],
                'values': [round(v, 2) for v in categoria_gastos.values()] or [0],
            },
            'balanceTrend': {
                'labels': [i['label'] for i in saldo_items] or ['Sin datos'],
                'values': [round(i['saldo'], 2) for i in saldo_items] or [0],
            },
            'taskStatus': {
                'labels': ['Pendientes', 'En progreso', 'Completadas', 'Vencidas'],
                'values': [
                    task_map['pendiente'],
                    task_map['en progreso'],
                    task_map['completada'],
                    task_map['vencida']
                ],
            },
            'debtLoan': {
                'labels': ['Deudas', 'Préstamos'],
                'values': [
                    deudas_pendientes['saldo_deudas_pendientes'],
                    prestamos_resumen['saldo_prestamos']
                ],
            }
        }

        return render_template(
            'panel_usuario.html',
            usuario=current_user.nombre_usuario,
            usuario_foto=foto,
            ultimos_movimientos=ultimos_movimientos,
            tareas_pendientes=tareas_pendientes_lista,
            proximos_eventos=proximos_eventos,
            total_ingresos=total_ingresos,
            total_gastos=total_gastos,
            saldo_neto=saldo_neto,
            saldo_wallet=saldo_wallet,
            deudas_pendientes=deudas_pendientes,
            prestamos=prestamos_resumen,
            total_tareas_pendientes=total_tareas_pendientes,
            total_tareas_completadas=total_tareas_completadas,
            total_eventos_proximos=total_eventos_proximos,
            chart_data=chart_data
        )

    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════════════
# TAREAS
# ══════════════════════════════════════════════════════════

@app.route('/tareas', methods=['GET', 'POST'])
@login_required
def tareas():
    conn   = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        titulo      = request.form['titulo']
        fecha_limite = request.form.get('fecha_limite')
        lista_id    = request.form.get('lista_id')
        if lista_id:
            try:
                lista_id = int(lista_id)
            except (TypeError, ValueError):
                lista_id = None
        else:
            lista_id = None

        cursor.execute(
            'INSERT INTO tareas (titulo, lista_id, usuario_id, fecha_limite, estado) VALUES (?, ?, ?, ?, ?)',
            (titulo, lista_id, current_user.id, fecha_limite, 'pendiente')
        )
        conn.commit()

    cursor.execute('SELECT * FROM listas WHERE usuario_id = ?', (current_user.id,))
    listas = cursor.fetchall()

    cursor.execute('SELECT * FROM tareas WHERE usuario_id = ?', (current_user.id,))
    tareas_usuario = cursor.fetchall()

    tareas_por_lista = defaultdict(list)
    for tarea in tareas_usuario:
        key = tarea['lista_id']
        if key is not None:
            try:
                key = int(key)
            except (TypeError, ValueError):
                pass
        tareas_por_lista[key].append(tarea)

    cursor.close()
    conn.close()

    return render_template(
        'tareas.html',
        listas=listas,
        tareas_por_lista=tareas_por_lista,
        usuario=current_user.nombre_usuario
    )


@app.route('/eliminar_tarea', methods=['POST'])
@login_required
def eliminar_tarea():
    tarea_id = request.form.get('id')
    if not tarea_id:
        return redirect(url_for('tareas'))
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tareas WHERE id = ? AND usuario_id = ?', (tarea_id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Error al eliminar tarea:", e)
    return redirect(url_for('tareas'))


@app.route('/editar_tarea', methods=['POST'])
@login_required
def editar_tarea():
    tarea_id     = request.form.get('id')
    nuevo_titulo = request.form.get('titulo')
    if not tarea_id or not nuevo_titulo:
        return redirect(url_for('tareas'))
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE tareas SET titulo = ? WHERE id = ? AND usuario_id = ?',
            (nuevo_titulo, tarea_id, current_user.id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Error al editar tarea:", e)
    return redirect(url_for('tareas'))


@app.route('/crear_lista', methods=['POST'])
@login_required
def crear_lista():
    nombre = request.form['nombre']
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO listas (nombre, usuario_id) VALUES (?, ?)', (nombre, current_user.id))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Lista creada exitosamente", "success")
    return redirect(url_for('tareas'))


@app.route('/actualizar_lista', methods=['POST'])
@login_required
def actualizar_lista():
    data          = request.get_json()
    tarea_id      = data.get('id')
    nuevo_lista_id = data.get('nuevo_lista_id')
    nuevo_estado  = data.get('nuevo_estado')

    if not tarea_id or not nuevo_lista_id:
        return jsonify({'exito': False, 'error': 'Datos incompletos'})
    try:
        nuevo_lista_id = int(nuevo_lista_id)
    except (TypeError, ValueError):
        return jsonify({'exito': False, 'error': 'Lista inválida'})

    estados_validos = ('pendiente', 'en progreso', 'completada')
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        if nuevo_estado and nuevo_estado in estados_validos:
            cursor.execute(
                'UPDATE tareas SET lista_id = ?, estado = ? WHERE id = ? AND usuario_id = ?',
                (nuevo_lista_id, nuevo_estado, tarea_id, current_user.id)
            )
        else:
            cursor.execute(
                'UPDATE tareas SET lista_id = ? WHERE id = ? AND usuario_id = ?',
                (nuevo_lista_id, tarea_id, current_user.id)
            )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'exito': True})
    except Exception as e:
        return jsonify({'exito': False, 'error': str(e)})


@app.route('/actualizar_estado_tarea', methods=['POST'])
@login_required
def actualizar_estado_tarea():
    tarea_id    = request.form.get('id')
    nuevo_estado = request.form.get('estado')
    if not tarea_id or nuevo_estado not in ('pendiente', 'en progreso', 'completada'):
        return redirect(url_for('tareas'))
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE tareas SET estado = ? WHERE id = ? AND usuario_id = ?',
            (nuevo_estado, tarea_id, current_user.id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print('Error al actualizar estado de tarea:', e)
    return redirect(url_for('tareas'))


@app.route('/actualizar_color_lista', methods=['POST'])
@login_required
def actualizar_color_lista():
    id    = request.form.get('id')
    color = request.form.get('color')
    if not id or not color:
        return redirect(url_for('tareas'))
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE listas SET color = ? WHERE id = ? AND usuario_id = ?',
            (color, id, current_user.id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass
    return redirect(url_for('tareas'))


@app.route('/renombrar_lista', methods=['POST'])
@login_required
def renombrar_lista():
    id     = request.form.get('id')
    nombre = request.form.get('nombre')
    if not id or not nombre:
        return redirect(url_for('tareas'))
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE listas SET nombre = ? WHERE id = ? AND usuario_id = ?',
            (nombre, id, current_user.id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass
    return redirect(url_for('tareas'))


@app.route('/eliminar_lista', methods=['POST'])
@login_required
def eliminar_lista():
    id = request.form.get('id')
    if not id:
        return redirect(url_for('tareas'))
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM listas WHERE id = ? AND usuario_id = ?', (id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass
    return redirect(url_for('tareas'))


# ══════════════════════════════════════════════════════════
# AGENDA — clima en paralelo con ThreadPoolExecutor
# ══════════════════════════════════════════════════════════

@app.route('/agenda', methods=['GET', 'POST'])
@login_required
def agenda():
    conn   = get_db_connection()
    cursor = conn.cursor()

    try:
        if request.method == 'POST':
            titulo      = (request.form.get('titulo') or '').strip()
            descripcion = (request.form.get('descripcion') or '').strip()
            fecha       = (request.form.get('fecha') or '').strip()
            hora        = (request.form.get('hora') or '').strip()

            if titulo and fecha:
                cursor.execute(
                    'INSERT INTO agenda (titulo, descripcion, fecha, hora, usuario_id) VALUES (?, ?, ?, ?, ?)',
                    (titulo, descripcion, fecha, hora, current_user.id)
                )
                conn.commit()
                flash('Actividad guardada correctamente.', 'success')
                return redirect(url_for('agenda'))
            else:
                flash('El título y la fecha son obligatorios.', 'danger')

        cursor.execute(
            'SELECT * FROM agenda WHERE usuario_id = ? ORDER BY fecha ASC, hora ASC',
            (current_user.id,)
        )
        eventos = cursor.fetchall()

        eventos_list   = []
        eventos_futuros = []
        hoy   = date.today()
        ahora = datetime.now()

        for evento in eventos:
            fecha_raw = evento['fecha']
            hora_raw  = evento['hora']

            fecha_str = fecha_raw.isoformat() if hasattr(fecha_raw, 'isoformat') else (str(fecha_raw) if fecha_raw else '')
            hora_str  = str(hora_raw)[:5] if hora_raw else ''

            eventos_list.append({
                'id':          evento['id'],
                'titulo':      evento['titulo'],
                'descripcion': evento['descripcion'] or '',
                'fecha':       fecha_str,
                'hora':        hora_str
            })

            if fecha_str:
                try:
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    if hora_str:
                        fecha_hora_evento = datetime.strptime(f'{fecha_str} {hora_str}', '%Y-%m-%d %H:%M')
                    else:
                        fecha_hora_evento = datetime.combine(fecha_obj, datetime.min.time())

                    if fecha_obj > hoy or (fecha_obj == hoy and fecha_hora_evento >= ahora):
                        eventos_futuros.append((fecha_hora_evento, evento))
                except ValueError:
                    pass

        eventos_futuros.sort(key=lambda x: x[0])
        eventos_urgentes = [e for _, e in eventos_futuros[:4]]

        # ── Clima en paralelo — no bloquea ──
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_clima      = executor.submit(obtener_clima_actual, 'Medellín,CO')
            fut_pronostico = executor.submit(obtener_pronostico,   'Medellin,CO')
            try:
                clima = fut_clima.result(timeout=5)
            except Exception:
                clima = None
            try:
                pronostico = fut_pronostico.result(timeout=5)
            except Exception:
                pronostico = []

        return render_template(
            'agenda.html',
            eventos=eventos,
            eventos_urgentes=eventos_urgentes,
            eventos_json=json.dumps(eventos_list, ensure_ascii=False),
            usuario=current_user.nombre_usuario,
            clima=clima,
            pronostico=pronostico
        )

    except Exception as e:
        print(f'Error en agenda: {e}')
        flash('Ocurrió un error al cargar la agenda.', 'danger')
        return render_template(
            'agenda.html',
            eventos=[], eventos_urgentes=[], eventos_json='[]',
            usuario=current_user.nombre_usuario, clima=None, pronostico=[]
        )
    finally:
        cursor.close()
        conn.close()


@app.route('/eliminar_cita/<int:cita_id>')
@login_required
def eliminar_cita(cita_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'DELETE FROM agenda WHERE id = ? AND usuario_id = ?',
            (cita_id, current_user.id)
        )
        conn.commit()
        flash('Actividad eliminada correctamente.', 'success')
    except Exception as e:
        conn.rollback()
        print(f'Error al eliminar actividad: {e}')
        flash('No se pudo eliminar la actividad.', 'error')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('agenda'))


@app.route('/editar_evento', methods=['POST'])
@login_required
def editar_evento():
    evento_id   = request.form.get('id')
    titulo      = request.form.get('titulo')
    descripcion = request.form.get('descripcion')
    fecha       = request.form.get('fecha')
    hora        = request.form.get('hora') or ''

    if evento_id and titulo and fecha:
        try:
            conn   = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE agenda SET titulo = ?, descripcion = ?, fecha = ?, hora = ? WHERE id = ? AND usuario_id = ?',
                (titulo, descripcion, fecha, hora, evento_id, current_user.id)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print('Error al editar evento de agenda:', e)
    return redirect(url_for('agenda'))


def obtener_movimientos_mes_actual(usuario_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        hoy       = datetime.today()
        primer_dia = hoy.replace(day=1).strftime('%Y-%m-%d')
        ultimo_dia = hoy.strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT * FROM movimientos
            WHERE usuario_id = ? AND fecha BETWEEN ? AND ?
            ORDER BY fecha DESC
        """, (usuario_id, primer_dia, ultimo_dia))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════════════
# MOVIMIENTOS
# ══════════════════════════════════════════════════════════

@app.route('/movimientos', methods=['GET', 'POST'])
@login_required
def movimientos():
    usuario_id = current_user.id
    conn   = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT foto FROM usuarios WHERE id = ?', (usuario_id,))
        resultado_foto = cursor.fetchone()
        usuario_foto   = (
            resultado_foto['foto']
            if resultado_foto and resultado_foto['foto']
            else "https://res.cloudinary.com/di9wdbb1z/image/upload/v1750640818/default_xm9gvv.jpg"
        )

        if request.method == 'POST':
            fecha       = request.form['fecha']
            descripcion = (request.form.get('descripcion') or '').strip()
            valor       = Decimal(request.form['valor'])
            tipo        = request.form['tipo']

            if tipo not in ['ingreso', 'gasto']:
                flash('Tipo de movimiento inválido.', 'danger')
                return redirect(url_for('movimientos'))

            cursor.execute(
                'INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id) VALUES (?, ?, ?, ?, ?)',
                (fecha, descripcion, valor, tipo, usuario_id)
            )
            conn.commit()
            flash('Movimiento guardado correctamente.', 'success')
            return redirect(url_for('movimientos'))

        cursor.execute("""
            SELECT COALESCE(SUM(CASE
                WHEN tipo IN ('ingreso','abono_a_recibir')               THEN valor
                WHEN tipo IN ('gasto','abono_deuda','prestamo_entregado') THEN -valor
                ELSE 0 END), 0) AS saldo
            FROM movimientos WHERE usuario_id = ?
        """, (usuario_id,))
        saldo_disponible = cursor.fetchone()['saldo']

        if conn.is_postgres:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS ingresos_mes FROM movimientos
                WHERE usuario_id = ? AND tipo = 'ingreso'
                  AND DATE_TRUNC('month', fecha) = DATE_TRUNC('month', CURRENT_DATE)
            """, (usuario_id,))
        else:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS ingresos_mes FROM movimientos
                WHERE usuario_id = ? AND tipo = 'ingreso'
                  AND strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now')
            """, (usuario_id,))
        ingresos_mes = cursor.fetchone()['ingresos_mes']

        if conn.is_postgres:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS gastos_mes FROM movimientos
                WHERE usuario_id = ? AND tipo IN ('gasto','abono_deuda','prestamo_entregado')
                  AND DATE_TRUNC('month', fecha) = DATE_TRUNC('month', CURRENT_DATE)
            """, (usuario_id,))
        else:
            cursor.execute("""
                SELECT COALESCE(SUM(valor), 0) AS gastos_mes FROM movimientos
                WHERE usuario_id = ? AND tipo IN ('gasto','abono_deuda','prestamo_entregado')
                  AND strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now')
            """, (usuario_id,))
        gastos_mes = cursor.fetchone()['gastos_mes']

        cursor.execute("""
            SELECT fecha, descripcion, valor, tipo FROM movimientos
            WHERE usuario_id = ? ORDER BY fecha DESC, id DESC LIMIT 8
        """, (usuario_id,))
        ultimos_movimientos = cursor.fetchall()

        return render_template(
            'movimientos.html',
            saldo_actual=saldo_disponible,
            ingresos_mes=ingresos_mes,
            gastos_mes=gastos_mes,
            ultimos_movimientos=ultimos_movimientos,
            usuario=current_user.nombre_usuario,
            usuario_foto=usuario_foto
        )
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════════════
# FORMULARIO DE REGISTROS
# ══════════════════════════════════════════════════════════

from datetime import datetime, timezone

@app.route('/nuevo_registro', methods=['GET', 'POST'])
@login_required
def formulario_registros():
    form           = RegistroUnicoForm()
    categoria_form = CategoriaForm()

    conn   = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM categorias WHERE usuario_id = ?", (current_user.id,))
    categorias = cursor.fetchall()
    form.categoria.choices = [(c[0], c[1]) for c in categorias]

    if request.method == 'POST' and form.validate_on_submit():
        tipo        = form.tipo.data
        fecha       = form.fecha.data
        frecuencia  = form.frecuencia.data
        descripcion = (form.descripcion.data or '').strip()
        valor       = form.valor.data
        persona     = (form.persona.data or '').strip()
        categoria_id = form.categoria.data if tipo in ['ingreso', 'gasto'] else None
        usuario_id  = current_user.id
        movimiento_id = None

        try:
            if tipo in ['ingreso', 'gasto']:
                if conn.is_postgres:
                    cursor.execute("""
                        INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
                        VALUES (?, ?, ?, ?, ?, ?) RETURNING id
                    """, (fecha, descripcion, valor, tipo, usuario_id, categoria_id))
                    movimiento_id = cursor.fetchone()['id']
                else:
                    cursor.execute("""
                        INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (fecha, descripcion, valor, tipo, usuario_id, categoria_id))
                    movimiento_id = cursor.lastrowid
                conn.commit()

            elif tipo == 'deuda':
                cursor.execute("""
                    INSERT INTO deudas (descripcion, persona, usuario_id, monto_inicial, saldo,
                        frecuencia, estado, fecha, fecha_creacion, tipo, movimiento_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (descripcion, persona, usuario_id, valor, valor, frecuencia,
                      'pendiente', fecha, datetime.now(timezone.utc), tipo, movimiento_id))
                conn.commit()

            elif tipo == 'prestamo':
                cursor.execute("""
                    INSERT INTO prestamos (descripcion, persona, usuario_id, monto_inicial, saldo,
                        frecuencia, estado, fecha, fecha_creacion, movimiento_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (descripcion, persona, usuario_id, valor, valor, frecuencia,
                      'pendiente', fecha, datetime.now(timezone.utc), movimiento_id))
                cursor.execute("""
                    INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
                    VALUES (?, ?, ?, ?, ?, NULL)
                """, (fecha, f"Préstamo entregado a {persona}" if persona else "Préstamo entregado",
                      valor, 'prestamo_entregado', usuario_id))
                conn.commit()

            flash('Registro guardado correctamente.', 'success')
            return redirect(url_for('formulario_registros'))

        except Exception as e:
            conn.rollback()
            print("Error al guardar registro:", e)
            flash('Error al guardar el registro.', 'danger')

    cursor.close()
    conn.close()

    return render_template('formulario_registros.html', form=form, categoria_form=categoria_form)


@app.route('/crear_categoria', methods=['POST'])
@login_required
def crear_categoria():
    form = CategoriaForm()
    if form.validate_on_submit():
        nombre     = form.nombre.data
        usuario_id = current_user.id
        ahora      = datetime.utcnow()

        conn   = get_db_connection()
        cursor = conn.cursor()
        if conn.is_postgres:
            cursor.execute(
                "INSERT INTO categorias (nombre, usuario_id, fecha_creacion) VALUES (?, ?, ?) RETURNING id",
                (nombre, usuario_id, ahora)
            )
            nueva_categoria_id = cursor.fetchone()['id']
        else:
            cursor.execute(
                "INSERT INTO categorias (nombre, usuario_id, fecha_creacion) VALUES (?, ?, ?)",
                (nombre, usuario_id, ahora)
            )
            nueva_categoria_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'id': nueva_categoria_id, 'nombre': nombre})
    return "Formulario no válido", 400


# ══════════════════════════════════════════════════════════
# REGISTROS
# ══════════════════════════════════════════════════════════

@app.route('/registros')
@login_required
def registros():
    form        = DummyForm()
    usuario_id  = current_user.id
    mostrar_todo = request.args.get('ver_todo', '0') == '1'
    dias_mostrar = int(request.args.get('dias', 1)) if not mostrar_todo else 9999

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT m.*, c.nombre AS categoria_nombre
            FROM movimientos m
            LEFT JOIN categorias c ON m.categoria_id = c.id
            WHERE m.usuario_id = ? ORDER BY m.fecha DESC
        """, (usuario_id,))
        movimientos_lista = cursor.fetchall()

        cursor.execute("""
            SELECT id, fecha, descripcion, monto_inicial, estado, saldo
            FROM prestamos WHERE usuario_id = ? ORDER BY fecha DESC
        """, (usuario_id,))
        prestamos = cursor.fetchall()

        cursor.execute("""
            SELECT id, fecha, descripcion, monto_inicial, estado, saldo, tipo, persona
            FROM deudas WHERE usuario_id = ? ORDER BY fecha DESC
        """, (usuario_id,))
        deudas = cursor.fetchall()

        hoy          = date.today()
        limite_fecha = hoy - timedelta(days=dias_mostrar - 1)

        movimientos_agrupados = defaultdict(list)
        for m in movimientos_lista:
            fecha_obj = to_date(m['fecha'])
            if fecha_obj and fecha_obj >= limite_fecha:
                movimientos_agrupados[formatear_fecha_humana(fecha_obj)].append(m)

        prestamos_agrupados = defaultdict(list)
        for p in prestamos:
            fecha_obj = to_date(p['fecha'])
            if fecha_obj and fecha_obj >= limite_fecha:
                prestamos_agrupados[formatear_fecha_humana(fecha_obj)].append(p)

        deudas_agrupadas = defaultdict(list)
        for d in deudas:
            fecha_obj = to_date(d['fecha'])
            if fecha_obj and fecha_obj >= limite_fecha:
                deudas_agrupadas[formatear_fecha_humana(fecha_obj)].append(d)

        hay_mas_mov   = any(to_date(m['fecha']) and to_date(m['fecha']) < limite_fecha for m in movimientos_lista)
        hay_mas_prest = any(to_date(p['fecha']) and to_date(p['fecha']) < limite_fecha for p in prestamos)
        seccion       = request.args.get('seccion', 'ingresos')

        return render_template(
            'registros.html',
            movimientos_agrupados=movimientos_agrupados,
            prestamos_agrupados=prestamos_agrupados,
            deudas=deudas,
            mostrar_todo=mostrar_todo,
            dias_mostrar=dias_mostrar,
            mostrar_mas_movimientos=hay_mas_mov,
            mostrar_mas_prestamos=hay_mas_prest,
            seccion=seccion,
            form=form
        )
    finally:
        cursor.close()
        conn.close()


@app.route('/abonar_deuda', methods=['POST'])
@login_required
def abonar_deuda():
    deuda_id       = request.form.get('deuda_id')
    monto_abono_raw = request.form.get('monto_abono', '').strip()

    try:
        monto_abono = to_decimal(monto_abono_raw)
    except (InvalidOperation, ValueError):
        flash('El monto del abono no es válido.', 'danger')
        return redirect(url_for('registros', seccion='deudas'))

    if monto_abono <= 0:
        flash('El monto del abono debe ser mayor a 0.', 'danger')
        return redirect(url_for('registros', seccion='deudas'))

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT saldo, descripcion FROM deudas WHERE id = ? AND usuario_id = ?",
            (deuda_id, current_user.id)
        )
        deuda = cursor.fetchone()
        if not deuda:
            flash('Deuda no encontrada.', 'danger')
            return redirect(url_for('registros', seccion='deudas'))

        saldo_actual = to_decimal(deuda['saldo'])
        nuevo_saldo  = saldo_actual - monto_abono
        if nuevo_saldo <= 0:
            nuevo_saldo = Decimal('0')
            estado = 'pagado'
        else:
            estado = 'pendiente'

        descripcion_deuda = deuda['descripcion'] or f"Deuda ID {deuda_id}"
        cursor.execute("""
            INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
            VALUES (CURRENT_DATE, ?, ?, ?, ?, NULL)
        """, (f"Abono a deuda: {descripcion_deuda}", float(monto_abono), 'abono_deuda', current_user.id))
        cursor.execute("""
            UPDATE deudas SET saldo = ?, estado = ? WHERE id = ? AND usuario_id = ?
        """, (float(nuevo_saldo), estado, deuda_id, current_user.id))
        conn.commit()
        flash('Abono a deuda registrado correctamente.', 'success')

    except Exception as e:
        conn.rollback()
        print("Error en abonar_deuda:", e)
        flash('Ocurrió un error al registrar el abono.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('registros', seccion='deudas'))


@app.route('/prestamos/abonar', methods=['POST'])
@login_required
def abonar_prestamo():
    prestamo_id    = request.form.get('prestamo_id')
    monto_abono_raw = request.form.get('monto_abono', '').strip()

    try:
        monto_abono = to_decimal(monto_abono_raw)
    except (InvalidOperation, ValueError):
        flash('El monto del abono no es válido.', 'danger')
        return redirect(url_for('registros', seccion='prestamos'))

    if monto_abono <= 0:
        flash('El monto del abono debe ser mayor a 0.', 'danger')
        return redirect(url_for('registros', seccion='prestamos'))

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT saldo, descripcion FROM prestamos WHERE id = ? AND usuario_id = ?",
            (prestamo_id, current_user.id)
        )
        prestamo = cursor.fetchone()
        if not prestamo:
            flash('Préstamo no encontrado.', 'danger')
            return redirect(url_for('registros', seccion='prestamos'))

        saldo_actual = to_decimal(prestamo['saldo'])
        nuevo_saldo  = saldo_actual - monto_abono
        if nuevo_saldo <= 0:
            nuevo_saldo = Decimal('0')
            estado = 'pagado'
        else:
            estado = 'pendiente'

        descripcion_prestamo = prestamo['descripcion'] or f"Préstamo ID {prestamo_id}"
        cursor.execute("""
            UPDATE prestamos SET saldo = ?, estado = ? WHERE id = ? AND usuario_id = ?
        """, (float(nuevo_saldo), estado, prestamo_id, current_user.id))
        cursor.execute("""
            INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
            VALUES (CURRENT_DATE, ?, ?, ?, ?, NULL)
        """, (f"Abono recibido del préstamo: {descripcion_prestamo}", float(monto_abono), 'abono_a_recibir', current_user.id))
        conn.commit()
        flash('Abono de préstamo registrado correctamente.', 'success')

    except Exception as e:
        conn.rollback()
        print("Error en abonar_prestamo:", e)
        flash('Ocurrió un error al registrar el abono.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('registros', seccion='prestamos'))


@app.route('/exportar_pdf', methods=['GET'])
@login_required
def exportar_pdf():
    fecha_desde = request.args.get('fecha_desde')
    fecha_hasta = request.args.get('fecha_hasta')
    ordenar     = request.args.get('ordenar')
    seccion     = request.args.get('seccion', 'deudas')
    usuario_id  = current_user.id

    query  = 'SELECT * FROM movimientos WHERE usuario_id = ?'
    params = [usuario_id]

    if fecha_desde:
        query += ' AND fecha >= ?'
        params.append(fecha_desde)
    if fecha_hasta:
        query += ' AND fecha <= ?'
        params.append(fecha_hasta)

    if seccion == 'ingresos':
        query += " AND tipo IN ('ingreso', 'gasto')"
    else:
        query += " AND tipo IN ('deuda', 'a_recibir', 'abono_a_recibir', 'abono_deuda')"

    orden_map = {
        'fecha_asc':  ' ORDER BY fecha ASC',
        'fecha_desc': ' ORDER BY fecha DESC',
        'valor_asc':  ' ORDER BY valor ASC',
        'valor_desc': ' ORDER BY valor DESC',
    }
    query += orden_map.get(ordenar, '')

    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, tuple(params))
    movimientos_lista = cursor.fetchall()
    cursor.close()
    conn.close()

    logo_path = os.path.join(current_app.root_path, 'static', 'img', 'logo.png')
    with open(logo_path, 'rb') as image_file:
        logo_base64 = base64.b64encode(image_file.read()).decode('utf-8')

    rendered_html = render_template(
        'pdf_movimientos.html',
        movimientos=movimientos_lista,
        seccion=seccion,
        logo_base64=logo_base64
    )

    pdf_output   = BytesIO()
    pisa_status  = pisa.CreatePDF(rendered_html, dest=pdf_output)
    if pisa_status.err:
        return f"Error al generar PDF: {pisa_status.err}"

    pdf_output.seek(0)
    return send_file(pdf_output, as_attachment=True,
                     download_name='movimientos_filtrados.pdf',
                     mimetype='application/pdf')


@app.route('/certificado_prestamo/<int:movimiento_id>')
@login_required
def certificado_prestamo(movimiento_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM prestamos WHERE id = ?", [movimiento_id])
    prestamo = cursor.fetchone()
    cursor.close()

    if not prestamo or prestamo['usuario_id'] != current_user.id:
        conn.close()
        return "No autorizado", 403

    cursor = conn.cursor()
    cursor.execute("SELECT nombre_usuario FROM usuarios WHERE id = ?", [prestamo['usuario_id']])
    prestamista = cursor.fetchone()
    cursor.close()
    conn.close()

    rendered_html = render_template(
        'certificado_prestamo.html',
        movimiento=prestamo,
        prestamista=prestamista,
        usuario_nombre=current_user.nombre_usuario,
        ahora=datetime.now()
    )

    pdf_output  = BytesIO()
    pisa_status = pisa.CreatePDF(rendered_html, dest=pdf_output)
    if pisa_status.err:
        return f"Error al generar PDF: {pisa_status.err}"

    pdf_output.seek(0)
    nombre_archivo = 'paz_y_salvo_deuda.pdf' if prestamo['saldo'] == 0 else 'certificado_prestamo.pdf'
    return send_file(pdf_output, as_attachment=True,
                     download_name=nombre_archivo, mimetype='application/pdf')


# ══════════════════════════════════════════════════════════
# ESTADÍSTICAS
# ══════════════════════════════════════════════════════════

@app.route('/estadisticas')
@login_required
def estadisticas():
    return render_template('estadisticas.html')


@app.route('/estadisticas/data')
@login_required
def estadisticas_data():
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT fecha,
                SUM(CASE WHEN tipo = 'ingreso' THEN valor ELSE 0 END) AS ingreso,
                SUM(CASE WHEN tipo = 'gasto'   THEN valor ELSE 0 END) AS gasto
            FROM movimientos WHERE usuario_id = ?
            GROUP BY fecha ORDER BY fecha
        """, (current_user.id,))
        movimientos_data = [
            {'fecha': str(f[0])[:10], 'ingreso': float(f[1] or 0), 'gasto': float(f[2] or 0)}
            for f in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT persona, SUM(saldo) as total_saldo
            FROM deudas WHERE usuario_id = ? GROUP BY persona
        """, (current_user.id,))
        deudas = [{'persona': d[0], 'total_saldo': float(d[1] or 0)} for d in cursor.fetchall()]

        cursor.execute("""
            SELECT persona, COUNT(*) as cantidad, SUM(monto_inicial) as monto_total
            FROM prestamos WHERE usuario_id = ? GROUP BY persona
        """, (current_user.id,))
        prestamos = [
            {'persona': p[0], 'cantidad': int(p[1] or 0), 'monto_total': float(p[2] or 0)}
            for p in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT estado, COUNT(*) as cantidad
            FROM (
                SELECT CASE
                    WHEN estado = 'completada' THEN 'completada'
                    WHEN fecha_limite IS NOT NULL AND fecha_limite < CURRENT_DATE THEN 'vencida'
                    ELSE COALESCE(estado, 'pendiente')
                END AS estado
                FROM tareas WHERE usuario_id = ?
            ) sub GROUP BY estado
        """, (current_user.id,))
        tareas = [{'estado': t[0], 'cantidad': int(t[1] or 0)} for t in cursor.fetchall()]

        return jsonify({'movimientos': movimientos_data, 'deudas': deudas,
                        'prestamos': prestamos, 'tareas': tareas})

    except Exception as e:
        print("❌ Error en estadísticas:", e)
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════════════
# CARTERA / PAGOS
# ══════════════════════════════════════════════════════════

@app.route('/confirmacion_wompi')
@login_required
def confirmacion_wompi():
    transaccion_id = request.args.get('id')
    referencia = request.args.get('reference')

    if not transaccion_id and not referencia:
        flash('No se recibió información de confirmación de Wompi.', 'warning')
        return redirect(url_for('cartera'))

    flash('Pago enviado a verificación. Si fue aprobado, tu saldo se actualizará.', 'info')
    return redirect(url_for('cartera'))


def generar_url_wompi(monto, referencia):
    monto_centavos = int(Decimal(monto) * 100)
    return (
        f"https://checkout.wompi.co/p/"
        f"?public-key={os.environ['WOMPI_PUBLIC_KEY']}"
        f"&currency=COP&amount-in-cents={monto_centavos}"
        f"&reference={referencia}"
        f"&redirect-url=https://tusitio.com/confirmacion_wompi"
    )


# ══════════════════════════════════════════════════════════
# CARTERA — Vinculación de tarjetas con Wompi
# ══════════════════════════════════════════════════════════

@app.route('/cartera')
@login_required
def cartera():
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT saldo_wallet FROM usuarios WHERE id = ?', (current_user.id,))
    saldo = cursor.fetchone()['saldo_wallet']

    cursor.execute('''
        SELECT marca, ultimos_4, fecha_exp
        FROM tarjetas_vinculadas
        WHERE usuario_id = ? AND activa = TRUE
        ORDER BY fecha_creacion DESC LIMIT 1
    ''', (current_user.id,))
    tarjeta = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template(
        'cartera.html',
        saldo=saldo,
        tarjeta=tarjeta,
        wompi_public_key=os.environ.get('WOMPI_PUBLIC_KEY', '')
    )


@app.route('/vincular_tarjeta', methods=['POST'])
@login_required
def vincular_tarjeta():
    """
    Recibe el token generado por el widget de Wompi en el frontend.
    Consulta la API de Wompi para obtener los datos reales de la tarjeta.
    """
    data       = request.get_json()
    token      = data.get('token')
    marca      = data.get('brand', '').upper()
    ultimos_4  = data.get('last_four', '****')
    fecha_exp  = data.get('exp_month', '') + '/' + data.get('exp_year', '')

    if not token:
        return jsonify({'exito': False, 'error': 'Token no recibido'}), 400

    try:
        conn   = get_db_connection()
        cursor = conn.cursor()

        # Desactivar tarjetas anteriores del usuario
        cursor.execute(
            'UPDATE tarjetas_vinculadas SET activa = FALSE WHERE usuario_id = ?',
            (current_user.id,)
        )

        # Guardar nueva tarjeta
        cursor.execute('''
            INSERT INTO tarjetas_vinculadas (usuario_id, token, marca, ultimos_4, fecha_exp, activa)
            VALUES (?, ?, ?, ?, ?, TRUE)
        ''', (current_user.id, token, marca, ultimos_4, fecha_exp))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'exito': True})

    except Exception as e:
        print('Error al vincular tarjeta:', e)
        return jsonify({'exito': False, 'error': str(e)}), 500


@app.route('/desvincular_tarjeta', methods=['POST'])
@login_required
def desvincular_tarjeta():
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE tarjetas_vinculadas SET activa = FALSE WHERE usuario_id = ?',
            (current_user.id,)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Tarjeta desvinculada correctamente.', 'success')
    except Exception as e:
        print('Error al desvincular:', e)
        flash('No se pudo desvincular la tarjeta.', 'danger')
    return redirect(url_for('cartera'))


@app.route('/iniciar_wompi', methods=['POST'])
@login_required
def iniciar_wompi():
    try:
        monto_raw = (request.form.get('monto') or '').strip()

        if not monto_raw:
            flash('Debes ingresar un monto válido.', 'danger')
            return redirect(url_for('cartera'))

        try:
            monto = Decimal(monto_raw)
        except Exception:
            flash('El monto ingresado no es válido.', 'danger')
            return redirect(url_for('cartera'))

        if monto <= 0:
            flash('El monto debe ser mayor a cero.', 'danger')
            return redirect(url_for('cartera'))

        wompi_public = os.environ.get('WOMPI_PUBLIC_KEY', '').strip()
        wompi_private = os.environ.get('WOMPI_PRIVATE_KEY', '').strip()

        if not wompi_public:
            print('ERROR WOMPI: Falta WOMPI_PUBLIC_KEY')
            flash('Wompi no está configurado correctamente.', 'danger')
            return redirect(url_for('cartera'))

        referencia = f"ORYON-{current_user.id}-{int(datetime.now(timezone.utc).timestamp())}"

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute('''
                SELECT token FROM tarjetas_vinculadas
                WHERE usuario_id = ? AND activa = TRUE
                ORDER BY fecha_creacion DESC
                LIMIT 1
            ''', (current_user.id,))
            tarjeta = cur.fetchone()

            cur.execute(
                '''
                INSERT INTO recargas (usuario_id, metodo, transaccion_id, monto, estado)
                VALUES (?, 'wompi', ?, ?, ?)
                ''',
                (current_user.id, referencia, float(monto), 'pendiente')
            )

            conn.commit()

        finally:
            cur.close()
            conn.close()

        # Si tiene tarjeta vinculada, cobrar con token
        if tarjeta:
            if not wompi_private:
                print('ERROR WOMPI: Falta WOMPI_PRIVATE_KEY')
                flash('Wompi no está configurado para cobros con tarjeta guardada.', 'danger')
                return redirect(url_for('cartera'))

            response = requests.post(
                'https://production.wompi.co/v1/transactions',
                headers={
                    'Authorization': f'Bearer {wompi_private}',
                    'Content-Type': 'application/json'
                },
                json={
                    'amount_in_cents': int(monto * 100),
                    'currency': 'COP',
                    'customer_email': getattr(current_user, 'correo_electronico', None) or 'cliente@orion360.com',
                    'reference': referencia,
                    'payment_method': {
                        'type': 'CARD',
                        'token': tarjeta['token'],
                        'installments': 1
                    }
                },
                timeout=20
            )

            try:
                resp_data = response.json()
            except Exception:
                print('RESPUESTA WOMPI NO JSON:', response.text)
                flash('Wompi devolvió una respuesta inválida.', 'danger')
                return redirect(url_for('cartera'))

            print('RESPUESTA WOMPI TOKEN:', resp_data)

            estado = resp_data.get('data', {}).get('status', '')

            if response.ok and estado == 'APPROVED':
                conn = get_db_connection()
                cur = conn.cursor()

                try:
                    cur.execute(
                        "UPDATE recargas SET estado = 'exitosa' WHERE transaccion_id = ?",
                        (referencia,)
                    )
                    cur.execute(
                        "UPDATE usuarios SET saldo_wallet = saldo_wallet + ? WHERE id = ?",
                        (float(monto), current_user.id)
                    )
                    conn.commit()
                finally:
                    cur.close()
                    conn.close()

                flash(f'Recarga de ${monto:,.0f} COP aprobada.', 'success')
            else:
                conn = get_db_connection()
                cur = conn.cursor()

                try:
                    cur.execute(
                        "UPDATE recargas SET estado = 'fallida' WHERE transaccion_id = ?",
                        (referencia,)
                    )
                    conn.commit()
                finally:
                    cur.close()
                    conn.close()

                flash('El pago no fue aprobado. Intenta de nuevo.', 'danger')

            return redirect(url_for('cartera'))

        # Sin tarjeta vinculada → redirigir al checkout de Wompi
        monto_centavos = int(monto * 100)

        url_pago = (
            "https://checkout.wompi.co/p/"
            f"?public-key={wompi_public}"
            f"&currency=COP"
            f"&amount-in-cents={monto_centavos}"
            f"&reference={referencia}"
            f"&redirect-url={url_for('confirmacion_wompi', _external=True)}"
        )

        return redirect(url_pago)

    except Exception as e:
        import traceback
        print('ERROR EN /iniciar_wompi:', e)
        traceback.print_exc()
        flash('Error al iniciar pago con Wompi.', 'danger')
        return redirect(url_for('cartera'))

# ══════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════

@app.route('/actualizar_usuario', methods=['POST'])
@login_required
def actualizar_usuario():
    nombre      = request.form.get('nombre', '').strip()
    email       = request.form.get('email', '').strip()
    telefono    = request.form.get('telefono', '').strip()
    nueva_clave = request.form.get('nueva_clave', '').strip()
    foto        = request.files.get('foto')

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        if nombre:
            cursor.execute('UPDATE usuarios SET nombre_usuario = ? WHERE id = ?', (nombre, current_user.id))
        if email:
            cursor.execute('UPDATE usuarios SET correo_electronico = ? WHERE id = ?', (email, current_user.id))
        if telefono:
            cursor.execute('UPDATE usuarios SET telefono = ? WHERE id = ?', (telefono, current_user.id))
        if nueva_clave:
            cursor.execute('UPDATE usuarios SET contraseña = ? WHERE id = ?',
                           (generate_password_hash(nueva_clave), current_user.id))
        if foto and foto.filename != '':
            try:
                resultado = cloudinary.uploader.upload(foto)
                url_foto  = resultado.get('secure_url')
                cursor.execute('UPDATE usuarios SET foto = ? WHERE id = ?', (url_foto, current_user.id))
            except Exception as e:
                flash('No se pudo subir la imagen.', 'warning')
                print('Error Cloudinary:', e)

        conn.commit()
        flash('Perfil actualizado correctamente.', 'success')

    except Exception as e:
        conn.rollback()
        flash(f'Error al actualizar: {str(e)}', 'danger')
        print('Error actualizar_usuario:', e)
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('configuracion'))


@app.route('/configuracion')
@login_required
def configuracion():
    return render_template('configuracion.html')


# ══════════════════════════════════════════════════════════
# COMPRAS / CARRITO
# ══════════════════════════════════════════════════════════

@app.route("/compras")
def compras():
    tiendas_productos = tiendas.obtener_productos_por_tienda()
    return render_template("compras.html", tiendas_productos=tiendas_productos)


@app.route("/producto/<tienda>/<nombre>")
def producto_detalle(tienda, nombre):
    productos = tiendas.obtener_productos_por_tienda().get(tienda, [])
    producto  = next((p for p in productos if p["nombre"] == nombre), None)
    if not producto:
        return "Producto no encontrado", 404
    return render_template("detalle_producto.html", producto=producto)


def obtener_carrito_usuario(usuario_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, precio, imagen FROM carrito_items WHERE usuario_id = ?",
        (usuario_id,)
    )
    carrito = [dict(item) for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return carrito


def migrar_carrito_sesion_a_db(usuario_id):
    carrito_sesion = session.pop('carrito', [])
    if not carrito_sesion:
        return
    conn   = get_db_connection()
    cursor = conn.cursor()
    for item in carrito_sesion:
        cursor.execute(
            "INSERT INTO carrito_items (usuario_id, nombre, precio, imagen) VALUES (?, ?, ?, ?)",
            (usuario_id, item.get('nombre'), item.get('precio'), item.get('imagen'))
        )
    conn.commit()
    cursor.close()
    conn.close()


@csrf.exempt
@app.route("/agregar-carrito", methods=["POST"])
def agregar_al_carrito():
    item = {
        "nombre": request.form["nombre"],
        "precio": float(request.form["precio"]),
        "imagen": request.form["imagen"]
    }
    if current_user.is_authenticated:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO carrito_items (usuario_id, nombre, precio, imagen) VALUES (?, ?, ?, ?)",
            (current_user.id, item["nombre"], item["precio"], item["imagen"])
        )
        conn.commit()
        cursor.close()
        conn.close()
    else:
        if "carrito" not in session:
            session["carrito"] = []
        session["carrito"].append(item)
        session.modified = True
    return redirect(url_for("ver_carrito"))


@app.route("/carrito")
def ver_carrito():
    if current_user.is_authenticated:
        carrito = obtener_carrito_usuario(current_user.id)
    else:
        carrito = session.get("carrito", [])
    total = sum(item["precio"] for item in carrito)
    return render_template("carrito.html", carrito=carrito, total=total)


@app.route("/eliminar-carrito/<int:item_id>")
def eliminar_del_carrito(item_id):
    if current_user.is_authenticated:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM carrito_items WHERE id = ? AND usuario_id = ?",
            (item_id, current_user.id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    else:
        carrito = session.get("carrito", [])
        if 0 <= item_id < len(carrito):
            carrito.pop(item_id)
            session.modified = True
    return redirect(url_for("ver_carrito"))


# ══════════════════════════════════════════════════════════
# IDEAS
# ══════════════════════════════════════════════════════════

@app.route("/ideas", methods=["GET", "POST"])
@login_required
def ideas():
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == "POST":
            titulo      = (request.form.get("titulo") or "").strip()
            descripcion = (request.form.get("descripcion") or "").strip()
            categoria   = (request.form.get("categoria") or "").strip()

            if not titulo or not descripcion:
                flash("Título y descripción son obligatorios.", "danger")
                return redirect(url_for("ideas"))

            cursor.execute(
                "INSERT INTO ideas (titulo, descripcion, categoria) VALUES (?, ?, ?)",
                (titulo, descripcion, categoria)
            )
            conn.commit()
            flash("Idea registrada con éxito.", "success")
            return redirect(url_for("ideas"))

        cursor.execute("SELECT * FROM ideas ORDER BY fecha_creacion DESC, id DESC")
        ideas_list = cursor.fetchall()
        return render_template("ideas.html", ideas=ideas_list)

    except Exception as e:
        conn.rollback()
        print("Error en ideas:", e)
        flash("Ocurrió un error al cargar o guardar ideas.", "danger")
        return render_template("ideas.html", ideas=[])
    finally:
        cursor.close()
        conn.close()


@app.route("/eliminar_idea/<int:id>", methods=["POST"])
@login_required
def eliminar_idea(id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ideas WHERE id = ?", (id,))
        conn.commit()
        flash("Idea eliminada correctamente.", "success")
    except Exception as e:
        conn.rollback()
        print("Error al eliminar idea:", e)
        flash("No se pudo eliminar la idea.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("ideas"))


@app.route("/editar_idea/<int:id>", methods=["GET", "POST"])
@login_required
def editar_idea(id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == "POST":
            titulo      = (request.form.get("titulo") or "").strip()
            descripcion = (request.form.get("descripcion") or "").strip()
            categoria   = (request.form.get("categoria") or "").strip()

            if not titulo or not descripcion:
                flash("Título y descripción son obligatorios.", "danger")
                return redirect(url_for("editar_idea", id=id))

            cursor.execute(
                "UPDATE ideas SET titulo = ?, descripcion = ?, categoria = ? WHERE id = ?",
                (titulo, descripcion, categoria, id)
            )
            conn.commit()
            flash("Idea actualizada correctamente.", "success")
            return redirect(url_for("ideas"))

        cursor.execute("SELECT * FROM ideas WHERE id = ?", (id,))
        idea = cursor.fetchone()
        if not idea:
            flash("La idea no existe.", "danger")
            return redirect(url_for("ideas"))
        return render_template("editar_idea.html", idea=idea)

    except Exception as e:
        conn.rollback()
        print("Error al editar idea:", e)
        flash("No se pudo editar la idea.", "danger")
        return redirect(url_for("ideas"))
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════════════
# ASISTENTE (Groq)
# ══════════════════════════════════════════════════════════

@app.route('/asistente')
@login_required
def asistente():
    return render_template('asistente.html', nombre=current_user.nombre_usuario)


@app.route('/consultar', methods=['POST'])
@login_required
def consultar():
    consulta_usuario = request.form.get('consulta', '')
    imagen = request.files.get('imagen', None)

    if not consulta_usuario:
        return jsonify({"error": "Consulta vacía", "mensaje": "⚠️ Consulta vacía"}), 400

    imagen_binaria = None
    mime_type = None

    if imagen and imagen.filename != "":
        try:
            imagen_binaria = imagen.read()

            if imagen_binaria:
                tipo = imagen.mimetype.split("/")[-1]

                if tipo == "jpg":
                    tipo = "jpeg"

                mime_type = f"image/{tipo}"

        except Exception as e:
            return jsonify({
                "error": str(e),
                "mensaje": f"❌ Error al procesar la imagen: {str(e)}"
            }), 500

    try:
        contexto_orion = construir_contexto_orion(current_user.id)

        prompt_final = f"""
Eres ORION, el asistente inteligente de Orion 360.

Tu tarea es ayudar al usuario con su información real dentro de la app:
- finanzas
- ingresos
- gastos
- deudas
- préstamos
- agenda
- movimientos
- facturas
- organización personal

REGLAS IMPORTANTES:
1. Responde siempre en español.
2. Usa solamente los datos proporcionados en el contexto.
3. No inventes datos que no estén en el contexto.
4. Si el usuario pregunta algo que no está disponible, responde que no tienes ese dato cargado.
5. Sé claro, directo y útil.
6. Cuando hables de dinero, usa formato en pesos.
7. El contexto pertenece únicamente al usuario autenticado actual.

{contexto_orion}

PREGUNTA DEL USUARIO:
{consulta_usuario}
"""

        texto_respuesta = generar_respuesta_groq(
            prompt_final,
            imagen_binaria,
            mime_type
        )

        return jsonify({"mensaje": texto_respuesta})

    except Exception as e:
        print("Error en consultar ORION:", e)
        return jsonify({
            "error": str(e),
            "mensaje": f"❌ Error al procesar la consulta: {str(e)}"
        }), 500
    

@app.route('/groq_status')
@login_required
def groq_status():
    return jsonify({
        "enabled": groq_client is not None,
        "message": "Groq está configurado." if groq_client is not None else "Groq no está disponible. Verifica GROQ_API_KEY."
    })

# ══════════════════════════════════════════════════════════
# CONFIGURACIÓN GROQ
# ══════════════════════════════════════════════════════════

from groq import Groq

def inicializar_groq():
    api_key = app.config.get('GROQ_API_KEY')

    if not api_key:
        print('[WARNING] GROQ_API_KEY no configurada.')
        return None

    try:
        cliente = Groq(api_key=api_key)
        print('[OK] Groq API inicializada correctamente.')
        return cliente
    except Exception as e:
        print('[WARNING] No se pudo inicializar Groq:', str(e)[:180])
        return None


groq_client = inicializar_groq()


def generar_respuesta_groq(prompt, imagen_binaria=None, mime_type=None):
    if groq_client is None:
        raise RuntimeError('GROQ_API_KEY no está configurada o Groq no se inició.')

    modelo_texto = 'llama-3.3-70b-versatile'
    modelo_vision = 'meta-llama/llama-4-scout-17b-16e-instruct'

    if imagen_binaria and mime_type:
        imagen_base64 = base64.b64encode(imagen_binaria).decode('utf-8')

        respuesta = groq_client.chat.completions.create(
            model=modelo_vision,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres ORION, el asistente inteligente de Orion 360. "
                        "Responde siempre en español. Si se solicita JSON, "
                        "devuelve únicamente JSON válido."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{imagen_base64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.1,
            max_completion_tokens=1024,
            response_format={"type": "json_object"}
        )
    else:
        respuesta = groq_client.chat.completions.create(
            model=modelo_texto,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres ORION, el asistente inteligente de Orion 360. "
                        "Ayudas con agenda, finanzas, deudas, préstamos, gastos, "
                        "ingresos, tareas, compras, ideas y configuración. "
                        "Responde claro, útil, práctico y siempre en español. "
                        "No inventes datos privados si no fueron consultados desde la app."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_completion_tokens=1200
        )

    return respuesta.choices[0].message.content


# ══════════════════════════════════════════════════════════
# ESCÁNER DE FACTURAS (Groq)
# ══════════════════════════════════════════════════════════

@app.route('/escanear_factura', methods=['GET'])
@login_required
def escanear_factura():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT id, nombre FROM categorias WHERE usuario_id = ?',
        (current_user.id,)
    )
    categorias = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('escanear_factura.html', categorias=categorias)


@app.route('/procesar_factura', methods=['POST'])
@login_required
def procesar_factura():
    imagen = request.files.get('imagen')

    if not imagen or imagen.filename == '':
        return jsonify({'error': 'No se recibió ninguna imagen'}), 400

    try:
        imagen_binaria = imagen.read()

        if not imagen_binaria:
            return jsonify({'error': 'La imagen está vacía'}), 400

        # Groq con base64 funciona mejor con imágenes no muy pesadas
        if len(imagen_binaria) > 8 * 1024 * 1024:
            return jsonify({'error': 'La imagen es muy pesada. Usa una imagen menor a 4 MB.'}), 400

        tipo = imagen.mimetype.split('/')[-1]

        if tipo == 'jpg':
            tipo = 'jpeg'

        if tipo not in ['jpeg', 'png', 'webp']:
            return jsonify({'error': 'Formato no soportado. Usa JPG, PNG o WEBP.'}), 400

        mime_type = f'image/{tipo}'

    except Exception as e:
        return jsonify({'error': f'Error al leer la imagen: {str(e)}'}), 500

    prompt = f"""Analiza esta factura o recibo y extrae la información en formato JSON.

Fecha de hoy: {date.today().isoformat()}

Responde ÚNICAMENTE con JSON válido.
No uses markdown.
No uses bloques de código.
No agregues explicaciones.

El JSON debe tener exactamente estas claves:
{{
  "descripcion": "nombre del establecimiento o descripción del gasto",
  "monto": 0.00,
  "fecha": "YYYY-MM-DD"
}}

Reglas:
- "descripcion" debe ser corta y clara.
- "monto" debe ser numérico, sin símbolo de moneda, sin puntos de miles.
- "fecha" debe estar en formato YYYY-MM-DD.
- Si el recibo está en español, interpreta total, subtotal, valor pagado o total a pagar.
- Si no puedes leer algún campo con certeza, usa:
  - descripcion: "Gasto escaneado"
  - monto: 0.00
  - fecha: "{date.today().isoformat()}"

Responde SOLO JSON válido."""

    try:
        resultado = generar_respuesta_groq(prompt, imagen_binaria, mime_type)
        resultado = (resultado or '').strip()

        # Limpieza defensiva por si el modelo devuelve texto extra
        resultado = resultado.replace('```json', '').replace('```', '').strip()

        inicio = resultado.find('{')
        fin = resultado.rfind('}')

        if inicio != -1 and fin != -1:
            resultado = resultado[inicio:fin + 1]

        datos = json.loads(resultado)

        descripcion = str(datos.get('descripcion', 'Gasto escaneado')).strip()
        fecha = str(datos.get('fecha', date.today().isoformat())).strip()

        monto_raw = datos.get('monto', 0)

        try:
            monto = float(str(monto_raw).replace('$', '').replace(',', '').strip())
        except (ValueError, TypeError):
            monto = 0.0

        try:
            datetime.strptime(fecha, '%Y-%m-%d')
        except ValueError:
            fecha = date.today().isoformat()

        if not descripcion:
            descripcion = 'Gasto escaneado'

        return jsonify({
            'exito': True,
            'descripcion': descripcion,
            'monto': monto,
            'fecha': fecha
        })

    except json.JSONDecodeError:
        return jsonify({
            'exito': True,
            'descripcion': 'Gasto escaneado',
            'monto': 0.0,
            'fecha': date.today().isoformat(),
            'advertencia': 'No se pudo leer la factura con claridad. Completa los datos manualmente.'
        })

    except Exception as e:
        print('Error Groq factura:', e)
        return jsonify({'error': f'Error al procesar: {str(e)}'}), 500


@app.route('/guardar_factura', methods=['POST'])
@login_required
def guardar_factura():
    try:
        fecha = (request.form.get('fecha') or '').strip()
        descripcion = (request.form.get('descripcion') or '').strip()
        monto_raw = (request.form.get('monto') or '0').strip()
        categoria_id = request.form.get('categoria_id') or None

        if not fecha or not descripcion:
            flash('Fecha y descripción son obligatorios.', 'danger')
            return redirect(url_for('escanear_factura'))

        try:
            monto = float(monto_raw)
        except ValueError:
            flash('El monto no es válido.', 'danger')
            return redirect(url_for('escanear_factura'))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''
            INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (fecha, descripcion, monto, 'gasto', current_user.id, categoria_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        flash('Gasto guardado correctamente desde la factura.', 'success')
        return redirect(url_for('registros'))

    except Exception as e:
        print('Error al guardar factura:', e)
        flash('Ocurrió un error al guardar el gasto.', 'danger')
        return redirect(url_for('escanear_factura'))
    


@app.route('/ahorros')
@login_required
def ahorros():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nombre, objetivo, ahorrado
        FROM ahorros
        WHERE usuario_id = ?
    """, (current_user.id,))

    ahorros = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('ahorros.html', ahorros=ahorros)        


@app.route('/negocios')
@login_required
def emprendimientos():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nombre, ingresos, gastos
        FROM negocios
        WHERE usuario_id = ?
    """, (current_user.id,))

    negocios = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('negocios.html', negocios=negocios)

@app.route('/ahorros/crear', methods=['POST'])
@login_required
def crear_ahorro():
    nombre   = (request.form.get('nombre') or '').strip()
    objetivo = request.form.get('objetivo', 0)

    try:
        objetivo = float(objetivo)
    except ValueError:
        flash('Objetivo inválido.', 'danger')
        return redirect(url_for('ahorros'))

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO ahorros (usuario_id, nombre, objetivo, ahorrado)
            VALUES (?, ?, ?, 0)
        """, (current_user.id, nombre, objetivo))
        conn.commit()
        flash('Ahorro creado correctamente.', 'success')
    except Exception as e:
        conn.rollback()
        print('Error al crear ahorro:', e)
        flash('Error al crear el ahorro.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('ahorros'))


@app.route('/ahorros/abonar', methods=['POST'])
@login_required
def abonar_ahorro():
    ahorro_id = request.form.get('ahorro_id')
    monto_raw = (request.form.get('monto') or '0').strip()

    try:
        monto = float(monto_raw)
    except ValueError:
        flash('Monto inválido.', 'danger')
        return redirect(url_for('ahorros'))

    if monto <= 0:
        flash('El monto debe ser mayor a 0.', 'danger')
        return redirect(url_for('ahorros'))

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE ahorros SET ahorrado = ahorrado + ?
            WHERE id = ? AND usuario_id = ?
        """, (monto, ahorro_id, current_user.id))
        conn.commit()
        flash('Abono registrado correctamente.', 'success')
    except Exception as e:
        conn.rollback()
        print('Error al abonar ahorro:', e)
        flash('Error al registrar el abono.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('ahorros'))


@app.route('/negocios/crear', methods=['POST'])
@login_required
def crear_negocio():
    nombre = (request.form.get('nombre') or '').strip()

    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('emprendimientos'))

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO negocios (usuario_id, nombre, ingresos, gastos)
            VALUES (?, ?, 0, 0)
        """, (current_user.id, nombre))
        conn.commit()
        flash('Negocio creado correctamente.', 'success')
    except Exception as e:
        conn.rollback()
        print('Error al crear negocio:', e)
        flash('Error al crear el negocio.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('emprendimientos'))


@app.route('/negocios/registrar_movimiento', methods=['POST'])
@login_required
def registrar_movimiento_negocio():
    negocio_id = request.form.get('negocio_id')
    tipo       = request.form.get('tipo')  # 'ingreso' o 'gasto'
    monto_raw  = (request.form.get('monto') or '0').strip()

    try:
        monto = float(monto_raw)
    except ValueError:
        flash('Monto inválido.', 'danger')
        return redirect(url_for('emprendimientos'))

    if tipo not in ('ingreso', 'gasto'):
        flash('Tipo inválido.', 'danger')
        return redirect(url_for('emprendimientos'))

    campo = 'ingresos' if tipo == 'ingreso' else 'gastos'

    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            UPDATE negocios SET {campo} = {campo} + ?
            WHERE id = ? AND usuario_id = ?
        """, (monto, negocio_id, current_user.id))
        conn.commit()
        flash('Movimiento registrado.', 'success')
    except Exception as e:
        conn.rollback()
        print('Error al registrar movimiento negocio:', e)
        flash('Error al registrar el movimiento.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('emprendimientos'))    

@app.route('/test_mail')
def test_mail():
    try:
        msg = Message(
            subject='Test Brevo - Oryon 360',
            recipients=['viking108.81@gmail.com'],
            body='Si recibes esto, Brevo está funcionando correctamente.'
        )
        mail.send(msg)
        return '✅ Correo enviado correctamente'
    except Exception as e:
        return f'❌ Error: {e}'

if __name__ == '__main__':
    app.run(debug=True, port=5000)                                                                                                                                                                                                                                                        


# ══════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════

if __name__ == '__main__':
    app.run(debug=True, port=5000)