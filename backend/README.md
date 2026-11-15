# Backend hospitalario

API REST con FastAPI, PostgreSQL, autenticación JWT, Open-Meteo y modelo ML.

## Ejecutar localmente

Requisitos: PostgreSQL en ejecución, una base creada (por ejemplo,
`hospital_db`) y Python; se recomienda 3.13 para reproducir el entorno ML.

En Mac, siga la sección [Puesta en marcha desde cero en Mac](#puesta-en-marcha-desde-cero-en-mac).

Desde la raíz del proyecto, en PowerShell:

```powershell
cd backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/download_model.py
```

Antes de iniciar, edite `.env`: configure `POSTGRES_*`, una `SECRET_KEY`
aleatoria privada y `SEED_ADMIN_PASSWORD` (la clave del admin de prueba, mínimo
8 caracteres). No suba este archivo a Git. Los artefactos se descargan
y verifican en `Modelo/artifacts/`; tampoco se versionan en Git.

### Tablas, columnas y datos de prueba (solo desarrollo)

Cada persona tiene su propia base local. `create_all()` no agrega columnas a tablas que ya
existían; `scripts/seed_dev.py` sí las agrega. Tiene tres modos:

```powershell
.\.venv\Scripts\python.exe scripts/seed_dev.py --solo-esquema   # solo tablas y columnas que falten, sin datos
.\.venv\Scripts\python.exe scripts/seed_dev.py --solo-admin     # lo anterior + solo el administrador
.\.venv\Scripts\python.exe scripts/seed_dev.py                  # lo anterior + hospitales y médicos de prueba
```

Los dos primeros no crean hospitales: sin hospitales cargados por otro medio, un médico no
tiene a dónde pertenecer y no hay dashboard por hospital. El tercero (completo) hace lo siguiente:

Actualiza el esquema y crea 8 hospitales reales que conoce el modelo v6 (uno por región, con su código
DEIS), el administrador `adminbot@adminhospitalario.cl` (clave: `SEED_ADMIN_PASSWORD`) y un
médico por hospital (`medico3@hospitalhurtado.cl`, `medico4@...`, `medico6@...` a
`medico11@...`; clave de prueba `123456789`). Se puede repetir sin duplicar ni pisar lo
existente, y se niega a correr contra un servidor que no sea local (salvo
`--force`). **No es para producción.**

Para llenar `clima_diario` con el pronóstico de Open-Meteo de las 8 regiones
(repetible, idealmente una vez al día):

```powershell
.\.venv\Scripts\python.exe scripts/load_climate.py
```

Para probar el dashboard sin datos reales, `scripts/seed_demo.py` inventa la demanda
diaria y los casos por grupo etario de los últimos 5 días en esos 8 hospitales (cifras
ficticias; no pisa lo existente). `--borrar` los elimina:

```powershell
.\.venv\Scripts\python.exe scripts/seed_demo.py
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Swagger: **http://127.0.0.1:8000/docs** (encendido por defecto; con `ENABLE_DOCS=false`
en `backend/.env`, `/docs` responde 404; hágalo antes de publicar la API en internet).
Use **Authorize** con el correo de uno de los usuarios de prueba como `username` y su
contraseña para obtener el JWT. Las cuentas nuevas se crean con `POST /api/auth/register`
(abierto, pero la cuenta queda **inactiva** hasta que un administrador la active) o
directamente un administrador con `POST /api/usuarios`.

## Puesta en marcha desde cero en Mac

Todo es local: cada persona tiene su propia base PostgreSQL. Esta guía no se ha
probado todavía en un Mac; si algún paso falla, anote el error y avise.

1. **Instalar** Python 3.13, Node y PostgreSQL (por ejemplo Postgres.app o
   `brew install postgresql`). Compruebe que PostgreSQL está en ejecución.
2. **Crear la base vacía:** `createdb hospital_db`.
3. **Configurar el backend**, desde la carpeta `backend`:

   ```bash
   cp .env.example .env
   ```

   Edite `.env`: `POSTGRES_USER` y `POSTGRES_PASSWORD` (en Postgres.app el usuario
   suele ser el de su Mac y la clave puede ir vacía), una `SECRET_KEY` propia,
   y `SEED_ADMIN_PASSWORD` (mínimo 8 caracteres).
4. **Instalar dependencias y el modelo:**

   ```bash
   python3.13 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python scripts/download_model.py
   ```

   El modelo se descarga de un release de GitHub. Si la descarga falla (por
   ejemplo, por permisos), pida el archivo `model_rf_directo_v6e2.joblib` y déjelo
   en `Modelo/artifacts/`.
5. **Crear las tablas, el administrador y los hospitales y médicos de prueba**, y cargar el
   clima (para otros modos, como solo el esquema, ver "Tablas, columnas y datos de prueba"):

   ```bash
   .venv/bin/python scripts/seed_dev.py
   .venv/bin/python scripts/load_climate.py
   ```

   Opcional, para ver el dashboard con cifras (inventadas, últimos 5 días):

   ```bash
   .venv/bin/python scripts/seed_demo.py
   ```
6. **Levantar la API:**

   ```bash
   .venv/bin/python -m uvicorn app.main:app --reload
   ```

   Compruebe `http://127.0.0.1:8000/api/healthcheck`. Para entrar: correo
   `medico3@hospitalhurtado.cl`, clave `123456789`.
7. **Levantar el front**, desde la carpeta `frontend`: `cp .env.example .env`, poner
   `VITE_API_URL=http://localhost:8000/api` (sin `/v1`), `npm install` y `npm run dev`
   (abre `http://localhost:5173`, el origen que la API permite por defecto).

Esa base queda con hospitales, usuarios y clima; la demanda solo existe si corrió `seed_demo.py`.

## Actualizar un proyecto ya instalado

Después de un `git pull`, la base local puede no tener las columnas nuevas. `scripts/seed_dev.py`
las agrega sin borrar datos (en Windows, `.\.venv\Scripts\python.exe` en lugar de `.venv/bin/python`).
Desde la carpeta `backend`:

1. Si falta, agregue `SEED_ADMIN_PASSWORD=` (8 o más caracteres) al `.env`. El `git pull` no lo toca.
2. **Antes de levantar la API**, actualice la base:

   ```bash
   .venv/bin/python scripts/seed_dev.py
   ```

   Si solo quiere las tablas y columnas, sin hospitales ni usuarios de prueba, agregue `--solo-esquema`.
3. Cargue el clima y, si quiere cifras de prueba, la demanda:

   ```bash
   .venv/bin/python scripts/load_climate.py
   .venv/bin/python scripts/seed_demo.py
   ```
4. Reinicie la API. En `frontend/.env`, `VITE_API_URL` debe ser `http://localhost:8000/api` (sin `/v1`).

El seed **agrega** lo que falte pero no borra hospitales ni usuarios de versiones anteriores: una base
que ya tenía los de prueba antiguos (códigos `99-001`, `99-002` y `16-803`) los conserva junto a los reales.
Para entrar con un médico de prueba, use por ejemplo `medico3@hospitalhurtado.cl` (clave `123456789`).

## Quitar `mp2_5` y `mp10` de `clima_diario` (solo si ya las tiene)

La contaminación (MP2.5 y MP10) **ya no se guarda en la base**: solo se muestra en la ruta de clima y en
la proyección. Una versión anterior del seed agregaba esas dos columnas a `clima_diario`.

- **Si nunca corrió esa versión del seed** (su `clima_diario` tiene solo `region`, `fecha`, `temp_min`,
  `temp_max` y `precipitacion_mm`): no tiene que hacer nada. `seed_dev.py` ya no las agrega.
- **Si ya las tiene:** dejarlas no rompe nada (la API las ignora), pero quedan obsoletas. Para quitarlas,
  desde la carpeta `backend` y con la API apagada, el mismo comando sirve en cualquier equipo, porque usa
  el Python del entorno virtual y no necesita `psql`. Se puede repetir sin riesgo:

  Mac o Linux:

  ```bash
  .venv/bin/python -c "from sqlalchemy import text; from app.db.session import engine; c = engine.connect(); c.execute(text('ALTER TABLE clima_diario DROP COLUMN IF EXISTS mp2_5, DROP COLUMN IF EXISTS mp10')); c.commit()"
  ```

  Windows (PowerShell):

  ```powershell
  .\.venv\Scripts\python.exe -c "from sqlalchemy import text; from app.db.session import engine; c = engine.connect(); c.execute(text('ALTER TABLE clima_diario DROP COLUMN IF EXISTS mp2_5, DROP COLUMN IF EXISTS mp10')); c.commit()"
  ```

  Alternativa con `psql`, si lo tiene a mano. En Mac con Homebrew funciona directo; en Windows suele hacer
  falta indicar la ruta de `psql.exe` y el usuario (`-U postgres`):

  ```bash
  psql hospital_db -c "ALTER TABLE clima_diario DROP COLUMN IF EXISTS mp2_5, DROP COLUMN IF EXISTS mp10;"
  ```

Esto borra solo valores de contaminación que se pueden volver a pedir a Open-Meteo.

## Endpoints principales

Salvo login, `/` y `/api/healthcheck`, las rutas requieren JWT.

| Área | Rutas |
|---|---|
| Autenticación | `POST /api/auth/login`, `GET /api/auth/me` (incluye rol y hospital), `POST /api/auth/register` (abierto: crea un médico inactivo, con el hospital deducido del dominio del correo; no acepta rol ni hospital) |
| Usuarios (solo admin) | `POST /api/usuarios`, `GET /api/usuarios`, `PATCH /api/usuarios/{id}` |
| Ingresos por grupo etario | `POST /api/ingresos`, `GET /api/ingresos` |
| Establecimientos | `GET /api/establecimientos` (filtros `activo`, `tipo`), `PATCH /api/establecimientos/{id}` (solo admin) |
| Demanda observada diaria | `PUT /api/demanda-diaria`, `GET /api/demanda-diaria` |
| Pronóstico Open-Meteo | `GET /api/establecimientos/{id}/clima` (clima de la región del hospital, y guarda el resumen diario en `clima_diario`; el médico solo el suyo), `GET /api/clima?latitud=&longitud=` (solo admin) |
| Clima almacenado | `PUT /api/clima/diario`, `GET /api/clima/historial` |
| Proyección 96 h del hospital | `GET /api/predict/proyeccion-96h` (médico: su hospital; admin: `?establecimiento_id=`). Entrega los días completos de las 96 h que consulta a Open-Meteo (normalmente 3, de mañana en adelante): clima, MP2.5/MP10, `total_lag_4` y `pacientes_predichos` por día. **La predicción es provisoria** (`prediccion_provisoria: true`): usa una cuota fija y `Pred_Region = Total_Lag_4 / cuota`, y no se guarda. Un día sin demanda cargada 4 días antes queda en `null` |
| Inferencia ML (modelo v6) | `POST /api/predict` (entradas manuales; solo pruebas) |
| Predicciones almacenadas | `GET /api/predicciones/historial` |

## Roles y hospitales

- Hay dos roles: **admin** (ve todos los hospitales, crea y administra usuarios,
  edita el catálogo y carga clima diario) y **medico** (solo ve y carga datos de
  su propio hospital). Cualquier otro rol se rechaza (también en la base, con
  una restricción `CHECK`).
- Cada hospital guarda su `dominio_correo` (por ejemplo `sapuhospital.cl`, con
  punto). Al crear un médico, su hospital se deduce del `@` del correo; si el
  dominio lo comparten varios centros, el admin indica `establecimiento_id` a mano.
- Un médico sin hospital, o con su hospital desactivado, recibe 403 en las rutas
  de datos. Acceder a datos de otro hospital también da 403.
- `PATCH /api/usuarios/{id}` permite desactivar o reactivar una cuenta (mejor que
  borrarla: la base no deja borrar a quien registró ingresos), reasignar su
  hospital y cambiar su contraseña. Un admin no puede desactivarse a sí mismo.
- El dominio del correo no prueba por sí solo que alguien sea funcionario: por eso quien
  se registra en `/api/auth/register` queda inactivo, y la seguridad depende de que el
  admin apruebe bien cada alta (`PATCH /api/usuarios/{id}` con `is_active: true`). El
  registro abierto no tiene límite de intentos todavía.

## Alcance y pendientes

- PostgreSQL contiene usuarios, establecimientos, ingresos, demanda diaria,
  clima diario y predicciones. `create_all()` no migra tablas existentes.
- Los ingresos usan el ID numérico; demanda y predicciones usan el código
  DEIS. Complete el catálogo con códigos y tipos reales.
- Los `PUT` diarios reemplazan la fila, no suman valores. El PUT climático
  deja en `NULL` los valores omitidos. No hay carga automática desde DEIS.
- El clima del modelo es regional. `GET /api/establecimientos/{id}/clima` consulta Open-Meteo en un punto fijo por región (su capital, `REGION_COORDS`) y guarda en `clima_diario` el resumen (mín, máx y lluvia) de cada día completo del pronóstico, reemplazando lo que hubiera para ese día. La contaminación (MP2.5 y MP10) no se guarda: solo se muestra, en la ruta de clima y en la proyección. Responde 409 si la región no tiene punto de consulta.
- `POST /api/predict` usa el modelo **v6 E2** (`modelo-v6-e2`, 27 variables).
  El backend deriva Pred_E1, estacionalidad, one-hot de región y tipo, y
  `Frio_Polar_Flag` (temp_min ≤ 2 °C). Quien consulta aporta `fecha`, `region`,
  `tipo_establecimiento`, `total_lag_4`, `share_trailing`, `pred_region`, el clima
  (`temp_min`, `temp_max`, `precipitacion_mm`, `temp_min_lag_4d`,
  `region_media_7d_temp_min`) y `lluvia_intensa` (precipitación sobre el p90 regional).
  Si se envía `id_establecimiento` (código DEIS existente) la predicción se guarda
  en `predicciones` (una por establecimiento, fecha y versión); si no existe → 404.
  No verifica anticipación de 96 h y el semáforo es demostrativo.
- La proyección de 96 h usa entradas **provisorias** (`app/services/provisional_inputs.py`):
  cuota fija de `cuotas_establecimiento_v5.csv` (si el código no figura, mediana de su región),
  `Pred_Region = Total_Lag_4 / cuota`, la temperatura mínima del propio día como lags de
  temperatura (así se comportó el entrenamiento) y 5 mm como umbral de lluvia intensa. Se
  reemplazan cuando ML defina las reales.
- Pendientes: cálculo automático de `total_lag_4`, `share_trailing` y `pred_region`
  desde la base (requiere historial de demanda y contaminación y el modelo regional
  de v5), el primer administrador en una instalación real (hoy solo existe el
  seed de desarrollo; falta definir el procedimiento con el equipo), Docker y
  despliegue en la nube.

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

