# Feature: v6 — Mejora del modelo a nivel establecimiento

## Objetivo
Mejorar las predicciones a nivel ESTABLECIMIENTO respecto al v5 commiteado,
a través de pruebas iterativas con datos. Cuando un modelo muestre buenos
resultados, ese pasará a ser la versión v6 oficial.

## Problema / por qué
El v5 (dos etapas) logra R² 0.85 a nivel REGIÓN pero solo 0.14–0.33 a nivel
establecimiento. Causa raíz identificada: la Etapa 2 es `total_region ×
cuota_fija_2024` — no aprende nada específico del establecimiento el día que
predice (sin demanda reciente, sin tipo, sin saturación).

## Alcance
- Mantener el v5 commiteado intacto (no se modifica).
- Todo experimento nuevo vive en scripts `reentrenar_modelo_v6_*.py`.
- Evaluación SIEMPRE a nivel establecimiento+día, test 2025.
- Horizonte de predicción: 96h → lags de demanda disponibles hasta T-4.

## Hipótesis a testear (con datos, en este orden)
1. **Descomposición de error**: ¿cuánto del error de establecimiento viene de
   la Etapa 1 (región), cuánto de la Etapa 2 (cuota) y cuánto es ruido propio
   del establecimiento?
2. **Techo con Etapa 1 perfecta**: usar región REAL × cuota 2024 → qué
   MAE/R² se logra. Mide el techo de la arquitectura actual.
3. **Cuota dinámica**: cuota trailing (últimos N días) vs cuota fija 2024.
4. **Lags de demanda**: señal de la demanda propia del establecimiento a
   lag 4 (96h) — ¿explica varianza más allá de la cuota?
5. Con los resultados: elegir el eje de mejora e implementar v6.

## Checklist de tareas
- [x] T1: Documento odd/tasks creado (este archivo) + espejo en Engram
- [x] T2: Diagnóstico de descomposición de error del v5 (script + resultados)
- [x] T3: Test de cuota dinámica (trailing) vs cuota fija 2024
- [x] T4: Test de señal de lags de demanda a nivel establecimiento (lag 4)
- [x] T5: Decidir eje de mejora con los datos de T2-T4
- [x] T6: Implementar scripts v6 (E1: cuota trailing end-to-end; E2: modelo directo estab)
- [x] T7: Evaluar v6 vs v5 (MAE, R², sesgo) — ¿mejora real?
- [x] T8: Adoptar E2 como v6 oficial → documentación (docs v6 + scripts/meta copiados al repo GitHub; joblib 45.6MB ignorado en .gitignore, se regenera con el script)
- [x] T10 (extra): Ablation E3 temperatura absolutas vs categóricas — evidencia para defensa
- [x] T11 (extra): E3 copiada al repo GitHub (script + metadata + sección en model_evolution.md)
- [x] T12 (extra): Demo notebook actualizado a v6 — sección 5 nueva (features, métricas, scatter, series, mini-caso), ejecutado sin errores, métricas idénticas a oficiales

Nota: el commit/push del repo no es una tarea del proyecto — está fuera del
alcance de esta feature (repo listo: 5 modificados + 8 nuevos).

## Criterios de aceptación
- Toda mejora medida a nivel establecimiento+día sobre test 2025, comparable
  con v5 (MAE 14.763 / R² 0.141) y con la mejor exploratoria (MAE 12.784 /
  R² 0.3277).
- Sin data leakage: lags de demanda ≤ T-4, cuotas calculadas solo con train.
- v5 commiteado intacto.

## Restricciones
- Idioma de artefactos técnicos: español (convención del proyecto).
- Commits/push: fuera del alcance de estas tareas.
- TDD: no aplica (scripts de experimentación, sin test runner configurado
  para ML — verificado: no hay framework de testing en el repo).

## Progreso
- [x] T1 completado
- [x] T2–T4 completados (script `src/pipelines/diagnostico_v6_descomposicion.py`,
  salida `models/diagnostico_v6_t2.json`)
- [x] T5 completado (decisión abajo)
- [x] T6 completado (E1 y E2 implementados y ejecutados)
- [x] T7 completado (E2 = mejor de toda la serie)
- [x] T8 completado (documentación v6 en repo GitHub + evidencia copiada)
- Sin tareas pendientes: T1–T8 y extras T10–T12 completos.

## Verificación (RDD on)
- Verificación de los writers: ambos experimentos ejecutados y reportados (comandos observados).
- Spot check del orquestador: re-ejecución de E2 reproduce métricas exactas.
- Revisión nativa (gentle-ai): NO DISPONIBLE — el git root de "Proyecto de título"
  apunta al home (~761k archivos sin trackear, supera el límite de 8MB de
  `ls-files`); STATUS y assess fallan con `invalid_request`. No es defecto del
  proveedor, es estado del repositorio.
- Verificación INDEPENDIENTE (worker fresh, read-only): **PASS** — reproducibilidad,
  anti-leakage (reimplementación independiente del lag: 229.528 filas, 100%
  coincidencia; Total_Lag_4==Total(T−4) en 219.995/219.995), split limpio,
  integridad v5/E1 por SHA-256, granularidad correcta.
- Warnings preexistentes (afectan igual a v2-v5, comparabilidad intacta):
  `TempMin_Lag_4D` y `MP2_5_Lag_2D` usan shift sobre FILAS (~97.8%/98.9%
  == mismo día; no cumplen su semántica de lag), `Lluvia_Intensa_Flag`
  (percentil 90 transductivo train+test), `Pred_Region` in-sample en train
  (documentado, sin fuga a test).

## Evidencia T6–T7: experimentos E1 y E2 (test 2025, nivel estab+día)

| Versión | MAE | RMSE | R² | Sesgo % |
|---|---|---|---|---|
| v5 (dos etapas, cuota fija) — referencia | 14.7633 | 22.9807 | 0.1410 | +21.01 |
| E1 (dos etapas, cuota trailing, denominador regional) | 13.8083 | 22.2623 | 0.1939 | +21.73 |
| Exploratoria post-hoc (sin cont + Anom_TempMin) | 12.7845 | 20.3300 | 0.3277 | +11.32 |
| **E2 (modelo directo estab)** | **9.3338** | **13.0481** | **0.7231** | **+9.77** |

- **E2 gana en las 4 métricas** vs v5 (MAE −36%, R² ×5.1) y vs la exploratoria.
- E2 features (27): `Total_Lag_4`, `Share_Trailing`, `Pred_Region`, `Pred_E1`,
  one-hot Tipo+Región, `Doy/Doy_Sin/Doy_Cos`, 7 climáticas (sin contaminación).
- Importancias top: Pred_E1 (0.311), Total_Lag_4 (0.304), Share_Trailing (0.113)
  → el modelo aprendió a corregir el sistema dos-etapas con demanda reciente.
- Anti-leakage verificado en script: Total_Lag_4 == Total(T−4) en 219.995/219.995
  filas; correlación Total_Lag_4 vs Total = 0.8016; sanity R² < 0.9.
- Por región: Maule 0.83 / Arica 0.81 / Metropolitana 0.70 / Magallanes 0.66 /
  Antofagasta 0.63 / O'Higgins 0.54 / Coquimbo 0.48 / **Atacama −0.03 (único
  débil: región nueva sin 2024)**.
- Bug de diseño documentado en E1: renormalizar cuota entre SOLO reportantes
  del día → 1.42% filas = 44.5% SSE; fix = denominador con TODOS los estabs
  de la región → 5.9% SSE.
- Artefactos: `models/model_metadata_v6e2.json`, `models/model_rf_directo_v6e2.joblib`,
  `models/model_metadata_v6e1.json`, `src/pipelines/reentrenar_modelo_v6_e1_trailing.py`,
  `src/pipelines/reentrenar_modelo_v6_e2_directo.py`.
- Control: pipeline E1 con cuota fija reproduce v5 EXACTAMENTE (14.7633/22.9807/0.141/21.01).

## Evidencia T10 (extra): ablation E3 — temperatura absolutas vs categóricas
Script: `src/pipelines/reentrenar_modelo_v6_e3_ablation_temp.py` →
`models/model_metadata_v6e3_ablation_temp.json`. Control A reproduce E2 exacto.

| Config | MAE | RMSE | R² | Sesgo |
|---|---|---|---|---|
| A — Absolutas (control E2) | 9.3338 | 13.0481 | 0.7231 | +9.77% |
| B — Categóricas one-hot (bins clínicos) | 9.3390 | 12.9860 | 0.7257 | +9.62% |
| C — Categóricas ordinal 0..4 (estilo v1) | 9.2869 | 13.0398 | 0.7234 | +9.42% |

Veredicto: **equivalencia estadística** (|ΔMAE| ≤ 0.5%, |ΔR²| ≤ 0.003; ninguna
codificación domina). Las absolutas se justifican por granularidad y no perder
información (los bins colapsan rangos: 0 filas "Caluroso" en TempMin_Lag_4D y
Region_Media_7d_TempMin), NO por mayor accuracy. Evidencia documental para la
defensa del cambio v1→v6.

## Evidencia / resultados (T2–T4, test 2025, nivel estab+día)

| Configuración | MAE | R² | Nota |
|---|---|---|---|
| C: v5 reportado (referencia) | 14.763 | 0.141 | metadata v5 |
| A: share × total regional real 2024 (MM-DD) | 10.403 | 0.411 | solo 6 regiones con train |
| B: share × total regional REAL (techo Etapa 1 perfecta) | 8.383 | 0.756 | sesgo 0.0% |
| D: cuota trailing 30d (shift 4) × total regional REAL | **6.952** | **0.836** | sesgo 0.0% |
| Persistencia pura (pred = Total lag 4) | 11.074 | 0.584 | sin ningún modelo |

Descomposición del error de v5 (14.763 → 8.383 → 6.952):
- **Etapa 1 (predicción regional) ≈ 6.4 MAE** del error: es la mayor fuente.
- **Cuota fija vs trailing ≈ 1.4 MAE** (−17%): la cuota trailing gana incluso
  con región perfecta; en Antofagasta/Atacama (sin cuota 2024) gana el doble
  (B 13.29 → D 6.37).
- Variabilidad diaria regional aporta ~2 MAE (A 10.403 → B 8.383).

T4 (lags de demanda): correlación parcial residuo-B vs lag4 = 0.284
(señal existe), pero ΔR² sobre D = 0.000 → **la cuota trailing ya absorbe
la señal del lag 4**; agregar lag4 como feature del share es redundante.
Persistencia pura (R² 0.584, MAE 11.07) es MEJOR que v5 → la demanda
reciente es el predictor más fuerte disponible a T-4.

Suelo de ruido: std(Total) dentro de región+fecha ≈ 19.98 (mediana 17.94).

## T5: Decisión de eje (con datos)
Ejecutar DOS experimentos (ambos con artefactos propios `reentrenar_modelo_v6_*.py`):
1. **E1 — v5 end-to-end con cuota trailing**: cambio mínimo en Etapa 2
   (evidencia T3: −1.4 MAE en techo, enorme en regiones sin histórico).
2. **E2 — modelo directo a nivel establecimiento**: features propias del
   estab (lag4, share trailing, tipo, doy, clima regional, pred región Etapa 1)
   → ataca la propagación del error de Etapa 1, que es la mayor fuente (6.4 MAE).

Comparar ambos contra v5 (14.763 / 0.141) y exploratoria (12.784 / 0.3277).

## Ruta elegida (por task)
- T1: inline (documento mecánico)
- T2–T4: inline (un script de diagnóstico, diseño previo hecho)
- T5: decisión del orquestador con los datos de T2–T4
- T6–T7: delegado (writer por experimento, un archivo cada uno)
