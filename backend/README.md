# Backend: guía de desarrollo local

## Iniciar la API

Desde la carpeta `backend`, instala las dependencias y levanta FastAPI:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

La documentación interactiva estará disponible en:

```text
http://127.0.0.1:8000/docs
```

## Usuario de prueba

Cada integrante usa su propia base de datos local. Después de iniciar la API,
cree este usuario desde `POST /api/auth/register` en Swagger:

```json
{
  "email": "demo@hospital.local",
  "password": "DemoHospital2026!",
  "full_name": "Usuario Demo"
}
```

Después puede iniciar sesión con `POST /api/auth/login`:

```text
username: demo@hospital.local
password: DemoHospital2026!
```

Estas credenciales son solo para desarrollo. No se deben usar datos personales,
usuarios reales ni contraseñas reales en este repositorio.

## Configuración

Copie `.env.example` como `.env` y complete las credenciales de su PostgreSQL
local antes de iniciar la API.
