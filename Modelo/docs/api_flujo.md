# Flujo de la API: datos en tiempo real → predicción

Documento para Backend & Database Lead.

## Diagrama de flujo

```mermaid
flowchart TD
    FE[Frontend: dashboard 96h] -->|POST /predict| API[FastAPI]
    API --> HIST[(PostgreSQL: clima histórico)]
    API --> WX[Open-Meteo API<br/>temp min/max, precipitación]
    API --> AQ[Open-Meteo Air Quality<br/>MP2.5, MP10]
    API --> ENC[(Encoders exportados<br/>región, tipo, categoría)]
    HIST --> FEAT[Módulo de features<br/>lags 4d/2d + rolling 7d + flags]
    WX --> FEAT
    AQ --> FEAT
    ENC --> FEAT
    FEAT --> MODEL[model_rf_respiratorio_v1.joblib]
    MODEL -->|pacientes predichos| API
    API -->|JSON| FE
    API -->|guarda predicción| DB[(PostgreSQL: predicciones)]
```

## Paso a paso

### 1. Recepción de la solicitud
- El frontend envía `Region`, `IdEstablecimiento` y la fecha objetivo.
- La API valida con Pydantic.

### 2. Datos climáticos en tiempo real
- Consulta a Open-Meteo (temperatura mínima/máxima, precipitación) por región y fecha.
- Consulta a Open-Meteo Air Quality (MP2.5, MP10) por región y fecha.

### 3. Histórico necesario (requisito del modelo)
El modelo NO predice solo con el dato del día. Necesita ventanas previas:

| Feature | Ventana requerida |
|---|---|
| `TempMin_Lag_4D` | temperatura mínima de hace 4 días |
| `MP2_5_Lag_2D` | MP2.5 de hace 2 días |
| `Region_Media_7d_TempMin` | media de los últimos 7 días |
| `Region_Media_7d_MP25` | media de los últimos 7 días |

El backend debe:
- Mantener una tabla `clima_diario` (region, fecha, temp_min, temp_max, precipitacion_mm, mp2_5, mp10) que se actualice con la API al iniciar cada día.
- Consultar esa tabla para armar las ventanas, o pedirle a la API de clima la última semana completa.

### 4. Feature engineering
Replicar en el backend la misma lógica del pipeline (`src/pipelines/feature_engineering.py`):
- Flags: `Frio_Polar_Flag` (≤2°C), `Lluvia_Intensa_Flag` (percentil 90 regional), `Alerta_MP25_Flag` (>15 μg/m³).
- Discretización de temperatura: `Cat_TempMin` (Muy Frío, Frío, Templado, Cálido, Caluroso).
- Encodings de región, tipo de establecimiento y categoría de temperatura.

### 5. Inferencia
- Cargar `model_rf_respiratorio_v1.joblib` una sola vez al arrancar el servicio.
- Ordenar las columnas EXACTAMENTE como `features.json`.
- Llamar `model.predict(X)` y devolver el resultado redondeado a entero.

### 6. Salida
- Devolver al frontend: `pacientes_predichos`, fecha, establecimiento y nivel de alerta.
- Guardar la predicción en `predicciones` (establecimiento, fecha, valor, fecha_hora_prediccion).

## Tablas sugeridas en PostgreSQL

```sql
-- Clima diario por región (alimenta lags y rolling)
CREATE TABLE clima_diario (
    region TEXT NOT NULL,
    fecha DATE NOT NULL,
    temp_min NUMERIC,
    temp_max NUMERIC,
    precipitacion_mm NUMERIC,
    mp2_5 NUMERIC,
    mp10 NUMERIC,
    PRIMARY KEY (region, fecha)
);

-- Predicciones emitidas
CREATE TABLE predicciones (
    id SERIAL PRIMARY KEY,
    id_establecimiento TEXT NOT NULL,
    fecha DATE NOT NULL,
    pacientes_predichos INTEGER NOT NULL,
    fecha_hora_prediccion TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Encoders (exportados en `encoders.joblib`)

El diccionario de traducción texto → número está en `Modelo/artifacts/encoders.joblib`:

- `temp_order`: mapeo ordinal de `Cat_TempMin` (Muy Frío=0 … Caluroso=4).
- `le_region`: `LabelEncoder` de las 8 regiones del modelo.
- `le_tipo`: `LabelEncoder` de los 5 tipos de establecimiento (CEAR, Hospital, SAPU, SAR, SUR).

Uso en el backend:

```python
enc = joblib.load("artifacts/encoders.joblib")
region_enc = enc["le_region"].transform([region])[0]
tipo_enc = enc["le_tipo"].transform([tipo])[0]
cat_enc = enc["temp_order"].get(cat_temp, -1)
```

**Ojo**: las clases de los encoders son fijas (las del entrenamiento). Si llega una
región o tipo desconocido, hay que manejarlo con un valor de fallback (por ejemplo -1).
