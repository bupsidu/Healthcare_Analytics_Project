# Tarea: Fix de bugs de features climáticas (base del modelo)

> **Feature:** `fix-features-clima` · **Estado:** en progreso · **Creado:** 2026-11-11
> **Ruta elegida:** delegated direct (trigger: 2+ archivos no triviales — fix de `feature_engineering.py` + script de reentrenamiento v7)

## Objetivo

Corregir los 3 bugs de features climáticas diagnosticados en el ciclo v6, regenerar
`df_modelo.parquet`, reentrenar y revalidar contra el baseline oficial v6 (E2),
dejando una base confiable antes de encarar Mejora 1 / habilitador 2022-2023.

## Problema (causa raíz verificada)

`data/interim/df_unificado.parquet` tiene **~152 filas por (Región, Fecha)** (mín 4, máx 604).
Las features se calculaban con operaciones sobre **filas**, no sobre **calendario**:

| Bug | Código actual | Evidencia | Efecto |
|-----|---------------|-----------|--------|
| `TempMin_Lag_4D` (y `MP2_5_Lag_2D`) | `groupby(Region).shift(4)` sobre filas | 97.8% de valores == `TempMin` mismo día | No es un lag de 4 días: es (casi) duplicado de `TempMin` |
| `Region_Media_7d_TempMin` (y `_MP25`) | `rolling(window=7)` sobre filas | 7 filas ≪ 1 día de datos (152 filas/día) | No es media de 7 días: es ruido de sub-día |
| `Lluvia_Intensa_Flag` | percentil 90 por región sobre **todo** el df | umbral calculado incluyendo test 2025 | Transductivo (data snooping) |

Archivo afectado: `src/pipelines/feature_engineering.py` (L96-110, L145-155, L211-222).
Los pipelines v5/E2/E1/E3 y el demo consumen `data/processed/df_modelo.parquet`,
que fue generado por este script → el parquet se debe **regenerar**.

## Por qué

- Defensa técnica: no podés presentar un modelo con features que sabés que no miden lo que dicen.
- Base sólida: cualquier mejora futura (etario, 2022-2023) construiría sobre features corruptas.
- Usuario eligió esta dirección explícitamente (2026-11-11) antes que Mejora 1 o datos nuevos.

## Alcance

**Dentro:**
1. Fix de los 3 bugs en `feature_engineering.py` (incluye `MP2_5_Lag_2D` y `Region_Media_7d_MP25`,
   mismos patrones — fuera del E2 pero en el mismo código).
2. Regeneración de `df_modelo.parquet`.
3. Diagnóstico post-fix (verificación de corrección calendárica).
4. Reentrenamiento E2 como **v7** con artefactos nuevos (release v6 queda congelado).
5. Comparación honesta de métricas v6 vs v7.
6. Sincronización al repo + docs + demo (sección nueva, sin tocar la sección 5 del v6).

**Fuera (conocido y documentado, no se toca):**
- `fillna(median)` transductivo en `filter_and_clean` (medias calculadas sobre todo el df).
  Candidato a fix en un ciclo siguiente.
- Mejoras 1-3 y datos 2022-2023 (roadmap `PROJECT_CONTEXT.md`).
- Commits/push: los hace Ignacio con GitHub Desktop (regla de proyecto).

## Decisiones de diseño

- **Fix de lags/rolling:** deduplicar a serie (Región, Fecha) con 1 fila por fecha, ordenar por
  fecha, aplicar `shift`/`rolling` ahí, y hacer merge de vuelta al df multi-fila. Verificación:
  el valor resultante debe ser igual al de la fecha calendario T−4 (no T−0).
- **Fix de `Lluvia_Intensa_Flag`:** umbral = percentil 90 por región calculado **solo sobre el
  período de train** (`Fecha < 2025-01-01`, protocolo train 2024 / test 2025), congelado y
  aplicado a todas las filas.
- **Versionado:** nueva versión **v7** (`model_rf_directo_v7.joblib`,
  `model_metadata_v7.json`, script `reentrenar_modelo_v7_features_fix.py`). No se pisa
  ningún artefacto del release `modelo-v6-e2`.
- **Regla de aceptación de métricas:** si v7 mejora o empatan → v7 es el nuevo oficial.
  Si v7 empeora materialmente → STOP y preguntar al usuario (decisión de producto: corrección
  vs. métrica publicada).

## Checklist de tareas

- [x] **T1** Fix de `feature_engineering.py` (lags calendárico, rolling calendárico,
      percentil train-only) + docstrings. — evidencia: `python3 src/pipelines/feature_engineering.py`
      → OK; 3 bugs corregidos (lags/rolling sobre serie calendario deduplicada con merge por
      (Región, Fecha); q90 de lluvia con `TRAIN_END=2025-01-01`) y docstrings de módulo/funciones
      actualizados; nombres de columnas sin cambios.
- [x] **T2** Regenerar `df_modelo.parquet` (esperar ~9-10k filas menos por dropna de los
      primeros 4 días calendario por región). — evidencia: `python3 src/pipelines/feature_engineering.py`
      → OK, **889.524 filas × 27 columnas** (viejo: 894.652; delta **-5.128**, NO -9-10k: la
      estimación del doc no considera que el lag calendárico reintegra filas que el lag viejo
      descartaba — días con TempMin NaN del mismo día pero T-4 con datos; ver T3(e)).
- [x] **T3** Diagnóstico post-fix: (a) lag == TempMin de T−4 calendario en muestra de regiones,
      (b) % lag==mismo día cae de 97.8% a ~0%, (c) rolling 7d == media calendario 7d en muestra,
      (d) umbral lluvia == percentil 90 solo de 2024, (e) filas/fechas/regiones coherentes.
      — evidencia: `python3 src/pipelines/verificar_fix_features.py` → **7/7 PASS**: (a) 100,0000%
      (716.308/716.308 en Metropolitana/Maule/O'Higgins; + MP2_5 T−2 100%), (b) **1,605%**
      (antes 97,8%; coincidencias casuales), (c) 100% con tolerancia 1e-9 (ventana [T−6..T]
      recomputada desde la fuente), (d) 889.524/889.524 sin discrepancias, (e) 27 cols / 8
      regiones / 727 fechas (2024-01-05→2025-12-31) — desviación vs estimación de filas
      explicitada en la salida.
- [x] **T4** Crear `reentrenar_modelo_v7_features_fix.py` (copia del E2 con outputs v7) y correr
      reentrenamiento (region stage + directo). Verificado: métricas impresas y guardadas en
      `models/model_metadata_v7.json`. — evidencia: `python3 src/pipelines/reentrenar_modelo_v7_features_fix.py`
      → OK, test 2025: **MAE 9,3011 / RMSE 13,0099 / R² 0,7250 / sesgo +8,78%** (n=118.308);
      artefactos `models/model_rf_directo_v7.joblib` + `models/model_metadata_v7.json` creados;
      identidad Etapa 1 vs metadata v5 congelada: DIFIEREN (esperado: `df_modelo` regenerado);
      script E2 original y artefactos v6 intactos.
- [x] **T5** Comparación v6 (baseline: MAE 9.3338 / RMSE 13.0481 / R² 0.7231 / +9.77%) vs v7.
      Si v7 empeora → STOP, preguntar. — evidencia: comparación metadata v6e2 vs v7 →
      **v7 mejora en las 4 métricas**: MAE 9,3338→**9,3011** (-0,35%), RMSE 13,0481→**13,0099**,
      R² 0,7231→**0,7250**, sesgo 9,77→**8,78** pts → continúa normal (sin STOP).
      Nota: el "+9,77%" del baseline coincide con el `sesgo_pct` de v6 en su metadata, no con una
      mejora MAE vs v5 (la real es 36,78%).
- [x] **T6** Sincronizar al repo (`Modelo/src/pipelines/`, `Modelo/artifacts/`), actualizar
      `Modelo/docs/model_evolution.md` y ambos `PROJECT_CONTEXT.md`, demo: nueva sección 6 (v7),
      dejar sección 5 (v6) intacta. **Ampliaciones (gatekeeper 2026-11-11):**
      a) el v7 solo vuelca el modelo directo — agregar dump de la Etapa 1 a
      `models/model_rf_region_v7.joblib` (la Etapa 1 v7 DIFIERE de la v5: parquet regenerado),
      re-ejecutar (RF con random_state fijo = determinista; métricas deben ser idénticas a las
      ya registradas — verificar) y llevar también ese joblib al repo (consistente con que
      `model_rf_region_v5.joblib` está trackeado);
      b) auditar el label "+9,77% vs v5" en docs del repo (`model_evolution.md`,
      `PROJECT_CONTEXT.md`, `README.md`): es el **sesgo** de v6, no una mejora MAE (la real
      v6 vs v5 es −36,8% MAE / R² 0,141→0,7231) — corregir donde esté mal etiquetado.
      — evidencia: re-run v7 con dump → **métricas idénticas** (9,3011/13,0099/0,7250/+8,78;
      RF determinista), `model_rf_region_v7.joblib` 1,28MB; repo sync con diff pre-copia
      confirmando que el diff era solo el fix; auditoría +9,77% → etiquetas ya correctas en
      los 4 docs + labels explícitos agregados; demo 36→42 celdas, sección 6 ejecutada con
      nbclient (secciones 1-5 byte-idénticas); labels residuales `arquitectura.md` y
      `model_report.md` corregidos inline por el orquestador; archivo ajeno
      `DIRECTIVAS_REVISION_PENDIENTE.md` (revisión externa, solo-lectura) detectado en el
      repo — NO tocado, requiere autorización del usuario.
- [ ] **T7** Commit en GitHub Desktop (usuario) + verificar que `Proyecto de título/models/`
      y el repo quedaron consistentes.

## Criterios de aceptación

1. Los 3 bugs corregidos con evidencia de diagnóstico (T3) — no afirmación, medición.
2. Reentrenamiento completo con métricas registradas en metadata v7.
3. Tabla v6 vs v7 entregada con veredicto honesto.
4. Repo sincronizado; artefactos v6 intactos; demo actualizada sin romper el v6.

## Verificación (checks aplicables)

- TDD: **no habilitado** en este proyecto (sin runner configurado; ciclos previos usaron
  verificación funcional — mantener ese modo).
- Diagnóstico post-fix (T3) y reentrenamiento con métricas (T4) son la verificación de registro.
- Chequeo de estructura final: `git status` en repo tras sincronización.

## Progreso

- [x] Exploración y causa raíz confirmada (152 filas/fecha; 97.8% duplicado; evidencia de código).
- [x] T1–T6 completados (fix + parquet + diagnóstico 7/7 PASS + v7 entrenado + comparación:
      v7 mejora a v6 + repo/docs/demo sincronizados + Etapa 1 volcada) — evidencias en el
      checklist.
- [ ] T7 Commit en GitHub Desktop (usuario) — archivos listados en `git status` del repo.

**Siguiente paso:** T7 (commit del usuario). Llegó además `Modelo/docs/DIRECTIVAS_REVISION_PENDIENTE.md`
(revisión externa de solo-lectura, originada durante T6): lista tareas propias con sus P0s
(SENAMHI Antofagasta/Atacama; ablación sin features de persistencia) que **requieren
autorización explícita del usuario** — no iniciar sin pedirla.

## Registro de rutas (route declaration)

| Tarea | Ruta | Trigger |
|-------|------|---------|
| Doc de tareas (este archivo) | inline | mecánico, ya entendido |
| T1-T5 (fix + parquet + diagnóstico + v7 + comparación) | delegated direct | writer trigger: 2+ archivos no triviales |
| T6 docs/demo | delegated direct | 2+ archivos |
| T7 commit | usuario | preferencia de proyecto (GitHub Desktop) |
