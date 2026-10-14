# Reporte del modelo — v6 (versión actual)

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

## Arquitectura — modelo directo a nivel establecimiento
v6 reemplaza la cadena de dos etapas (Etapa 1 región → Etapa 2 cuota) por un
**único `RandomForestRegressor` entrenado directamente sobre filas
(establecimiento, fecha)** con target `Total` en nivel.

**Por qué se abandona la arquitectura de dos etapas** (diagnóstico T2–T4, ver
`model_evolution.md`): la Etapa 1 concentraba ~6.4 MAE del error de v5 y su
error se propagaba íntegro a cada establecimiento; además, la persistencia pura
(`pred = Total_Lag_4`, MAE 11.074 / R² 0.584) ya le ganaba a v5. El modelo
directo no elimina las señales regionales: las usa como **features** y aprende a
corregirlas con la demanda reciente del propio establecimiento.

**27 features:**
1. **Núcleo (4):** `Total_Lag_4` (demanda propia a T−4, calendario),
   `Share_Trailing` (cuota dinámica E1), `Pred_Region` (total regional
   predicho por la Etapa 1 de v5) y `Pred_E1 = Share_Trailing × Pred_Region`
   (el sistema dos-etapas completo como feature a corregir).
2. **One-hot de `TipoEstablecimiento`** (5) y **one-hot de región** (8).
3. **Estacionalidad:** `Doy`, `Doy_Sin`, `Doy_Cos`.
4. **Clima regional del día T sin contaminación** (7): `TempMin`, `TempMax`,
   `Precipitacion_mm`, `TempMin_Lag_4D`, `Region_Media_7d_TempMin`,
   `Frio_Polar_Flag`, `Lluvia_Intensa_Flag`.

Mismos hiperparámetros y semilla que v5 (`n_estimators=200`, `max_depth=15`,
`min_samples_split=50`, `min_samples_leaf=20`, `max_features="sqrt"`,
`random_state=42`) para que el delta aisle el efecto de la **arquitectura**, no
el del tuner.

## Resultados (test 2025, nivel establecimiento + día)
| Versión | MAE | RMSE | R² | Sesgo |
|---------|-----|------|-----|-------|
| v5 (dos etapas, cuota fija) | 14.763 | 22.981 | 0.141 | +21.01% |
| v6 E1 (dos etapas, cuota trailing) | 13.808 | 22.262 | 0.1939 | +21.73% |
| Exploratoria post-hoc (sin contam. + `Anom_TempMin`) | 12.785 | 20.330 | 0.3277 | +11.32% |
| **v6 E2 (modelo directo — actual)** | **9.334** | **13.048** | **0.7231** | **+9.77%** |

E2 gana en las 4 métricas frente a v5 (MAE −36%, R² ×5.1) y también frente a
la mejor exploratoria. Importancias top: `Pred_E1` 0.311, `Total_Lag_4` 0.304,
`Share_Trailing` 0.113 — el modelo aprendió a **corregir** el sistema
dos-etapas usando la demanda reciente.

**Por región (R²):** Maule 0.83 · Arica 0.81 · Metropolitana 0.70 ·
Magallanes 0.66 · Antofagasta 0.63 · O'Higgins 0.54 · Coquimbo 0.48 ·
**Atacama −0.03** (sesgo +64.8%). Atacama es región nueva sin train 2024,
igual que Antofagasta — pero Antofagasta sí responde (0.63), así que el caso
merece un análisis propio: ver `model_evolution.md`.

## Verificación anti-leakage
- `Total_Lag_4` coincide con `Total(T−4)` en **219.995 / 219.995** filas con
  historial comparable; se construye con `shift(4)` sobre calendario **antes**
  de unir con el target, por construcción no lee `Total(e, T)`.
- El target no está entre las features; correlación `Total_Lag_4` vs `Total` =
  0.8016 (no sospechosa); sanity-check automático: R² de test > 0.9 se marca
  como fuga — observado **0.7231**.
- Verificación independiente **PASS**; v5 intacto (SHA-256 verificado).

## Supuestos
- **Clima del día T como pronóstico:** las variables climáticas de la fecha T
  se asumen disponibles al momento de pronosticar T (variables exógenas de
  pronóstico, mismo supuesto que v1–v5). No es fuga del target.
- **`Pred_Region` in-sample en train:** en las filas de 2024 es la predicción
  in-sample de la Etapa 1 (mismo modelo que la usa en test). No es fuga del
  target del establecimiento (es un total regional agregado), pero es una
  feature más "limpia" en train que en test: documentado como limitación.
- Solo 2 años de datos: el delta se mide sobre el mismo split, no es
  validación externa.

## Evidencia incluida (`artifacts/`)
- `model_metadata_v6e2.json` — métricas, features, verificación anti-leakage,
  comparativa y limitaciones de E2.
- `model_metadata_v6e1.json` — configuración de la cuota trailing, control que
  reproduce v5 exactamente y el bug de normalización corregido.
- `diagnostico_v6_t2.json` — descomposición de error T2–T4 (techos y techo de
  ruido).
- `model_rf_region_v5.joblib`, `model_metadata_v5.json`,
  `cuotas_establecimiento_v5.csv`, `features_region_v5.json`,
  `encoders.joblib` — evidencia de v5, preservada.
- **No se versiona** `model_rf_directo_v6e2.joblib` (45.6 MB): está en
  `.gitignore` junto a los joblibs pesados de v1/v2 y se **regenera** con
  `src/pipelines/reentrenar_modelo_v6_e2_directo.py`.
- Scripts de evidencia en `src/pipelines/`: `diagnostico_v6_descomposicion.py`,
  `reentrenar_modelo_v6_e1_trailing.py`, `reentrenar_modelo_v6_e2_directo.py`
  (referencian rutas relativas del entorno de trabajo de experimentos, igual
  que v2–v5: se guardan como evidencia reproducible).

## Historial
Las versiones v1→v5, los experimentos de la v6 (diagnóstico, E1, E2), sus
problemas (incluido el *data leakage* de v1) y cómo se corrigieron están
documentados en [`model_evolution.md`](model_evolution.md), incluida la tabla
completa de versiones.

> **Advertencia sobre v1:** el primer modelo reportaba R² 0.9956 porque usaba
> los rangos etarios como features y `Total` es exactamente su suma (*data
> leakage*). Esos números son artificiales y fueron descartados. No citarlos
> como resultado.
