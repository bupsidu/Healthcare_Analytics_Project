# Backend: guía de desarrollo local

## Requisitos previos

- Python 3.11 o superior para las dependencias ML. El entrenamiento usó 3.13.6;
  se recomienda Python 3.13 para reproducir ese entorno. Esta integración
  también se probó localmente con Python 3.14 y las versiones ML fijadas.
- PostgreSQL en ejecución.
- Una base de datos creada, por ejemplo `hospital_db`.

## Configuración e inicio

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


## Clima y contaminación: Open-Meteo

`GET /api/clima` requiere autenticación y dos coordenadas.

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

## Predicción ML: MVP con variables precalculadas

`POST /api/predict` integra el RandomForest de Ignacio publicado en el
[release modelo-v1](https://github.com/bupsidu/Healthcare_Analytics_Project/releases/tag/modelo-v1).
Recibe las 20 variables ya calculadas, exige JWT y devuelve una estimación
redondeada de pacientes, un semáforo y un mensaje operativo de demostración.
No consulta ingresos ni Open-Meteo y no guarda predicciones en PostgreSQL.
No recibe establecimiento ni fecha objetivo: el horizonte depende de la
preparación de las variables, y este MVP no verifica una anticipación de 96h.

### Preparar y ejecutar desde PowerShell

Desde la carpeta `backend` (no hace falta activar el entorno virtual):

```powershell
# Solo si todavía no existe backend/.venv:
python -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/download_model.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

El script descarga y verifica estos archivos en `Modelo/artifacts/`:

```text
features.json
model_metadata.json
model_rf_respiratorio.joblib
```

Verifica el SHA-256 publicado antes de colocar el modelo en su ubicación
definitiva. Si ya están todos los archivos, comprueba su integridad y no los
descarga otra vez. Si hay archivos parciales o distintos, solicita revisarlos
en lugar de sobrescribirlos. Esta carpeta ya está excluida de Git; el binario
de unos 83 MB no debe añadirse al commit.

La ruta es configurable con `ML_ARTIFACTS_DIR` en `backend/.env`. Por defecto
usa `Modelo/artifacts` en la raíz del repositorio; una ruta relativa se
interpreta respecto de `backend`. Si usa otra ubicación:

```powershell
.\.venv\Scripts\python.exe scripts/download_model.py --directory "C:/ruta/artifacts"
```

Configure `ML_ARTIFACTS_DIR` con esa misma ubicación y reinicie FastAPI.
El modelo se carga una sola vez por proceso durante el inicio, no en cada
petición. Se verifican hash, tamaño, versiones ML, nombres y orden de las
features antes de habilitar inferencia. Los artefactos deben proceder del
release de confianza del equipo; no se cargan archivos enviados por clientes.

### Probar en Swagger

1. Abra `http://127.0.0.1:8000/docs`.
2. Use `Authorize` con las credenciales de un usuario registrado.
3. Abra `POST /api/predict`, pulse `Try it out` y use este ejemplo sintético:

   ```json
   {
     "Menores_1": 8,
     "De_1_a_4": 15,
     "De_5_a_14": 12,
     "De_15_a_64": 25,
     "De_65_y_mas": 18,
     "TempMin": 1.5,
     "TempMax": 14.2,
     "Precipitacion_mm": 5.0,
     "MP2_5": 28.5,
     "MP10": 55.0,
     "TempMin_Lag_4D": 0.8,
     "MP2_5_Lag_2D": 32.0,
     "Frio_Polar_Flag": 1,
     "Lluvia_Intensa_Flag": 0,
     "Alerta_MP25_Flag": 1,
     "Cat_TempMin_Encoded": 1,
     "Region_Media_7d_TempMin": 2.1,
     "Region_Media_7d_MP25": 25.4,
     "Region_Encoded": 0,
     "TipoEstablecimiento_Encoded": 0
   }
   ```

4. Pulse `Execute`: debe responder `200`. El ejemplo probado con el release
   verificado devolvió 67 pacientes; es una prueba técnica, no una validación
   de precisión ni una predicción sobre un hospital real.

La respuesta incluye `pacientes_predichos`, `nivel_alerta`, `color_semaforo`,
`recomendacion`, `alerta_demostracion: true` y `version_modelo: modelo-v1`.
Se redondea la salida del modelo y se limita su mínimo a cero. Las alertas
son las propuestas en la guía: menos de 15 verde, de 15 a 29 amarillo y
desde 30 rojo. Son umbrales de demostración; no miden saturación, capacidad
de camas ni demanda pediátrica, y no constituyen indicaciones clínicas.

Los 20 campos son obligatorios. No se sustituyen datos ausentes por cero.
Se rechazan cantidades negativas, banderas distintas de 0/1, valores no
finitos, campos desconocidos y temperaturas mínima/máxima invertidas.
El orden de claves del JSON no importa: el servicio construye un DataFrame
con las columnas ordenadas exactamente como `features.json`.

