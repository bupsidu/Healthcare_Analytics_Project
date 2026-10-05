# Backend: guía de desarrollo local

## Requisitos previos

- Python 3.10 o superior.
- PostgreSQL en ejecución.
- Una base de datos creada, por ejemplo `hospital_db`.

## Configuración e inicio

Desde la carpeta `backend`, copie `.env.example` como `.env` y configure las
credenciales de su PostgreSQL. No suba `.env` al repositorio.

Instale dependencias y levante FastAPI:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

La documentación interactiva estará disponible en:

```text
http://127.0.0.1:8000/docs
```

## Usuario de prueba

Después de iniciar la API, cree un usuario desde `POST /api/auth/register` en
Swagger:

```json
{
  "email": "demo@hospital.local",
  "password": "DemoHospital2026!",
  "full_name": "Usuario Demo"
}
```

Luego inicie sesión con `POST /api/auth/login`:

```text
username: demo@hospital.local
password: DemoHospital2026!
```

Copie el token recibido y use `Authorize` en Swagger con:

```text
Bearer TU_TOKEN
```

Los endpoints de ingresos requieren ese token.

## Registrar un ingreso respiratorio

Antes de registrar ingresos debe existir un establecimiento en la base de
datos. El endpoint actual de establecimientos aún no está implementado, por
lo que en desarrollo se puede crear uno directamente en PostgreSQL.

Use `POST /api/ingresos` con este cuerpo:

```json
{
  "fecha": "2026-10-02",
  "establecimiento_id": 1,
  "casos_respiratorios": 12,
  "grupo_etario": "Infantil"
}
```

Valores permitidos para `grupo_etario`: `Infantil`, `Adulto`, `Adulto Mayor` y
`General`. Los casos respiratorios no pueden ser negativos. El backend toma
el usuario creador desde el JWT, por lo que el cliente no envía ese dato.

## Historial de ingresos

`GET /api/ingresos` requiere autenticación y admite filtros opcionales:

```text
/api/ingresos?establecimiento_id=1&fecha_desde=2026-10-01&fecha_hasta=2026-10-31&grupo_etario=Infantil&skip=0&limit=50
```

`limit` tiene máximo 100. La respuesta incluye `total`, `skip`, `limit` e
`items`.
