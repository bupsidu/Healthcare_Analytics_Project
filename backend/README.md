# Backend: guía de desarrollo local

## Requisitos previos

- Python 3.10 o superior.
- PostgreSQL en ejecución.
- Una base de datos creada, por ejemplo `hospital_db`.

## Configuración e inicio

Desde la carpeta `backend`, copie `.env.example` como `.env` y configure las
credenciales de su PostgreSQL.

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
(Este es un ejemplo para crear un usuario, puedes cambiar lo que quieras por comodidad)
Luego inicie sesión con `POST /api/auth/login`:

Una vez hehco el usuario debe ingresar sesion dentro de la api para poder acceder a mas opciones.
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

La respuesta incluye `total`, `skip`, `limit` e `items`. `limit` tiene un máximo
de 100.

## Columnas de PostgreSQL en inglés

Los nombres de las tablas siguen siendo `usuarios`, `establecimientos` e
`ingresos_diarios`. Los campos JSON y filtros de la API siguen en español,
al igual que los valores del grupo etario. Los modelos mapean estos atributos
a las columnas SQL en inglés para conservar compatibilidad con el frontend.

| Tabla | Nombre anterior de columna | Nombre actual |
|---|---|---|
| establecimientos | nombre | name |
| establecimientos | comuna | commune |
| establecimientos | capacidad_camas | bed_capacity |
| ingresos_diarios | fecha | date |
| ingresos_diarios | establecimiento_id | establishment_id |
| ingresos_diarios | casos_respiratorios | respiratory_cases |
| ingresos_diarios | grupo_etario | age_group |

Para actualizar una base existente:

1. Detenga FastAPI con `Ctrl+C` en su terminal.
2. En pgAdmin, seleccione la misma base configurada en `backend/.env` y abra
   `Query Tool`.
3. Abra [sql/rename_columns_to_english.sql](sql/rename_columns_to_english.sql)
   y ejecute todo el bloque, desde `BEGIN` hasta `COMMIT`, una sola vez.
4. Si aparece un error, ejecute `ROLLBACK;` antes de continuar y revise el
   mensaje. No vuelva a ejecutar un script que ya terminó correctamente.
5. Actualice la vista de tablas en pgAdmin con `Refresh`.
6. Compruebe los nombres con la siguiente consulta:

```sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('usuarios', 'establecimientos', 'ingresos_diarios')
ORDER BY table_name, ordinal_position;
```

El script sólo renombra columnas; conserva los registros y sus relaciones.
PostgreSQL actualiza las referencias de las restricciones e índices, aunque
sus nombres puedan seguir en español. Las columnas de `usuarios` ya estaban
en inglés y no requieren cambios.

Una base nueva usa las columnas en inglés automáticamente al iniciar FastAPI;
no ejecute el script sobre ella. `create_all()` no renombra columnas existentes.

Para reiniciar la API, desde `backend`:

```powershell
python -m uvicorn app.main:app --reload
```

Pruebe en Swagger el registro y el historial usando los campos JSON de los
ejemplos anteriores. Para consultar establecimientos directamente en SQL use:

```sql
SELECT id, name, commune, region, bed_capacity
FROM public.establecimientos
ORDER BY id;
```
