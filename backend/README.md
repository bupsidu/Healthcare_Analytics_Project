# Backend hospitalario

API REST con FastAPI, PostgreSQL, autenticación JWT, Open-Meteo y modelo ML.

## Ejecutar localmente

Requisitos: PostgreSQL en ejecución, una base creada (por ejemplo,
`hospital_db`) y Python; se recomienda 3.13 para reproducir el entorno ML.

En Mac (Terminal) los comandos equivalentes son: `cp .env.example .env`,
`python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`
y `.venv/bin/python -m uvicorn app.main:app --reload`.

Desde la raíz del proyecto, en PowerShell:

```powershell
cd backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/download_model.py
```

Antes de iniciar, edite `.env`: configure `POSTGRES_*` y una `SECRET_KEY`
aleatoria privada. No suba este archivo a Git. Los artefactos se descargan
y verifican en `Modelo/artifacts/`; tampoco se versionan en Git.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Swagger: **http://127.0.0.1:8000/docs**.
Cree una cuenta con `POST /api/auth/register` y use **Authorize**
con el correo como `username` y su contraseña para obtener el JWT.

## Endpoints principales

Salvo registro, login, `/` y `/api/healthcheck`, las rutas requieren JWT.

| Área | Rutas |
|---|---|
| Autenticación | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| Ingresos por grupo etario | `POST /api/ingresos`, `GET /api/ingresos` |
| Establecimientos | `GET /api/establecimientos`, `PATCH /api/establecimientos/{id}` |
| Demanda observada diaria | `PUT /api/demanda-diaria`, `GET /api/demanda-diaria` |
| Pronóstico Open-Meteo | `GET /api/clima` |
| Clima almacenado | `PUT /api/clima/diario`, `GET /api/clima/historial` |
| Inferencia ML (modelo v6) | `POST /api/predict` |
| Predicciones almacenadas | `GET /api/predicciones/historial` |

## Alcance y pendientes

- PostgreSQL contiene usuarios, establecimientos, ingresos, demanda diaria,
  clima diario y predicciones. `create_all()` no migra tablas existentes.
- Los ingresos usan el ID numérico; demanda y predicciones usan el código
  DEIS. Complete el catálogo con códigos y tipos reales.
- Los `PUT` diarios reemplazan la fila, no suman valores. El PUT climático
  deja en `NULL` los valores omitidos. No hay carga automática desde DEIS.
- `GET /api/clima` devuelve 96 horas de pronóstico, sin guardarlo.
- `POST /api/predict` usa el modelo **v6 E2** (`modelo-v6-e2`, 27 variables).
  El backend deriva Pred_E1, estacionalidad, one-hot de región y tipo, y
  `Frio_Polar_Flag` (temp_min ≤ 2 °C). Quien consulta aporta `fecha`, `region`,
  `tipo_establecimiento`, `total_lag_4`, `share_trailing`, `pred_region`, el clima
  (`temp_min`, `temp_max`, `precipitacion_mm`, `temp_min_lag_4d`,
  `region_media_7d_temp_min`) y `lluvia_intensa` (precipitación sobre el p90 regional).
  Si se envía `id_establecimiento` (código DEIS existente) la predicción se guarda
  en `predicciones` (una por establecimiento, fecha y versión); si no existe → 404.
  No verifica anticipación de 96 h y el semáforo es demostrativo.
- Pendientes: cálculo automático de `total_lag_4`, `share_trailing` y `pred_region`
  desde la base (requiere historial de demanda y contaminación y el modelo regional
  de v5), permisos por rol/hospital, Docker y despliegue en la nube.

## Pruebas y documentación

Desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas usan recursos temporales y servicios simulados, no validan el
PostgreSQL real ni la precisión del modelo.

- [Documentación del modelo ML](../Modelo/docs/model_report.md).
- [Flujo propuesto para la integración automática](../Modelo/docs/api_flujo.md)
  (diseño futuro, no describe todo como implementado).

