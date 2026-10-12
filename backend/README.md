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
  "grupo_etario": "1-4"
}
```

Valores permitidos para registros nuevos: `Menores de 1`, `1-4`, `5-14`,
`15-64` y `65+`. `grupo_etario` es obligatorio; no se asigna un valor por
defecto. El ejemplo representa 12 casos de personas entre 1 y 4 años, no
la edad de un paciente individual. Los casos respiratorios no pueden ser
negativos. El backend toma
el usuario creador desde el JWT, por lo que el cliente no envía ese dato.

## Historial de ingresos

`GET /api/ingresos` requiere autenticación y admite filtros opcionales:

```text
/api/ingresos?establecimiento_id=1&fecha_desde=2026-10-01&fecha_hasta=2026-10-31&grupo_etario=1-4&skip=0&limit=50
```

La respuesta incluye `total`, `skip`, `limit` e `items`. `limit` tiene un máximo
de 100.

El historial conserva y permite filtrar también las categorías antiguas:
`Infantil`, `Adulto`, `Adulto Mayor` y `General`. Estas ya no se aceptan al
crear registros. Los casos antiguos no se reparten automáticamente entre
los nuevos rangos, porque no se conocen sus edades exactas.

En una base existente, el CHECK de `public.ingresos_diarios.age_group` debe
admitir los cinco rangos nuevos y las cuatro categorías históricas. Ese
cambio se realiza manualmente en PostgreSQL. Los cambios del modelo Python
solo se aplican automáticamente al crear una tabla nueva: `create_all()`
no modifica restricciones de tablas existentes.

## Clima y contaminación: Open-Meteo

`GET /api/clima` requiere autenticación y dos coordenadas. Ejemplo para Santiago:

```text
/api/clima?latitud=-33.4489&longitud=-70.6693
```

En Swagger (`http://127.0.0.1:8000/docs`), use `Authorize` con las credenciales
de un usuario registrado; Swagger obtiene y envía el JWT. En la sección
`Clima y contaminación`, abra `GET /api/clima`, pulse `Try it out`, ingrese
las coordenadas y pulse `Execute`.

La API consulta dos servicios públicos:

- Pronóstico: `https://api.open-meteo.com/v1/forecast`.
- Calidad del aire: `https://air-quality-api.open-meteo.com/v1/air-quality`.

Solicita `forecast_hours=96`, combina los valores por fecha/hora y devuelve
`latitud`, `longitud`, `zona_horaria`, `horas_pronosticadas`, `fuente` y
`pronostico_horario`. Cada hora incluye temperatura (°C), humedad (%),
precipitación (mm), viento (km/h), PM10/PM2.5/ozono (µg/m³) e índice US AQI.
Los horarios se expresan como hora local de `America/Santiago`; los valores
ausentes del proveedor se conservan como `null`, no se convierten en cero.

Es información de pronóstico de modelos meteorológicos y de calidad del aire,
no mediciones de una estación hospitalaria ni predicciones de pacientes.
US AQI es el índice estadounidense, no una clasificación normativa chilena.

La implementación se organiza en:

- `app/api/climate.py`: endpoint, coordenadas válidas, autenticación y errores HTTP.
- `app/services/open_meteo.py`: solicitudes HTTP y combinación de datos externos.
- `app/schemas/climate.py`: formato y validación de la respuesta JSON.
- `app/main.py`: registro del router con el prefijo `/api`.

No requiere cambiar PostgreSQL, instalar dependencias adicionales ni configurar
una API key para probar el servicio público. No guarda los datos en la base.
Se debe conservar la atribución a Open-Meteo y CAMS cuando se muestren datos
de calidad del aire; revisar los términos para otros usos:
[pronóstico](https://open-meteo.com/en/docs),
[calidad del aire](https://open-meteo.com/en/docs/air-quality-api).

Errores: `401` sin token válido, `422` por coordenadas inválidas, `502` por
errores/respuestas incompletas del proveedor y `504` por tiempo de espera.
Cada solicitud externa tiene un timeout de 10 segundos. Se realizan dos
solicitudes consecutivas, por lo que la consulta completa puede tomar unos
20 segundos si hay demoras de conexión.

Para ejecutar las pruebas locales sin consultar Open-Meteo ni PostgreSQL:

```powershell
python -m unittest discover -s tests -v
```
