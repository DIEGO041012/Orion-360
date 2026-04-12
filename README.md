# Orion 360

Aplicación Flask para gestión personal con tareas, agenda, finanzas y asistente.

## Despliegue en Render

1. Crear un repositorio Git en tu cuenta.
2. Subir este proyecto al repositorio.
3. En Render, crear un nuevo servicio web apuntando al repo.
4. Usar `render.yaml` para la configuración del servicio.

## Variables de entorno necesarias

- `SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `DATABASE_URL`
- `GEMINI_API_KEY`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `OAUTHLIB_INSECURE_TRANSPORT=1`

## Neon / PostgreSQL

Usa `DATABASE_URL` con la cadena de conexión de Neon. Por ejemplo:

```env
DATABASE_URL=postgres://usuario:contraseña@host:puerto/nombre_de_base
```

Si estás usando Neon, no necesitas definir `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` ni `POSTGRES_PORT` en Render.

## Comandos de arranque

Render usará:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

## Notas

- Actualmente la app usa SQLite local (`orion.db`), que en Render no es persistente.
- Para producción, se recomienda usar PostgreSQL o una base de datos externa.
- Render debería usar Python 3.12 para este proyecto; en `render.yaml` ya se puso `pythonVersion: 3.12.14`.
# Orion-360
