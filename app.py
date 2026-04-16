from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, current_app, jsonify
from requests_oauthlib import OAuth2Session
from flask_dance.contrib.google import make_google_blueprint, google
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
import json
import sqlite3
import psycopg2        # type: ignore
import psycopg2.extras # type: ignore
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google.generativeai import GenerativeModel, configure
from PIL import Image
import base64
import mimetypes
import google.generativeai as genai
import cloudinary
import cloudinary.uploader
from config import Config
import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'flaskform')))
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
sqlite3.register_adapter(Decimal, float)


# ══════════════════════════════════════════════════════════
# INICIALIZACIÓN DE LA APLICACIÓN
# ══════════════════════════════════════════════════════════

app = Flask(__name__)
app.config.from_object(Config)
print("DATABASE_URL:", app.config.get("DATABASE_URL"))

CORS(app)
csrf = CSRFProtect(app)

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
        """)

        cursor.execute('PRAGMA table_info(tareas)')
        columnas_tareas = [row[1] for row in cursor.fetchall()]
        if 'estado' not in columnas_tareas:
            cursor.execute("ALTER TABLE tareas ADD COLUMN estado TEXT DEFAULT 'pendiente'")

    conn.commit()
    cursor.close()
    conn.close()


# Verificar conexión
try:
    db_url = app.config.get('DATABASE_URL')

    conn = get_db_connection()
    init_db()
    conn.close()

    if db_url:
        print("✅ Conectado a PostgreSQL (Neon) correctamente.")
    else:
        print("✅ Conectado a SQLite correctamente.")

except Exception as e:
    print("❌ Error conectando a la base de datos")
    print("Detalle:", str(e))


# ══════════════════════════════════════════════════════════
# CONFIGURACIÓN GEMINI
# ══════════════════════════════════════════════════════════

def inicializar_gemini():
    api_key = app.config.get('GEMINI_API_KEY')
    if not api_key:
        print('⚠️ GEMINI_API_KEY no configurado; la función de asistente no funcionará.')
        return None

    try:
        genai.configure(api_key=api_key)
        modelo = genai.GenerativeModel(model_name='models/gemini-2.0-flash')
        print('✅ Gemini API inicializada correctamente.')
        return modelo
    except Exception as e:
        print('⚠️ No se pudo inicializar Gemini:', str(e)[:180])
        return None


def generar_respuesta_gemini(prompt, imagen_binaria=None, mime_type=None):
    if model is None:
        raise RuntimeError('GEMINI_API_KEY no está configurado o el modelo no se inició.')

    inputs = ['Responde siempre en español.', prompt]
    if imagen_binaria and mime_type:
        inputs.append({
            'mime_type': mime_type,
            'data': base64.b64encode(imagen_binaria).decode('utf-8')
        })

    resultado = model.generate_content(inputs)
    if hasattr(resultado, 'text'):
        return resultado.text
    if isinstance(resultado, str):
        return resultado
    return str(resultado)


model = inicializar_gemini()


# ══════════════════════════════════════════════════════════
# CONFIGURACIÓN ARCHIVOS & FILTROS JINJA
# ══════════════════════════════════════════════════════════

CARPETA_FOTOS = 'static/uploads'
if not os.path.exists(CARPETA_FOTOS):
    os.makedirs(CARPETA_FOTOS)
app.config['CARPETA_FOTOS'] = CARPETA_FOTOS
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def archivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def escapejs_filter(value):
    if not isinstance(value, str):
        value = str(value)
    replacements = {
        '\\': '\\\\',
        '"': '\\"',
        "'": "\\'",
        '\n': '\\n',
        '\r': '\\r',
        '</': '<\\/'
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


app.jinja_env.filters['escapejs'] = escapejs_filter


# ══════════════════════════════════════════════════════════
# CONTEXT PROCESSOR
# ══════════════════════════════════════════════════════════

@app.context_processor
def inject_user_data():
    if current_user.is_authenticated:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT foto FROM usuarios WHERE id = ?', (current_user.id,))
        resultado = cursor.fetchone()
        cursor.close()
        conn.close()
        foto = (
            resultado['foto']
            if resultado and resultado['foto']
            else "https://res.cloudinary.com/di9wdbb1z/image/upload/v1750640818/default_xm9gvv.jpg"
        )
        return {'usuario': current_user.nombre_usuario, 'usuario_foto': foto}
    return {}


# ══════════════════════════════════════════════════════════
# HELPERS DE FECHA
# ══════════════════════════════════════════════════════════

def to_date(val):
    """Convierte string, datetime o date a date. Retorna None si falla."""
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


# 👇 PEGA ESTO AQUÍ 👇
def to_decimal(valor):
    """
    Convierte float, int, str o Decimal a Decimal de forma segura.
    Evita mezclar float con Decimal en operaciones matemáticas.
    """
    if valor is None:
        return Decimal('0')
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def formatear_fecha_humana(fecha):
    """Devuelve 'Hoy', 'Ayer', nombre del día o dd/mm/yyyy."""
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
# MODELO DE USUARIO
# ══════════════════════════════════════════════════════════

class Usuario(UserMixin):
    def __init__(self, id, nombre_usuario):
        self.id = id
        self.nombre_usuario = nombre_usuario


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM usuarios WHERE id = ?', (user_id,))
    cuenta = cursor.fetchone()
    cursor.close()
    conn.close()
    if cuenta:
        return Usuario(cuenta['id'], cuenta['nombre_usuario'])
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
    correo = form.correo.data.strip().lower()
    clave = generate_password_hash(form.clave.data)
    foto = form.foto.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM usuarios WHERE nombre_usuario = ? OR correo_electronico = ?',
        (usuario, correo)
    )
    existente = cursor.fetchone()
    if existente:
        cursor.close()
        conn.close()
        flash('El nombre de usuario o correo ya está en uso.', 'danger')
        return redirect(url_for('registro'))

    url_foto = "https://res.cloudinary.com/di9wdbb1z/image/upload/v1750640818/default_xm9gvv.jpg"
    if foto and foto.filename != "":
        try:
            resultado = cloudinary.uploader.upload(foto)
            url_foto = resultado.get("secure_url")
        except Exception as e:
            flash("Error al subir imagen. Se usará la imagen por defecto.", "warning")
            print("Error Cloudinary:", e)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO usuarios (nombre_usuario, correo_electronico, contraseña, foto) VALUES (?, ?, ?, ?)',
        (usuario, correo, clave, url_foto)
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash('Registro exitoso.', 'success')
    return redirect(url_for('iniciar_sesion'))


@app.route('/iniciar_sesion', methods=['GET', 'POST'])
def iniciar_sesion():
    form = LoginForm()

    if form.validate_on_submit():
        usuario = form.usuario.data
        clave = form.clave.data

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM usuarios WHERE nombre_usuario = ?', (usuario,))
        cuenta = cursor.fetchone()
        cursor.close()
        conn.close()

        if cuenta and check_password_hash(cuenta['contraseña'], clave):
            user = Usuario(cuenta['id'], cuenta['nombre_usuario'])
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
    email = user_info.get("email")
    nombre = user_info.get("name")
    foto = user_info.get("picture")

    conn = get_db_connection()
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

    usuario_log = Usuario(cuenta['id'], cuenta['nombre_usuario'])
    login_user(usuario_log)
    migrar_carrito_sesion_a_db(usuario_log.id)
    return redirect(url_for("panel_usuario"))


# ══════════════════════════════════════════════════════════
# PANEL PRINCIPAL
# ══════════════════════════════════════════════════════════

@app.route('/panel_usuario')
@login_required
def panel_usuario():
    usuario_id = current_user.id
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT foto FROM usuarios WHERE id = ?', (usuario_id,))
    resultado = cursor.fetchone()
    foto = (
        resultado['foto']
        if resultado and resultado['foto']
        else "https://res.cloudinary.com/di9wdbb1z/image/upload/v1750640818/default_xm9gvv.jpg"
    )

    cursor.execute("""
        SELECT fecha, descripcion, valor, tipo FROM movimientos
        WHERE usuario_id = ? ORDER BY fecha DESC LIMIT 5
    """, (usuario_id,))
    ultimos_movimientos = cursor.fetchall()

    cursor.execute("""
        SELECT titulo, fecha_limite FROM tareas
        WHERE usuario_id = ? AND fecha_limite >= CURRENT_DATE
        ORDER BY fecha_limite ASC LIMIT 3
    """, (usuario_id,))
    tareas_pendientes = cursor.fetchall()

    cursor.execute("""
        SELECT COALESCE(SUM(valor), 0) AS total_ingresos
        FROM movimientos WHERE usuario_id = ? AND tipo = 'ingreso'
    """, (usuario_id,))
    total_ingresos = cursor.fetchone()['total_ingresos']

    cursor.execute("""
        SELECT COALESCE(SUM(valor), 0) AS total_gastos
        FROM movimientos WHERE usuario_id = ? AND tipo = 'gasto'
    """, (usuario_id,))
    total_gastos = cursor.fetchone()['total_gastos']

    cursor.execute("""
        SELECT COUNT(*) AS total_deudas_pendientes, SUM(saldo) AS saldo_deudas_pendientes
        FROM deudas WHERE usuario_id = ? AND estado = 'pendiente'
    """, (usuario_id,))
    deudas_pendientes = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS total_prestamos, SUM(saldo) AS saldo_prestamos
        FROM prestamos WHERE usuario_id = ?
    """, (usuario_id,))
    prestamos = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        'panel_usuario.html',
        usuario=current_user.nombre_usuario,
        usuario_foto=foto,
        ultimos_movimientos=ultimos_movimientos,
        tareas_pendientes=tareas_pendientes,
        total_ingresos=total_ingresos,
        total_gastos=total_gastos,
        deudas_pendientes=deudas_pendientes,
        prestamos=prestamos
    )


# ══════════════════════════════════════════════════════════
# TAREAS
# ══════════════════════════════════════════════════════════

@app.route('/tareas', methods=['GET', 'POST'])
@login_required
def tareas():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        titulo = request.form['titulo']
        fecha_limite = request.form.get('fecha_limite')
        lista_id = request.form.get('lista_id')
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
        conn = get_db_connection()
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
    tarea_id = request.form.get('id')
    nuevo_titulo = request.form.get('titulo')
    if not tarea_id or not nuevo_titulo:
        return redirect(url_for('tareas'))
    try:
        conn = get_db_connection()
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
    conn = get_db_connection()
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
    data = request.get_json()
    tarea_id = data.get('id')
    nuevo_lista_id = data.get('nuevo_lista_id')

    if not tarea_id or not nuevo_lista_id:
        return jsonify({'exito': False, 'error': 'Datos incompletos'})
    try:
        try:
            nuevo_lista_id = int(nuevo_lista_id)
        except (TypeError, ValueError):
            return jsonify({'exito': False, 'error': 'Lista inválida'})

        conn = get_db_connection()
        cursor = conn.cursor()
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
    tarea_id = request.form.get('id')
    nuevo_estado = request.form.get('estado')

    if not tarea_id or nuevo_estado not in ('pendiente', 'en progreso', 'completada'):
        return redirect(url_for('tareas'))
    try:
        conn = get_db_connection()
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
    id = request.form.get('id')
    color = request.form.get('color')
    if not id or not color:
        return redirect(url_for('tareas'))
    try:
        conn = get_db_connection()
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
    id = request.form.get('id')
    nombre = request.form.get('nombre')
    if not id or not nombre:
        return redirect(url_for('tareas'))
    try:
        conn = get_db_connection()
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM listas WHERE id = ? AND usuario_id = ?', (id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass
    return redirect(url_for('tareas'))


# ══════════════════════════════════════════════════════════
# MOVIMIENTOS
# ══════════════════════════════════════════════════════════


@app.route('/agenda', methods=['GET', 'POST'])
@login_required
def agenda():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if request.method == 'POST':
            titulo = (request.form.get('titulo') or '').strip()
            descripcion = (request.form.get('descripcion') or '').strip()
            fecha = (request.form.get('fecha') or '').strip()
            hora = (request.form.get('hora') or '').strip()

            if titulo and fecha:
                cursor.execute(
                    '''
                    INSERT INTO agenda (titulo, descripcion, fecha, hora, usuario_id)
                    VALUES (?, ?, ?, ?, ?)
                    ''',
                    (titulo, descripcion, fecha, hora, current_user.id)
                )
                conn.commit()
                flash('Actividad guardada correctamente.', 'success')
                return redirect(url_for('agenda'))
            else:
                flash('El título y la fecha son obligatorios.', 'error')

        cursor.execute(
            '''
            SELECT * FROM agenda
            WHERE usuario_id = ?
            ORDER BY fecha ASC, hora ASC
            ''',
            (current_user.id,)
        )
        eventos = cursor.fetchall()

        eventos_list = []
        eventos_futuros = []

        hoy = date.today()
        ahora = datetime.now()

        for evento in eventos:
            fecha_raw = evento['fecha']
            hora_raw = evento['hora']

            if hasattr(fecha_raw, 'isoformat'):
                fecha_str = fecha_raw.isoformat()
            else:
                fecha_str = str(fecha_raw) if fecha_raw else ''

            hora_str = str(hora_raw)[:5] if hora_raw else ''

            eventos_list.append({
                'id': evento['id'],
                'titulo': evento['titulo'],
                'descripcion': evento['descripcion'] or '',
                'fecha': fecha_str,
                'hora': hora_str
            })

            if fecha_str:
                try:
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()

                    if hora_str:
                        fecha_hora_evento = datetime.strptime(
                            f'{fecha_str} {hora_str}',
                            '%Y-%m-%d %H:%M'
                        )
                    else:
                        fecha_hora_evento = datetime.combine(fecha_obj, datetime.min.time())

                    if fecha_obj > hoy or (fecha_obj == hoy and fecha_hora_evento >= ahora):
                        eventos_futuros.append((fecha_hora_evento, evento))

                except ValueError:
                    pass

        eventos_futuros.sort(key=lambda x: x[0])
        eventos_urgentes = [evento for _, evento in eventos_futuros[:4]]

        clima = {
            'ciudad': 'Medellín',
            'temperatura': 24,
            'estado': 'Parcialmente nublado',
            'max': 27,
            'min': 18,
            'humedad': 72,
            'lluvia': 20,
            'icono': 'fa-cloud-sun'
        }

        return render_template(
            'agenda.html',
            eventos=eventos,
            eventos_urgentes=eventos_urgentes,
            eventos_json=json.dumps(eventos_list, ensure_ascii=False),
            usuario=current_user.nombre_usuario,
            clima=clima
        )

    except Exception as e:
        print(f'Error en agenda: {e}')
        flash('Ocurrió un error al cargar la agenda.', 'error')
        return redirect(url_for('agenda'))

    finally:
        cursor.close()
        conn.close()



@app.route('/eliminar_cita/<int:cita_id>')
@login_required
def eliminar_cita(cita_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            'DELETE FROM agenda WHERE id = %s AND usuario_id = %s',
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
    evento_id = request.form.get('id')
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion')
    fecha = request.form.get('fecha')
    hora = request.form.get('hora') or ''

    if evento_id and titulo and fecha:
        try:
            conn = get_db_connection()
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
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hoy = datetime.today()
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


@app.route('/movimientos', methods=['GET', 'POST'])
@login_required
def movimientos():
    usuario_id = current_user.id
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT foto FROM usuarios WHERE id = ?', (usuario_id,))
        resultado_foto = cursor.fetchone()
        usuario_foto = resultado_foto['foto'] if resultado_foto and resultado_foto['foto'] else None

        if request.method == 'POST':
            fecha = request.form['fecha']
            descripcion = request.form['descripcion']
            valor = Decimal(request.form['valor'])
            tipo = request.form['tipo']

            if tipo not in ['ingreso', 'gasto']:
                flash('Tipo de movimiento inválido', 'danger')
                return redirect(url_for('movimientos'))

            cursor.execute("""
                INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id)
                VALUES (?, ?, ?, ?, ?)
            """, (fecha, descripcion, valor, tipo, usuario_id))
            conn.commit()
            return redirect(url_for('movimientos'))

        cursor.execute("""
            SELECT COALESCE(SUM(
                CASE WHEN tipo = 'ingreso' THEN valor
                     WHEN tipo = 'gasto'   THEN -valor
                     ELSE 0 END
            ), 0) AS saldo
            FROM movimientos WHERE usuario_id = ?
        """, (usuario_id,))
        saldo_actual = cursor.fetchone()['saldo']

        return render_template(
            'movimientos.html',
            saldo_actual=saldo_actual,
            usuario=current_user.nombre_usuario,
            usuario_foto=usuario_foto
        )
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════════════
# FORMULARIO DE REGISTROS (ingreso / gasto / deuda / préstamo)
# ══════════════════════════════════════════════════════════

@app.route('/nuevo_registro', methods=['GET', 'POST'])
@login_required
def formulario_registros():
    form = RegistroUnicoForm()
    categoria_form = CategoriaForm()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM categorias WHERE usuario_id = ?", (current_user.id,))
    categorias = cursor.fetchall()
    form.categoria.choices = [(c[0], c[1]) for c in categorias]

    if request.method == 'POST' and form.validate_on_submit():
        tipo = form.tipo.data
        fecha = form.fecha.data
        frecuencia = form.frecuencia.data
        descripcion = form.descripcion.data
        valor = form.valor.data
        persona = form.persona.data
        categoria_id = form.categoria.data if tipo in ['ingreso', 'gasto'] else None
        usuario_id = current_user.id
        movimiento_id = None

        if tipo in ['ingreso', 'gasto']:
            if conn.is_postgres:
                cursor.execute("""
                    INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    RETURNING id
                """, (fecha, descripcion, valor, tipo, usuario_id, categoria_id))
                movimiento_id = cursor.fetchone()['id']
            else:
                cursor.execute("""
                    INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (fecha, descripcion, valor, tipo, usuario_id, categoria_id))
                movimiento_id = cursor.lastrowid
            conn.commit()

        if tipo == 'deuda':
            cursor.execute("""
                INSERT INTO deudas (
                    descripcion, persona, usuario_id, monto_inicial, saldo,
                    frecuencia, estado, fecha, fecha_creacion, tipo, movimiento_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (descripcion, persona, usuario_id, valor, valor,
                  frecuencia, 'pendiente', fecha, datetime.utcnow(), tipo, movimiento_id))
            conn.commit()

        elif tipo == 'prestamo':
            cursor.execute("""
                INSERT INTO prestamos (
                    descripcion, persona, usuario_id, monto_inicial, saldo,
                    frecuencia, estado, fecha, fecha_creacion, movimiento_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (descripcion, persona, usuario_id, valor, valor,
                  frecuencia, 'pendiente', fecha, datetime.utcnow(), movimiento_id))
            conn.commit()

        cursor.close()
        conn.close()
        return redirect(url_for('formulario_registros'))

    cursor.close()
    conn.close()
    return render_template('formulario_registros.html', form=form, categoria_form=categoria_form)


@app.route('/crear_categoria', methods=['POST'])
@login_required
def crear_categoria():
    form = CategoriaForm()
    if form.validate_on_submit():
        nombre = form.nombre.data
        usuario_id = current_user.id
        ahora = datetime.utcnow()

        conn = get_db_connection()
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
# REGISTROS (listado, abonos, exportación PDF)
# ══════════════════════════════════════════════════════════

@app.route('/registros')
@login_required
def registros():
    form = DummyForm()
    usuario_id = current_user.id
    mostrar_todo = request.args.get('ver_todo', '0') == '1'
    dias_mostrar = int(request.args.get('dias', 1)) if not mostrar_todo else 9999

    conn = get_db_connection()
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
            SELECT id, fecha, descripcion, monto_inicial, estado, saldo, tipo
            FROM deudas WHERE usuario_id = ? ORDER BY fecha DESC
        """, (usuario_id,))
        deudas = cursor.fetchall()

        hoy = date.today()
        limite_fecha = hoy - timedelta(days=dias_mostrar - 1)

        # Agrupar movimientos
        movimientos_agrupados = defaultdict(list)
        for m in movimientos_lista:
            fecha_obj = to_date(m['fecha'])
            if fecha_obj is None:
                continue
            if fecha_obj >= limite_fecha:
                movimientos_agrupados[formatear_fecha_humana(fecha_obj)].append(m)

        # Agrupar préstamos
        prestamos_agrupados = defaultdict(list)
        for p in prestamos:
            fecha_obj = to_date(p['fecha'])
            if fecha_obj is None:
                continue
            if fecha_obj >= limite_fecha:
                prestamos_agrupados[formatear_fecha_humana(fecha_obj)].append(p)

        # Agrupar deudas
        deudas_agrupadas = defaultdict(list)
        for d in deudas:
            fecha_obj = to_date(d['fecha'])
            if fecha_obj is None:
                continue
            if fecha_obj >= limite_fecha:
                deudas_agrupadas[formatear_fecha_humana(fecha_obj)].append(d)

        # FIX: usar to_date() para evitar AttributeError con strings de SQLite
        hay_mas_mov = any(
            to_date(m['fecha']) and to_date(m['fecha']) < limite_fecha
            for m in movimientos_lista
        )
        hay_mas_prest = any(
            to_date(p['fecha']) and to_date(p['fecha']) < limite_fecha
            for p in prestamos
        )

        seccion = request.args.get('seccion', 'ingresos')

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
    deuda_id = request.form.get('deuda_id')
    monto_abono_raw = request.form.get('monto_abono', '').strip()

    try:
        monto_abono = to_decimal(monto_abono_raw)
    except (InvalidOperation, ValueError):
        flash('El monto del abono no es válido.', 'danger')
        return redirect(url_for('registros', seccion='deudas'))

    if monto_abono <= 0:
        flash('El monto del abono debe ser mayor a 0.', 'danger')
        return redirect(url_for('registros', seccion='deudas'))

    conn = get_db_connection()
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
        nuevo_saldo = saldo_actual - monto_abono

        if nuevo_saldo <= 0:
            nuevo_saldo = Decimal('0')
            estado = 'pagado'
        else:
            estado = 'pendiente'

        descripcion_deuda = deuda['descripcion'] or f"Deuda ID {deuda_id}"

        cursor.execute("""
            INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
            VALUES (CURRENT_DATE, ?, ?, ?, ?, NULL)
        """, (
            f"Abono a deuda: {descripcion_deuda}",
            float(monto_abono),
            'abono_deuda',
            current_user.id
        ))

        cursor.execute("""
            UPDATE deudas SET saldo = ?, estado = ?
            WHERE id = ? AND usuario_id = ?
        """, (
            float(nuevo_saldo),
            estado,
            deuda_id,
            current_user.id
        ))

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
    prestamo_id = request.form.get('prestamo_id')
    monto_abono_raw = request.form.get('monto_abono', '').strip()

    try:
        monto_abono = to_decimal(monto_abono_raw)
    except (InvalidOperation, ValueError):
        flash('El monto del abono no es válido.', 'danger')
        return redirect(url_for('registros', seccion='prestamos'))

    if monto_abono <= 0:
        flash('El monto del abono debe ser mayor a 0.', 'danger')
        return redirect(url_for('registros', seccion='prestamos'))

    conn = get_db_connection()
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
        nuevo_saldo = saldo_actual - monto_abono

        if nuevo_saldo <= 0:
            nuevo_saldo = Decimal('0')
            estado = 'pagado'
        else:
            estado = 'pendiente'

        descripcion_prestamo = prestamo['descripcion'] or f"Préstamo ID {prestamo_id}"

        cursor.execute("""
            UPDATE prestamos SET saldo = ?, estado = ?
            WHERE id = ? AND usuario_id = ?
        """, (
            float(nuevo_saldo),
            estado,
            prestamo_id,
            current_user.id
        ))

        cursor.execute("""
            INSERT INTO movimientos (fecha, descripcion, valor, tipo, usuario_id, categoria_id)
            VALUES (CURRENT_DATE, ?, ?, ?, ?, NULL)
        """, (
            f"Abono recibido del préstamo: {descripcion_prestamo}",
            float(monto_abono),
            'abono_a_recibir',
            current_user.id
        ))

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
    ordenar = request.args.get('ordenar')
    seccion = request.args.get('seccion', 'deudas')
    usuario_id = current_user.id

    query = 'SELECT * FROM movimientos WHERE usuario_id = ?'
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
        'fecha_asc': ' ORDER BY fecha ASC',
        'fecha_desc': ' ORDER BY fecha DESC',
        'valor_asc': ' ORDER BY valor ASC',
        'valor_desc': ' ORDER BY valor DESC',
    }
    query += orden_map.get(ordenar, '')

    conn = get_db_connection()
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

    pdf_output = BytesIO()
    pisa_status = pisa.CreatePDF(rendered_html, dest=pdf_output)
    if pisa_status.err:
        return f"Error al generar PDF: {pisa_status.err}"

    pdf_output.seek(0)
    return send_file(pdf_output, as_attachment=True,
                     download_name='movimientos_filtrados.pdf',
                     mimetype='application/pdf')


@app.route('/certificado_prestamo/<int:movimiento_id>')
@login_required
def certificado_prestamo(movimiento_id):
    conn = get_db_connection()
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

    pdf_output = BytesIO()
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
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ═══════════════════════════════
        # Gráfica 1: Ingresos y Gastos
        # ═══════════════════════════════
        cursor.execute("""
            SELECT fecha,
                SUM(CASE WHEN tipo = 'ingreso' THEN valor ELSE 0 END) AS ingreso,
                SUM(CASE WHEN tipo = 'gasto'   THEN valor ELSE 0 END) AS gasto
            FROM movimientos
            WHERE usuario_id = ?
            GROUP BY fecha
            ORDER BY fecha
        """, (current_user.id,))
        movimientos_raw = cursor.fetchall()

        movimientos_data = [
            {
                'fecha': str(f[0])[:10],
                'ingreso': float(f[1] or 0),
                'gasto': float(f[2] or 0)
            }
            for f in movimientos_raw
        ]

        # ═══════════════════════════════
        # Gráfica 2: Deudas
        # ═══════════════════════════════
        cursor.execute("""
            SELECT persona, SUM(saldo) as total_saldo
            FROM deudas
            WHERE usuario_id = ?
            GROUP BY persona
        """, (current_user.id,))
        deudas = [
            {'persona': d[0], 'total_saldo': float(d[1] or 0)}
            for d in cursor.fetchall()
        ]

        # ═══════════════════════════════
        # Gráfica 3: Préstamos
        # ═══════════════════════════════
        cursor.execute("""
            SELECT persona, COUNT(*) as cantidad, SUM(monto_inicial) as monto_total
            FROM prestamos
            WHERE usuario_id = ?
            GROUP BY persona
        """, (current_user.id,))
        prestamos = [
            {
                'persona': p[0],
                'cantidad': int(p[1] or 0),
                'monto_total': float(p[2] or 0)
            }
            for p in cursor.fetchall()
        ]

        # ═══════════════════════════════
        # Gráfica 4: Tareas (FIX POSTGRES)
        # ═══════════════════════════════
        cursor.execute("""
            SELECT estado, COUNT(*) as cantidad
            FROM (
                SELECT
                    CASE
                        WHEN estado = 'completada' THEN 'completada'
                        WHEN fecha_limite IS NOT NULL AND fecha_limite < CURRENT_DATE THEN 'vencida'
                        ELSE COALESCE(estado, 'pendiente')
                    END AS estado
                FROM tareas
                WHERE usuario_id = ?
            ) sub
            GROUP BY estado
        """, (current_user.id,))
        tareas = [
            {'estado': t[0], 'cantidad': int(t[1] or 0)}
            for t in cursor.fetchall()
        ]

        return jsonify({
            'movimientos': movimientos_data,
            'deudas': deudas,
            'prestamos': prestamos,
            'tareas': tareas
        })

    except Exception as e:
        print("❌ Error en estadísticas:", e)
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()    


# ══════════════════════════════════════════════════════════
# CARTERA / PAGOS
# ══════════════════════════════════════════════════════════

def generar_url_wompi(monto, referencia):
    monto_centavos = int(Decimal(monto) * 100)
    return (
        f"https://checkout.wompi.co/p/"
        f"?public-key={os.environ['WOMPI_PUBLIC_KEY']}"
        f"&currency=COP&amount-in-cents={monto_centavos}"
        f"&reference={referencia}"
        f"&redirect-url=https://tusitio.com/confirmacion_wompi"
    )


@app.route('/cartera')
@login_required
def cartera():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT saldo_wallet FROM usuarios WHERE id=?", (current_user.id,))
    saldo = cur.fetchone()['saldo_wallet']
    cur.close()
    conn.close()
    # FIX: el template debe usar current_user.nombre_usuario, no session['usuario']
    return render_template('cartera.html', saldo=saldo)


@app.route('/iniciar_paypal', methods=['POST'])
@login_required
def iniciar_paypal():
    monto = request.form.get('monto')
    if not monto:
        flash("Monto faltante", "danger")
        return redirect(url_for('cartera'))

    transaccion_id = f"PAYPAL-{current_user.id}-{int(datetime.now().timestamp())}"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO recargas (usuario_id, metodo, transaccion_id, monto) VALUES (?, 'paypal', ?, ?)",
        (current_user.id, transaccion_id, monto)
    )
    conn.commit()
    cur.close()
    conn.close()

    return render_template('paypal_checkout.html', transaccion_id=transaccion_id, monto=monto)


@app.route('/procesar_pago_paypal', methods=['POST'])
@login_required
def procesar_pago_paypal():
    data = request.get_json()
    txid = data['orderID']
    monto = data['monto']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("UPDATE recargas SET estado='exitosa' WHERE transaccion_id=?", (txid,))
    cur.execute("""
        INSERT INTO wallet_movimientos
            (usuario_id, referencia_externa, monto, tipo, estado, descripcion, medio_pago)
        VALUES (?, ?, ?, 'recarga', 'completado', 'Recarga PayPal', 'paypal')
    """, (current_user.id, txid, monto))
    cur.execute(
        "UPDATE usuarios SET saldo_wallet = saldo_wallet + ? WHERE id = ?",
        (monto, current_user.id)
    )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify(status='ok')


@app.route('/iniciar_wompi', methods=['POST'])
@login_required
def iniciar_wompi():
    monto = Decimal(request.form.get('monto'))
    referencia = f"WOMPI-{current_user.id}-{int(datetime.utcnow().timestamp())}"
    url_pago = generar_url_wompi(monto, referencia)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO recargas (usuario_id, metodo, transaccion_id, monto) VALUES (?, 'wompi', ?, ?)",
        (current_user.id, referencia, monto)
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_pago)


@app.route('/webhook_wompi', methods=['POST'])
def webhook_wompi():
    tx = request.get_json()['data']['transaction']
    referencia = tx['reference']
    estado = tx['status']
    monto = Decimal(tx['amount_in_cents']) / 100

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE recargas SET estado=? WHERE transaccion_id=?",
        ('exitosa' if estado == 'APPROVED' else 'fallida', referencia)
    )
    if estado == 'APPROVED':
        cur.execute("""
            INSERT OR IGNORE INTO wallet_movimientos
                (usuario_id, referencia_externa, monto, tipo, estado, descripcion, medio_pago)
            SELECT usuario_id, transaccion_id, ?, 'recarga', 'completado', 'Recarga Wompi', 'wompi'
            FROM recargas WHERE transaccion_id=?
        """, (monto, referencia))
        cur.execute("""
            UPDATE usuarios SET saldo_wallet = saldo_wallet + ?
            WHERE id IN (SELECT usuario_id FROM recargas WHERE transaccion_id=?)
        """, (monto, referencia))
    conn.commit()
    cur.close()
    conn.close()
    return '', 200


@app.route('/confirmacion_wompi')
@login_required
def confirmacion_wompi():
    flash("Tu recarga ha sido procesada. Revisa tu saldo.", "success")
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

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if nombre:
            cursor.execute(
                'UPDATE usuarios SET nombre_usuario = ? WHERE id = ?',
                (nombre, current_user.id)
            )
        if email:
            cursor.execute(
                'UPDATE usuarios SET correo_electronico = ? WHERE id = ?',
                (email, current_user.id)
            )
        if telefono:
            cursor.execute(
                'UPDATE usuarios SET telefono = ? WHERE id = ?',
                (telefono, current_user.id)
            )
        if nueva_clave:
            clave_hash = generate_password_hash(nueva_clave)
            cursor.execute(
                'UPDATE usuarios SET contraseña = ? WHERE id = ?',
                (clave_hash, current_user.id)
            )
        if foto and foto.filename != '':
            try:
                resultado = cloudinary.uploader.upload(foto)
                url_foto = resultado.get('secure_url')
                cursor.execute(
                    'UPDATE usuarios SET foto = ? WHERE id = ?',
                    (url_foto, current_user.id)
                )
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
    # El context_processor inject_user_data ya provee usuario_foto y usuario
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
    producto = next((p for p in productos if p["nombre"] == nombre), None)
    if not producto:
        return "Producto no encontrado", 404
    return render_template("detalle_producto.html", producto=producto)


def obtener_carrito_usuario(usuario_id):
    conn = get_db_connection()
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
    conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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
def ideas():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        titulo = request.form["titulo"]
        descripcion = request.form["descripcion"]
        categoria = request.form.get("categoria", "")
        cursor.execute(
            "INSERT INTO ideas (titulo, descripcion, categoria) VALUES (?, ?, ?)",
            [titulo, descripcion, categoria]
        )
        conn.commit()
        flash("Idea registrada con éxito", "success")
        cursor.close()
        conn.close()
        return redirect(url_for("ideas"))

    cursor.execute("SELECT * FROM ideas ORDER BY fecha_creacion DESC")
    ideas_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("ideas.html", ideas=ideas_list)


@app.route("/eliminar_idea/<int:id>")
def eliminar_idea(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ideas WHERE id = ?", [id])
    conn.commit()
    cursor.close()
    conn.close()
    flash("Idea eliminada", "info")
    return redirect(url_for("ideas"))


@app.route("/editar_idea/<int:id>", methods=["GET", "POST"])
def editar_idea(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        titulo = request.form["titulo"]
        descripcion = request.form["descripcion"]
        categoria = request.form["categoria"]
        cursor.execute(
            "UPDATE ideas SET titulo = ?, descripcion = ?, categoria = ? WHERE id = ?",
            [titulo, descripcion, categoria, id]
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Idea actualizada", "success")
        return redirect(url_for("ideas"))

    cursor.execute("SELECT * FROM ideas WHERE id = ?", [id])
    idea = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template("editar_idea.html", idea=idea)


# ══════════════════════════════════════════════════════════
# ASISTENTE (Gemini)
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
            return jsonify({"error": str(e), "mensaje": f"❌ Error al procesar la imagen: {str(e)}"}), 500

    try:
        texto_respuesta = generar_respuesta_gemini(consulta_usuario, imagen_binaria, mime_type)
        return jsonify({"mensaje": texto_respuesta})
    except Exception as e:
        return jsonify({"error": str(e), "mensaje": f"❌ Error al procesar la consulta: {str(e)}"}), 500


@app.route('/gemini_status')
@login_required
def gemini_status():
    return jsonify({
        "enabled": model is not None,
        "message": "Gemini está configurado." if model is not None else "Gemini no está disponible. Verifica GEMINI_API_KEY."
    })


# ══════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════

if __name__ == '__main__':
    app.run(debug=True, port=5000)