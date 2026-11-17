# Directivas de revisión pendientes

> ⚠️ **Documento histórico.** Se escribió cuando la versión vigente era v7.
> Desde entonces se resolvieron la cobertura regional (8 → 16 regiones) y se
> avanzó hasta v11 (MAE 6.787 / R2 0.8283). Los puntos que siguen abiertos en
> v11 están listados en `model_evolution.md` sección "Estado actual y camino
> pendiente". Este documento se conserva como registro de la revisión.

Documento de trabajo para el agente activo. Origen: revisión externa de solo
lectura sobre el estado v6 E2 / v7. **No es un informe de errores.** Es una
lista de verificación de lo que queda expuesto frente a la defensa de tesis.

Estado verificado al escribir esto: v7 (`model_metadata_v7.json`) ya corrigió
los tres bugs de features climáticas (lags de calendario, `Region_Media_7d_*`
sobre días, umbral de lluvia train-only). Eso **no está pendiente**; está bien
hecho y no se menciona más abajo.

---

## No tocar

- **v5 y sus artefactos.** Métricas, joblib, cuotas, metadata: congelados.
  Son la referencia contra la que se mide el delta de arquitectura.
- **El split 2024 / 2025.** No re-particionar, no hacer k-fold, no mezclar
  años. Es la garantía de honestidad del proyecto.
- **Los números ya publicados en `model_evolution.md`.** Si un fix los
  invalida, se agrega una fila nueva a la tabla; no se edita el histórico.

---

## Verificar antes de avanzar

### 1. Atribución de `Pred_E1` — la pregunta que van a hacer en la defensa

`Pred_E1 = Share_Trailing × Pred_Region`, y `Share_Trailing` se construye con
`shift(4).rolling(30).sum()`, o sea **contiene demanda real reciente del propio
establecimiento**.

Las tres features de mayor importancia (`Pred_E1` 0.311, `Total_Lag_4` 0.304,
`Share_Trailing` 0.113 en v6 E2) suman **~0.73 de la importancia total**. Las
tres son, en esencia, *la misma información*: lo que el establecimiento atendió
hace unos días, expresado de tres formas.

No es leakage —la verificación existente lo demuestra bien— pero sí es un
problema de **atribución**. La pregunta que sigue sin respuesta es:

> ¿Cuánto del R² 0.72 lo aporta el clima y cuánto la autocorrelación del target?

**Esto no se puede responder sin una ablación.** Es la tarea T2.

### 2. Cobertura real: ¿8 o 16 regiones?

- `docs/PROJECT_CONTEXT.md` línea del apartado 1: **"16 regiones administrativas"**
- `docs/model_report.md`, sección Datos: **"Regiones: 8"**
- `model_metadata_v7.json` → `metricas_por_region` tiene **8 entradas**

Además, Antofagasta y Atacama **no existen en train 2024** (bug de CSVs
SENAMHI 2024), así que su one-hot está en cero en train y el modelo se apoya
solo en su historia de 2025.

Atacama: R² −0.0639, sesgo **+66.26%** (v7). Eso no es un caso "acotado": es
un modelo que falla en una región que el proyecto declara cubrir.

### 3. Sanity de `Total_Lag_4` — ya verificado, dejar registrado

`218.777 / 218.777` filas con historial comparable coinciden con `Total(T−4)`.
`16.331` filas coinciden también con `Total(T)` por valor idéntico
(coincidencia de demanda estable, no fuga). Correlación `0.8015`.

Conclusión: **el lag está bien.** No re-verificar ni reabrir. Solo asegurar que
este resultado esté citado en el reporte, porque es la defensa central.

---

## Orden de trabajo

### T1 — CSVs SENAMHI 2024 de Antofagasta y Atacama (P0)

Sin estas dos regiones el modelo no cubre Chile y Atacama falla con sesgo
+66%. Es la prioridad más alta, por encima de cualquier mejora de modelo.

- Localizar la causa del bug en `src/data_extraction/` (¿encoding? ¿formato de
  fecha? ¿nombres de estación?) y verificar si los datos crudos existen.
- Si los datos crudos existen → regenerar `df_unificado.parquet` e incorporar
  ambas regiones a train 2024. **Esto obliga a reentrenar v5, E1, E2, v7** para
  mantener la comparabilidad. Ver "Restricciones" abajo antes de hacerlo.
- Si los datos no existen → documentar explícitamente en `PROJECT_CONTEXT.md`
  que la cobertura real es de 6 regiones con train y 2 sin, y **cambiar el
  "16" por el número real**. Un evaluador del MINSAL pregunta primero por su
  región.

**Criterio de aceptación:** `metricas_por_region` incluye Antofagasta y
Atacama con datos de train, o el documento declara la cobertura real sin
ambigüedad. Nunca las dos cosas contradictorias.

### T2 — Ablación sin persistencia (P0)

El experimento que falta para poder afirmar algo sobre el clima.

Entrenar el mismo `RandomForestRegressor`, mismo split, misma semilla,
quitando `Total_Lag_4`, `Share_Trailing`, `Pred_Region` y `Pred_E1`. Quedan:
one-hot tipo + región, `Doy`/`Doy_Sin`/`Doy_Cos`, y las 7 climáticas.

Dos resultados posibles, **ambos publicables**:

| Resultado | Lectura honesta |
|---|---|
| R² ~0.2 | El aporte del clima es marginal; el valor del sistema está en la persistencia. Hay que decirlo. |
| R² ~0.5 | El clima aporta señal sustantiva una vez que se lo aísla. Hallazgo más fuerte para la tesis. |

**Lo que no es publicable es no hacer la ablación.** Es la diferencia entre
"mi modelo predice usando clima" y "mi modelo predice usando la semana pasada,
y además incorpora clima".

**Criterio de aceptación:** artefacto en `artifacts/` con MAE/RMSE/R²/sesgo de
la ablación, fila nueva en la tabla de `model_evolution.md`, y una frase en
`model_report.md` que declare qué fracción del desempeño explica la
persistencia.

### T3 — `Dias_Desde_Ultimo_Reporte` (P1)

`calcular_total_lag_calendario` usa `reindex(cal).ffill()` antes del
`shift(4)`. Si un establecimiento no reporta 10 días, `Total_Lag_4` en T es el
último valor observado, que puede ser de T−14 aunque el nombre diga T−4.

No es leakage (nunca mira el futuro) y está documentado en el docstring, pero
el modelo no puede distinguir un lag de 4 días de uno de 14. Una feature con
los días transcurridos desde el último reporte cierra el flanco a bajo costo.

**Criterio de aceptación:** feature agregada, reentrenado, delta de métricas
documentado (aunque sea nulo — un delta nulo es un resultado válido).

### T4 — DEIS 2022–2023 (P1, bloqueado por datos)

Es la única forma de (a) validar fuera de este split y (b) responder la
hipótesis de la contaminación. Mientras no exista, `model_evolution.md` debe
decir con claridad que **el modelo no está validado externamente**.

---

## Restricciones

- **Solo lectura hasta autorización explícita del usuario.** Este documento es
  una directiva de revisión, no una autorización de escritura.
- **T1 puede romper la comparabilidad histórica.** Incorporar regiones a train
  invalida las métricas de v5/E1 contra las que se mide todo. Si se hace,
  versionar como release nuevo y **no borrar** los artefactos previos.
- **No optimizar hiperparámetros todavía.** Están congelados a los de v5 a
  propósito, para aislar el efecto de la arquitectura. Tunear ahora contaminaría
  la comparación v5 → E1 → E2 → v7.
- **No presentar la exploratoria post-hoc como resultado validado.** Fue
  seleccionada con el test a la vista (`model_evolution.md` ya lo advierte;
  mantener esa advertencia).

---

## Criterio de cierre

Cada tarea, al cerrarse, deja:

1. Un artefacto en `artifacts/` con las métricas observadas.
2. Una entrada en `docs/model_evolution.md` con el problema, la decisión y el
   resultado — respetando el formato de las versiones anteriores, que ya es
   bueno.
3. Si el resultado contradice un documento previo, se corrige el documento y se
   deja constancia del cambio. La contradicción "16 regiones" vs "8 regiones"
   es el caso actual.

Ninguna tarea se cierra con métricas sin artefacto que las respalde.
