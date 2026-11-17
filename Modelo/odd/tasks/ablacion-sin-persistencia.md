# Tarea: Ablación sin persistencia (directivas T2 — P0)

> **Feature:** `ablacion-sin-persistencia` · **Estado:** en progreso · **Creado:** 2026-11-15
> **Ruta:** delegated direct (writer trigger: script nuevo + 2 docs)
> **Autorización:** usuario, 2026-11-15 ("Ejecutar ablación B+C")

## Objetivo

Responder la pregunta P0 de la defensa: **¿cuánto del R² 0,725 lo aportan el clima y
la estacionalidad, y cuánto la autocorrelación de la demanda?** Hoy es inseparable:
Pred_E1 (0,311) + Total_Lag_4 (0,304) + Share_Trailing (0,113) = 0,728 de la
importancia total, tres codificaciones de la misma señal.

Fuente: `Modelo/docs/DIRECTIVAS_REVISION_PENDIENTE.md` sección T2 (con el matiz
de corrida C agregado por el orquestador: dentro de "el resto" está `Doy*`, que es
estacionalidad, no clima).

## Diseño (aprobado en conversación)

Mismo parquet v7, mismo split 2024/2025, mismos hiperparámetros congelados (sin
tuning), misma semilla. Una sola clonación del script v7 que entrena dos modelos
quitando columnas de la matriz antes de ajustar:

| Corrida | Quita | n features | Responde |
|---|---|---|---|
| A (base, ya existe) | — | 27 | R² 0,7250 |
| B sin persistencia | Pred_E1, Total_Lag_4, Share_Trailing, Pred_Region | 23 | clima+calendario+tipo sin historia |
| C sin persist ni calendario | B − Doy, Doy_Sin, Doy_Cos | 20 | ¿clima o estacionalidad pura? |

Interpretaciones pre-registradas: B ≈ 0,2 → el sistema vive de la persistencia;
B ≈ 0,5 → el resto aporta sustantivamente; C ≪ B → parte de B era calendario.
Las tres lecturas son publicables; lo no publicable es no hacerlo.

**Cuidado de redacción:** R² no es aditivo entre corridas — reportar caídas
observadas ("de 0,7250 a X"), no fracciones aritméticas inventadas.

## Checklist

- [x] **B1** Crear `src/pipelines/reentrenar_v7_ablation.py` (clon del v7: mismos
      hiperparámetros/semilla verificados, dos corridas B y C, sin tuning) +
      ejecutar ambas. → EJECUTADO 2026-11-15 (3,4 s): **B** MAE 14,0248 /
      RMSE 18,8330 / R² 0,4237 / sesgo +8,20% · **C** MAE 14,3812 / RMSE
      19,1327 / R² 0,4052 / sesgo +8,16% (n = 118.308 ambas; sin NaN, R² < 0,9).
      Hiperparámetros idénticos verificados: ambos scripts usan
      `v5.HIPERPARAMETROS` (n_estimators=200, max_depth=15,
      min_samples_split=50, min_samples_leaf=20, max_features='sqrt',
      random_state=42), ninguno los redefine.
- [x] **B2** Artefactos: `models/model_metadata_v7_ab_sin_persistencia.json` y
      `models/model_metadata_v7_ab_sin_persist_sin_doy.json` (con MAE/RMSE/R²/sesgo
      test 2025 + lista de features usadas). Sin dump de joblib (no aporta, 44MB c/u).
      → CREADOS (23 y 20 features respectivamente; incluyen hiperparámetros,
      semilla, split, base declarada v7/parquet 2026-11-15 y comparación vs
      A: R² 0,7250 / MAE 9,3011). Joblibs v6/v7 intactos (mtime 22:17).
- [x] **B3** Docs: fila + sección nueva en `Modelo/docs/model_evolution.md` (formato
      de versiones previas, append-only) y frase honesta en `Modelo/docs/model_report.md`
      sobre qué explica la caída; copia de metadata a `Modelo/artifacts/` del repo.
      → HECHO: sección "## v7-ab — Ablación sin persistencia (2026-11-15)" +
      2 filas nuevas en la tabla resumen; declaración en `model_report.md`
      (caídas observadas, sin aritmética de fracciones; C ≈ B → calendario
      no es el motor); 2 JSON copiados a `Modelo/artifacts/`.
- [x] **B4** Checkboxes de este doc + espejo engram actualizados con métricas.
      → ESTE ACTO + guardado en Engram (project: poke-tracker).

## Criterios de aceptación (directivas + contrato)

1. Artefacto con MAE/RMSE/R²/sesgo por corrida (cierre directivas: sin artefacto no hay cierre).
2. Entrada en `model_evolution.md` con problema/decisión/resultado.
3. Frase en `model_report.md` con lectura honesta (sin aritmética de fracciones).
4. Verificación: parámetros idénticos a v7 (grep de config), split sin tocar,
   hiperparámetros sin tunear.

## Verificación

- TDD no habilitado (proyecto); checks funcionales: corrida completa + métricas
  impresas + comparación contra v7 base (0,7250 / MAE 9,3011).
- Chequeo de estructura: `git status` del repo (solo archivos esperados).

## Progreso

- [x] Diseño aprobado por usuario (2026-11-15)
- [x] B1–B4 (ejecutado 2026-11-15; sin commits — el commit lo realiza el usuario)

**Siguiente paso:** revisión/commit por el usuario (pendiente: nada de este
ciclo; B1–B4 cerrados con artefactos y docs).
