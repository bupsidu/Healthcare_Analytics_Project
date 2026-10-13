# Reporte del modelo — v5 (versión actual)

## Objetivo
Predecir la demanda diaria en urgencias respiratorias por establecimiento, con
96 horas (4 días) de anticipación.

## Datos
- Entrenamiento: 2024
- Prueba: 2025 (split temporal, nunca se mezclan años)
- Regiones: 8
- Establecimientos: 339
- Evaluación a nivel **establecimiento + día** (el dataset DEIS tiene ~4 filas
  por establecimiento+fecha, una por causa respiratoria; la demanda real es la
  suma).

## Arquitectura — dos etapas
El clima es a nivel **región** (idéntico para todos los establecimientos de una
misma región+fecha), por lo que un modelo directo no puede distinguirlos. Se
divide el problema según la jerarquía de los datos:

1. **Etapa 1 (región):** `RandomForest` predice el total diario de la región.
   Features: clima, anomalías de contaminación con baseline *trailing*,
   estacionalidad cíclica (`Doy_Sin`/`Doy_Cos`) y one-hot de región.
2. **Etapa 2 (establecimiento):** el total regional se reparte por **cuota
   histórica** (share) de cada establecimiento calculada sobre train 2024.
   Estabilidad verificada: correlación 0.993 entre 2024 y 2025 (297
   establecimientos comunes).

## Resultados (test 2025)
| Nivel | MAE | R² | Sesgo |
|-------|-----|-----|-------|
| Región (Etapa 1) | 467.4 | 0.8545 | — |
| Establecimiento + día (sistema completo) | 14.763 | 0.141 | +21.0% |

## Sobre la contaminación
La contaminación **no mejora** el modelo con 2 años de datos. Correlaciona con
la demanda *dentro* de un año porque ambas suben en invierno, pero esa señal es
en gran parte un proxy de la estación, que ya se modela explícitamente. La
**temperatura** (como anomalía `Anom_TempMin`) sí aporta señal incremental. Ver
`model_evolution.md` para el análisis completo.

## Evidencia incluida (`artifacts/`)
- `model_rf_region_v5.joblib` — modelo Etapa 1 (región)
- `cuotas_establecimiento_v5.csv` — cuotas Etapa 2
- `features_region_v5.json` — lista de features
- `model_metadata_v5.json` — métricas, hiperparámetros y comparaciones
- `encoders.joblib` — codificadores de región/tipo/orden temporal

## Historial
Las versiones v1→v4, sus problemas (incluido el *data leakage* de v1) y cómo
se corrigieron están documentados en [`model_evolution.md`](model_evolution.md).

> **Advertencia sobre v1:** el primer modelo reportaba R² 0.9956 porque usaba
> los rangos etarios como features y `Total` es exactamente su suma (*data
> leakage*). Esos números son artificiales y fueron descartados. No citarlos
> como resultado.
