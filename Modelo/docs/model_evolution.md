# Evolución del Modelo — v1 a v11

Historial de iteraciones del modelo de predicción de demanda en urgencias
respiratorias. Cada versión se documenta con el problema que motivó el cambio,
la decisión tomada y las métricas verificadas sobre el mismo split
(train 2024 → test 2025).

> **Nota de integridad:** las métricas de v1 están infladas por *data leakage*
> y se conservan solo como referencia del punto de partida. Todas las versiones
> posteriores son honestas.

---

## Contexto común a todas las versiones

- **Target:** total de atenciones de urgencia respiratoria (CIE-10 J00–J99).
- **Split temporal:** train = 2024, test = 2025 (nunca se mezclan años).
- **Evaluación a nivel establecimiento+día.** El dataset DEIS tiene ~4 filas
  por (establecimiento, fecha) — una por cada causa respiratoria distinta —
  por lo que la demanda real de un establecimiento en un día es la **suma** de
  esas filas. Todas las métricas citadas se re-agregan a esa granularidad
  para ser comparables entre versiones.
- **Señal climática:** es a nivel **región**, no por establecimiento. Todos los
  establecimientos de una misma región+fecha reciben exactamente el mismo
  clima (~44 establecimientos por grupo, con desviación estándar del target
  ≈ 13.6). Este hecho estructural explica gran parte de la historia.

---

## Tabla resumen

| Versión | Arquitectura | MAE (estab+día) | R² | Sesgo |
|---------|--------------|-----------------|-----|-------|
| v1 | Una etapa, con rangos etarios | 0.321 | 0.9956 | — |
| *— v1 era artificial (leakage) —* | | | | |
| v2 | Una etapa, absolutos | 17.437 | 0.0427 | +17.3% |
| v3 | Dos etapas, absolutos | 20.119 | −1.979 | +34.6% |
| v4 completo | Dos etapas, anomalías fijas | 16.307 | −0.2851 | +24.95% |
| v4 sin contaminación | — | 13.396 | 0.2423 | +13.72% |
| v5 | Dos etapas, anomalías trailing | 14.763 | 0.141 | +21.01% |
| v5 sin contaminación | — | 13.285 | 0.1942 | +17.63% |
| v6 E1 | Dos etapas, cuota trailing regional | 13.808 | 0.1939 | +21.73% |
| v6 E2 | Directo, 1 RF a nivel establecimiento | 9.334 | 0.7231 | +9.77% |
| v7 (8 regiones) | Directo + fix de features climáticas | 9.301 | 0.7250 | +8.78% |
| v7-ab B (sin persistencia) | Directo, 23 feats (sin historia de demanda) | 14.025 | 0.4237 | +8.20% |
| v7-ab C (B sin calendario) | Directo, 20 feats (clima + tipo puro) | 14.381 | 0.4052 | +8.16% |
| v7 (16 regiones) | Directo, 35 feats, cobertura completa | 8.550 | 0.7378 | +5.69% |
| v8 | + nivel y tendencia regional | 8.009 | 0.7648 | +4.17% |
| v9 | + patrón semanal | 7.236 | 0.8066 | +4.25% |
| v10 | + calendario de feriados (rechazada) | 7.251 | 0.8060 | +4.54% |
| **v11 (actual)** | **+ ventanas móviles del establecimiento** | **6.787** | **0.8283** | **+2.57%** |

**R² a nivel REGIÓN (Etapa 1 del modelo de dos etapas):**

| Versión | R² región |
|---------|-----------|
| v3 | 0.5643 |
| v5 (trailing) | 0.8545 |
| v5 mejor config exploratoria | 0.9037 |

---

## v1 — El *data leakage* que infló el modelo

**Qué era:** un `RandomForest` directo a nivel establecimiento que reportaba
MAE 0.321 y R² 0.9956.

**El problema:** el target `Total` es exactamente la suma de las cinco columnas
de rango etario (`Menores_1`, `De_1_a_4`, `De_5_a_14`, `De_15_a_64`,
`De_65_y_mas`). Esas columnas estaban entre las features. El modelo no
**predecía** la demanda: la **sumaba**. Un R² de 0.99 no era señal, era la
identidad matemática `Total = Σ rangos` aprendida por el árbol.

**Por qué pasó desapercibido:** un MAE de 0.32 pacientes/día parece fantástico
sobre un target con media ~31. La anomalía se detectó al cruzar la definición
del target con la lista de features, no al mirar la métrica.

**Arreglo:** v2 elimina por completo los rangos etarios de las features.

**Lección:** una métrica perfecta casi siempre indica un leak, no un modelo
extraordinario. Conviene auditar siempre `target == f(features)`.

---

## v2 — Modelo honesto, y el muro del clima regional

**Qué era:** el mismo enfoque de una etapa, pero con 15 features reales
(clima, contaminación, lags, banderas) y **sin** rangos etarios.

**Resultado:** a nivel establecimiento+día, MAE 17.437 / R² 0.0427.

**El diagnóstico:** el R² casi nulo no era un problema de hiperparámetros. El
clima es idéntico para los ~44 establecimientos de una misma región+fecha, así
que el modelo **no tiene información para distinguirlos**. Con un target cuya
desviación estándar dentro de cada grupo es ≈ 13.6, predecir "el promedio del
grupo" ya es casi todo lo que se puede hacer. El techo estaba en los datos, no
en el algoritmo.

**Lección:** cuando la señal predictiva es a nivel región y el target es a
nivel establecimiento, un modelo de una etapa no puede inventar la variación
faltante.

---

## v3 — Arquitectura de dos etapas

**Idea:** separar el problema en dos etapas que respetan la jerarquía de los
datos.

1. **Etapa 1 (región):** predecir la demanda **total de la región** por día,
   donde el clima sí varía entre regiones y hay señal real.
2. **Etapa 2 (establecimiento):** repartir ese total a cada establecimiento
   usando su **cuota histórica** (share) calculada sobre train 2024.

La estabilidad de las cuotas se verificó: correlación **0.993** entre 2024 y
2025 sobre 297 establecimientos comunes. Es decir, el "tamaño" relativo de cada
establecimiento dentro de su región es casi constante entre años.

**Resultado:** a nivel región la Etapa 1 logró R² 0.5643. Pero a nivel
establecimiento el sistema completo quedó en MAE 20.119 / R² −1.979, **peor**
que v2.

**Por qué falló:** dos bugs encoding/estacionalidad, no la arquitectura:
1. `Region_Encoded` con `LabelEncoder` es **ordinal**: el RF trataba a las
   regiones como un número continuo (Antofagasta=0 … O'Higgins=7), imponiendo un
   orden falso.
2. Sin estacionalidad explícita (día del año / semana epidémica) el RF no podía
   capturar el ciclo respiratorio.

**Lección:** la arquitectura de dos etapas era correcta; la implementación
tenía features mal codificadas. Distinguir "la idea está mal" de "la
implementación está mal" evita descartar buenos enfoques.

---

## v4 — Estacionalidad, one-hot y anomalías (y un bug de baseline)

**Correcciones sobre v3:**
- One-hot de región en lugar de `LabelEncoder` (R² de región: 0.56 → 0.80).
- Estacionalidad cíclica `Doy_Sin` / `Doy_Cos` (seno/coseno del día del año).
- La contaminación pasó de **nivel absoluto** a **anomalía** (desviación de la
  media histórica de esa región), para que el modelo aprenda "más
  contaminación de lo normal", no "más contaminación".

**Resultado y hallazgo inesperado:**

| Ablación | MAE | R² |
|----------|-----|-----|
| v4 completo | 16.307 | −0.2851 |
| v4 **sin** contaminación | 13.396 | 0.2423 |

Quitar la contaminación **mejoró** el modelo. La causa raíz: el baseline
estacional de la anomalía se calculó **solo con train 2024 y quedó congelado**.
Pero la contaminación tuvo un *drift* interanual (+26% a +57% de MP2.5 entre
2024 y 2025 en 5 de 6 regiones), de modo que las anomalías de test 2025 quedaron
 sistemáticamente > 0. El modelo proyectaba al alza la relación
 contaminación→demanda aprendida dentro de 2024, cuando en 2025 la demanda
**bajó** mientras la contaminación **subió**.

**Lección:** una feature derivada con un baseline congelado arrastra cualquier
*drift* interanual al test. Y un resultado contraintuitivo (quitar una feature
mejora) es una pista diagnóstica de oro, no un motivo para ignorarlo.

---

## v5 — Baseline adaptativo *trailing*

**La corrección:** reemplazar el baseline congelado por uno **adaptativo
trailing**. Para cada región y fecha `T`, la "normalidad" se calcula con la
media de los últimos **45 días estrictamente anteriores** a `T`
(`serie.shift(1).rolling(45, min_periods=10).mean()`). El `shift(1)` garantiza
que `T` nunca entra en su propio baseline. Así la normalidad se redefine con el
paso del tiempo y el drift deja de contaminar las anomalías.

**Evidencia de que el drift quedó corregido:** la anomalía media de MP2.5 en
test pasó de sistemáticamente positiva (v4) a **−0.124** (v5), centrada cerca de
cero.

**Resultado:** a nivel región, R² **0.8545**. A nivel establecimiento, MAE
14.763 / R² 0.141.

**Pero la contaminación sigue sin aportar.** El trailing corrigió el bug del
drift, no el problema de fondo de la señal:

| Ablación v5 | MAE | R² |
|-------------|-----|-----|
| Con contaminación trailing | 14.763 | 0.141 |
| **Sin contaminación** | 13.285 | 0.1942 |
| Con contaminación absoluta | 16.550 | −0.4998 |

---

## v6 — Del sistema de dos etapas al modelo directo (release publicado)

v6 no nace de una intuición sino de un **diagnóstico previo** (T2–T4) que
descompuso el error de v5 antes de tocar el modelo, y de ahí salieron dos
experimentos: E1 (cambio mínimo dentro de la arquitectura de dos etapas) y E2
(cambio de arquitectura). El resultado oficial es **E2**.

### Diagnóstico T2–T4 — ¿dónde estaba el error de v5?

Script: `src/pipelines/diagnostico_v6_descomposicion.py` · salida:
`artifacts/diagnostico_v6_t2.json`. Todo sobre test 2025, nivel
establecimiento+día.

| Configuración | MAE | R² | Qué mide |
|---|---|---|---|
| C: v5 reportado | 14.763 | 0.141 | referencia |
| A: cuota 2024 × climatología regional 2024 (mismo MM-DD) | 10.403 | 0.411 | techo climatológico (solo 6 regiones con train) |
| B: Etapa 1 **perfecta** × cuota fija 2024 | 8.383 | 0.756 | techo de v5 |
| D: Etapa 1 **perfecta** × cuota trailing 30d | 6.952 | 0.836 | techo con cuota dinámica |
| Persistencia pura (`pred = Total_Lag_4`) | 11.074 | 0.584 | baseline sin modelo |

Descomposición del error de v5 (14.763 → 8.383 → 6.952):

- **La Etapa 1 concentra ≈ 6.4 MAE** del error: es la mayor fuente. La arquitectura
  de dos etapas transmite ese error a cada establecimiento.
- **La variabilidad diaria de la región aporta ≈ 2 MAE** (A 10.403 → B 8.383):
  pasar de climatología a la región real del día ya mejora bastante.
- **La cuota trailing gana ≈ 1.4 MAE** incluso con región perfecta (8.383 →
  6.952); en Antofagasta/Atacama, sin cuota 2024, gana el doble (13.29 → 6.37).
- **La persistencia pura ya le ganaba a v5** (11.074 vs 14.763): la demanda
  reciente del propio establecimiento era la señal más fuerte disponible a T−4.
- **T4:** la correlación parcial del residuo con el lag 4 es 0.284 (señal
  existe), pero ΔR² sobre D = 0.000 → la cuota trailing ya absorbe esa señal;
  el lag 4 sirve como **feature del modelo**, no como corrección del share.
- **Suelo de ruido:** la dispersión del `Total` real dentro de una misma
  región+fecha es σ ≈ 19.98 (mediana 17.94): es el techo de cualquier
  reparto por cuota.

### E1 — Cuota trailing con denominador regional (mejora parcial)

**Cambio único sobre v5:** la Etapa 2 pasa de cuota histórica fija 2024 a
**cuota dinámica trailing** `shift(4).rolling(30, min_periods=10)` sobre el
**calendario** de cada establecimiento (días sin reporte = NaN), repartida con
**denominador regional**: el peso se divide por la suma del peso de **todos**
los establecimientos de la región (reporten o no ese día), de modo que los no
reportantes dejan su parte sin repartir — la misma semántica conservadora de
v5. La Etapa 1 se importa sin modificar del módulo v5 (features, anomalías
trailing N=45, one-hot, hiperparámetros y semilla idénticos; R² región 0.8545
verificado idéntico). Un control con cuota fija reprodujo v5 **exactamente**
(14.763 / 22.981 / 0.141 / +21.01%), de modo que el único delta es la cuota.

**Bug de diseño encontrado y corregido en E1:** la primera versión
renormalizaba la cuota entre **solo los establecimientos con fila ese día** (los
reportantes). Como hay (Región, Fecha) con **un solo reportante**, ese
establecimiento se llevaba el 100% del total regional predicho (~2.000–2.600)
frente a una demanda real de decenas. Resultado: **1.42% de las filas
explicaban el 44.54% del SSE** (MAE 14.0604, pero RMSE 29.1255 / R² −0.3798).
Fix: denominador **regional** (con el trail calculado sobre series reindexadas
al calendario). Con el fix, esas mismas filas explican solo el 5.87% del SSE.

**Resultado de E1:** MAE **13.808** / RMSE 22.262 / R² **0.1939** / sesgo
+21.73% → mejora en 3 de 4 métricas frente a v5 (ΔMAE −0.955), pero **no es
un éxito total**: el sesgo empeora levemente y la arquitectura sigue atada al
techo de la Etapa 1.

### E2 — Modelo directo a nivel establecimiento (resultado final)

Reemplaza la cadena de dos etapas por **un solo `RandomForestRegressor`**
entrenado sobre filas (establecimiento, fecha) con target `Total` en nivel:
27 features (`Total_Lag_4`, `Share_Trailing`, `Pred_Region`, `Pred_E1`,
one-hot Tipo+Región, `Doy`/`Doy_Sin`/`Doy_Cos`, y 7 climáticas regionales del
día T **sin contaminación**), mismos hiperparámetros y semilla 42 que v5.
Pred_E1 entra como feature para que el modelo directo **corrija** al sistema
dos-etapas en lugar de depender de él.

| Versión | MAE | RMSE | R² | Sesgo |
|---|---|---|---|---|
| v5 (dos etapas, cuota fija) | 14.763 | 22.981 | 0.1410 | +21.01% |
| E1 (dos etapas, cuota trailing) | 13.808 | 22.262 | 0.1939 | +21.73% |
| Exploratoria post-hoc (sin contam. + `Anom_TempMin`) | 12.785 | 20.330 | 0.3277 | +11.32% |
| **E2 (directo — oficial)** | **9.334** | **13.048** | **0.7231** | **+9.77%** |

**Verificación independiente PASS (anti-leakage):**
- `Total_Lag_4 == Total(T−4)` en **219.995 / 219.995** filas con historial
  comparable (se construye con `shift(4)` sobre calendario antes de unir con el
  target); correlación `Total_Lag_4` vs `Total` = 0.8016, no sospechosa.
- Target no es feature; sanity-check automático R² < 0.9 cumplido (0.7231).
- v5 intacto: SHA-256 del artefacto v5 verificado sin cambios.

**Importancias top:** `Pred_E1` **0.311** · `Total_Lag_4` **0.304** ·
`Share_Trailing` **0.113** → el modelo aprendió a ajustar el sistema
dos-etapas con la demanda reciente.

**Por región (R²):** Maule 0.83 · Arica y Parinacota 0.81 · Metropolitana
0.70 · Magallanes 0.66 · Antofagasta 0.63 · O'Higgins 0.54 · Coquimbo 0.48 ·
**Atacama −0.03** (única región débil; sesgo +64.8%).

### E3 — Ablación de temperatura: absolutas vs categóricas

Justifica metodológicamente el cambio v1→v6 en la codificación de temperatura.
Mismo modelo E2, mismo split, tres configuraciones (control A reproduce E2
exacto):

| Config | MAE | RMSE | R² | Sesgo |
|---|---|---|---|---|
| A — Absolutas (config. v6 E2) | 9.3338 | 13.0481 | 0.7231 | +9.77% |
| B — Categóricas one-hot (bins clínicos −5/5/15/25 °C) | 9.3390 | 12.9860 | 0.7257 | +9.62% |
| C — Categóricas ordinal 0..4 (estilo v1) | 9.2869 | 13.0398 | 0.7234 | +9.42% |

**Conclusión: equivalencia estadística** (|ΔMAE| ≤ 0.5%, |ΔR²| ≤ 0.003). Las
absolutas no se justifican por mayor precisión sino por **granularidad y no
perder información**: los bins fijos colapsan rangos útiles (0 filas "Caluroso"
en `TempMin_Lag_4D` y `Region_Media_7d_TempMin`), y el RandomForest aprende los
umbrales por sí solo. Evidencia:
`src/pipelines/reentrenar_modelo_v6_e3_ablation_temp.py` +
`artifacts/model_metadata_v6e3_ablation_temp.json`.

### Hallazgos abiertos de v6

- **Atacama:** R² −0.03 y sesgo +64.8%. Es región **nueva** (junto con
  Antofagasta, no existe en train 2024 por el bug de los CSV SENAMHI 2024), su
  one-hot está en 100% cero en train y solo se apoya en su historia de 2025.
  Antofagasta, con la misma limitación, sí responde (R² 0.63): el problema de
  Atacama no está solo en la ausencia de train. Caso conocido y acotado.
- **`TempMin_Lag_4D` preexistente (no introducido por v6):** en
  `src/pipelines/feature_engineering.py` el lag se calcula con
  `groupby("Region").shift(4)` sobre **filas**, no sobre el calendario. Como el
  panel tiene ~116–176 filas por región+fecha, el "lag 4" cae dentro de la
  misma fecha: **97.8% de los valores coinciden con el mismo día** (medido
  sobre `df_modelo.parquet`: 874.992/894.652). `MP2_5_Lag_2D` tiene el mismo
  defecto (98.9%). Afecta **por igual a todas las versiones** (v1–v6 usan el
  mismo módulo), así que la comparabilidad relativa entre versiones queda
  intacta; era candidato a fix futuro con reindex al calendario — **resuelto en
  v7** (ver sección siguiente).
- **La contaminación sigue sin aportar:** E2 la excluye de sus features y aun
  así logra el mejor resultado de la serie; el único rol de la contaminación en
  v6 es dentro de `Pred_Region` (config trailing de v5). La hipótesis sigue
  abierta: validarla requiere DEIS 2022–2023.

---

## v7 — Fix de los bugs de features climáticas

**Fecha:** 2026-11-11. **Qué motivó el cambio:** el hallazgo de v6 sobre
`TempMin_Lag_4D` (arriba) se diagnosticó a fondo y resultó ser parte de un
problema más grande: `df_unificado.parquet` tiene **~152 filas por (Región,
Fecha)** (una por causa DEIS), y las features climáticas se calculaban con
operaciones sobre **filas**, no sobre el **calendario**. Tres bugs:

| Bug | Antes | Después |
|---|---|---|
| `TempMin_Lag_4D` / `MP2_5_Lag_2D` | `shift(n)` sobre filas → **97,8%** de los valores eran el mismo día | lag de **CALENDARIO** (serie deduplicada 1 fila/fecha, ordenada y mergada de vuelta) |
| `Region_Media_7d_TempMin` / `_MP25` | `rolling(7)` sobre filas ≈ fracción de un día (~152 filas/día) | media de **7 DÍAS de calendario** |
| `Lluvia_Intensa_Flag` | percentil 90 por región sobre **todo** el df (incluía test 2025 → transductivo) | umbral q90 **train-only** (`Fecha < 2025-01-01`), congelado y aplicado a todas las filas |

- `df_modelo.parquet` regenerado: **889.524 filas × 27 columnas** (antes
  894.652; delta −5.128 por el dropna de los primeros días calendario, que a la
  vez reintegra filas que el lag viejo descartaba).
- Verificación: `src/pipelines/verificar_fix_features.py` → **7/7 PASS**
  (lag == T−4 calendario 100,0000%; % de lag == mismo día 97,8% → **1,605%**;
  rolling == media de calendario 100%; q90 sin discrepancias en 889.524 filas).
- Reentrenamiento E2 como v7 con el **mismo split, hiperparámetros y semilla**
  (`src/pipelines/reentrenar_modelo_v7_features_fix.py`): RF con
  `random_state=42` fijo → **determinista**; una segunda ejecución reprodujo
  exactamente las mismas métricas.

> **Nota de cobertura:** esta sección describe v7 con el dataset de **8
> regiones** (el disponible cuando se escribió). Con la cobertura corregida a
> 16/16 regiones, el mismo v7 pasa a **MAE 8.550 / R2 0.7378 / sesgo +5.69%**
> (35 features). La metadata del v7 de 8 regiones se conserva como
> `artifacts/model_metadata_v7_8reg.json`; `artifacts/model_metadata_v7.json`
> contiene la versión de 16 regiones.


| Versión | MAE | RMSE | R² | Sesgo |
|---|---|---|---|---|
| v6 E2 (release publicado) | 9.334 | 13.048 | 0.7231 | +9.77% |
| v7 (8 regiones) | 9.301 | 13.010 | 0.7250 | +8.78% |

v7 **mejora las 4 métricas** frente a v6 (ΔMAE −0,35%; sesgo 9,77 → 8,78 pts,
n = 118.308): el salto de calidad lo dio v6 (cambio de arquitectura); el fix de
features es una mejora incremental honesta sobre la base correcta.

**Artefactos (`models/` en el workspace, `Modelo/artifacts/` en el repo):**

- `model_rf_directo_v7.joblib` — modelo directo (44 MB; **NO** se trackea en el
  repo, igual que el v6: los modelos directos se publican como release).
- `model_rf_region_v7.joblib` — **Etapa 1 (regional) de v7**, exportada por
  primera vez: genera `Pred_Region`/`Pred_E1`, features del modelo directo.
  **DIFIERE de la Etapa 1 v5** (el parquet se regeneró), así que el pipeline v7
  no puede servirse con el joblib v5. Sí se trackea (1,3 MB), consistente con
  que `model_rf_region_v5.joblib` está versionado.
- `model_metadata_v7.json` · scripts `reentrenar_modelo_v7_features_fix.py` y
  `verificar_fix_features.py`.

**Estado del release:** el release publicado sigue siendo **`modelo-v6-e2`**;
el de v7 (`modelo-v7-features-fix`) se publica por separado cuando corresponda.
Los artefactos v6 quedan congelados e intactos.

---

## v7-ab — Ablación sin persistencia (2026-11-15)

**Fecha:** 2026-11-15. **Directiva:** T2 (P0) de
`DIRECTIVAS_REVISION_PENDIENTE.md`.

**Problema (atribución):** en v7, tres codificaciones de la MISMA señal de
autocorrelación de la demanda concentran **0,728 de la importancia total** —
`Pred_E1` 0,311 + `Total_Lag_4` 0,304 + `Share_Trailing` 0,113. Sin una
ablación, "el modelo predice con clima" y "el modelo predice con la semana
pasada, y además incorpora clima" son indistinguibles.

**Decisión:** clon controlado del script v7
(`src/pipelines/reentrenar_v7_ablation.py`): mismo `df_modelo.parquet`, mismo
split 2024/2025, **mismos hiperparámetros y semilla congelados** (RF del v5,
`random_state=42`, sin tuning — verificados por importación de
`v5.HIPERPARAMETROS`, la misma fuente que usa el script v7) y mismo protocolo
de evaluación (nivel establecimiento + día). Dos corridas quitando columnas
**antes** de ajustar:

- **B (sin persistencia):** quita `Pred_E1`, `Total_Lag_4`, `Share_Trailing`,
  `Pred_Region` → **23 features** (one-hot tipo/región + `Doy*` + 7
  climáticas).
- **C (sin persistencia ni calendario):** B además quita `Doy`, `Doy_Sin`,
  `Doy_Cos` → **20 features** (one-hot tipo/región + 7 climáticas).

La Etapa 1 regional se ejecuta igual dentro del pipeline (genera
`Pred_Region` antes de quitarlo); no se vuelca ningún joblib.

| Corrida | n features | MAE | RMSE | R² | Sesgo |
|---|---|---|---|---|---|
| **A — v7 base (8 regiones)** | 27 | **9.301** | **13.010** | **0.7250** | **+8.78%** |
| B — sin persistencia | 23 | 14.025 | 18.833 | 0.4237 | +8.20% |
| C — sin persistencia ni calendario | 20 | 14.381 | 19.133 | 0.4052 | +8.16% |

Mismo test 2025, n = 118.308 en las tres corridas.

**Lectura honesta** (anclas pre-registradas en
`odd/tasks/ablacion-sin-persistencia.md`: B ≈ 0,2 → vive de la persistencia;
B ≈ 0,5 → el resto aporta sustantivamente; C ≪ B → parte era calendario):

- **B = 0,4237:** queda **entre** los dos anclas pre-registradas. El sistema
  **no** vive solo de la persistencia (de serlo, B quedaría ≈ 0,2), pero sin
  ella el R² **cae de 0,7250 a 0,4237** y el MAE sube de 9,3011 a 14,0248.
  Es decir: clima + calendario + tipo sostienen por su cuenta un R² de 0,42
  (por encima de v5 completo, 0,1410, y de la exploratoria post-hoc, 0,3277),
  pero la demanda reciente del propio establecimiento es necesaria para
  llegar a 0,7250.
- **C = 0,4052 vs B = 0,4237:** quitar la estacionalidad de calendario mueve
  el R² apenas **0,0185** → **la estacionalidad de calendario NO es el
  motor** del rendimiento sin persistencia; lo que queda en B/C es
  esencialmente clima regional + one-hot de tipo/región.
- **Referencia cruzada:** la persistencia pura del diagnóstico T2
  (`pred = Total_Lag_4`, R² 0,584 / MAE 11,074) tampoco se iguala por
  separado: B/C sin historia quedan en 0,42/0,41. El desempeño de v7 está en
  la **combinación** de persistencia con el resto, no en ningún bloque solo.

Cuidado de redacción: el R² **no es aditivo** entre corridas — lo anterior
son **caídas observadas** sobre el mismo split ("de 0,7250 a X"), no
fracciones del desempeño "explicadas" por cada bloque de features.

**Artefactos:** `artifacts/model_metadata_v7_ab_sin_persistencia.json` (B) y
`artifacts/model_metadata_v7_ab_sin_persist_sin_doy.json` (C),
copiados a `Modelo/artifacts/`. Sin dumps de joblib. Script:
`src/pipelines/reentrenar_v7_ablation.py`.

---

## Hallazgo transversal — La contaminación no mejora el modelo

Es el resultado más contraintuitivo del proyecto y conviene entenderlo bien.

**La contaminación correlaciona con la demanda *dentro* de un año** porque
ambas suben en invierno (frío → leña → smog, y frío → virus respiratorios).
Pero esa correlación es en gran parte un **proxy de la estación**. Cuando la
estacionalidad se modela explícitamente (`Doy_Sin`/`Doy_Cos`) y la contaminación
se lleva a anomalía, la señal adicional que aporta **no supera al ruido**.

Con solo 2 años de datos no hay muestra suficiente para separar "contaminación
cae demanda" de "ambas siguen la estación". Es una limitación de datos, no del
modelo.

**La temperatura sí aporta.** La mejor configuración exploratoria de todo el
proyecto combina el clima **sin** contaminación con la **anomalía de
temperatura mínima** (`Anom_TempMin`): MAE **12.784** / R² **0.3277** / sesgo
**+11.3%** — el mejor balance logrado *entre v1 y v5* (luego superado por el
modelo directo de v6, que conserva el clima sin contaminación). El frío, medido
como anomalía, sí tiene señal predictiva incremental.

**Cómo verificar la hipótesis de la contaminación:** incorporar DEIS de **2022
y 2023** y testear si la relación contaminación→demanda se sostiene entre pares
de años distintos. Si es causal, más años la confirman; si es espuria, más
años la descartan.

---

## Hallazgo transversal — Región vs. establecimiento

El R² a nivel región (0.85–0.90) y el R² a nivel establecimiento (0.14–0.33)
**no son comparables entre sí** y no deberían citarse como el mismo número.

- **Región:** el clima varía entre regiones → hay señal → R² alto.
- **Establecimiento:** todos los de una región+fecha reciben el mismo clima →
  el modelo solo reparte por cuota histórica → R² bajo.

Un R² de 0.33 a nivel establecimiento **no es un mal modelo**; es el techo
honesto de predecir por establecimiento usando principalmente clima. La
variación que queda sin explicar es la específica de cada establecimiento
(política interna, referencias, capacidad), que el clima no captura.

> **Actualización v6:** ese techo (0.14–0.33) describía a la arquitectura de
> **dos etapas**, no al problema. El modelo directo de v6 llega a R² 0.7231 a
> nivel establecimiento porque agrega la señal que a las dos etapas le faltaba:
> la demanda reciente del propio establecimiento (`Total_Lag_4`) y su cuota
> trailing, corrigiendo la predicción regional en lugar de repartirla a ciegas.

---

## Regiones nuevas sin histórico

**Antofagasta y Atacama no existen en train 2024** (bug de los CSV SENAMHI
2024). Concentran los peores errores del sistema, porque la Etapa 1 no tiene
historial de esas regiones. El fallback actual asigna la mediana de cuotas por
tipo de establecimiento. Es un caso conocido y acotado, no un defecto general.

---

## Corrección de cobertura regional (pre-v8)

Antes de continuar con la mejora del modelo hubo que resolver un problema de
datos que limitaba todo: **solo 8 de las 16 regiones llegaban al modelo**.

La causa no era falta de información — el archivo DEIS de atenciones es único y
contiene las 16 regiones con volumen abundante (Antofagasta 1.92M atenciones
2024, Atacama 1.37M). Lo que fallaba era la integración del clima:

| # | Bug | Efecto verificado |
|---|---|---|
| 1 | Nombres de carpeta en Unicode **NFD** (macOS) vs alias_map en **NFC** | `Valparaíso` jamás hacía match → merge de clima devolvía NaN |
| 2 | Alias DEIS faltantes (`Del Bíobío` con í acentuada, `De Aisén del Gral...`) | 2 regiones nunca se normalizaban |
| 3 | Fechas con hora en el CSV de Valparaíso (`2024-01-01 15:00`) | intersección de fechas clima/salud = **0** de 731 |
| 4 | CSV de temperatura inválidos: Antofagasta 2024 ausente, Atacama 2024 era de precipitación, Los Lagos 2024/2025 vacíos, Tarapacá 2024 ausente | 4 regiones sin clima 2024 |

Los cuatro se corrigieron (normalización NFC, alias explícitos, truncado de hora
y consolidación de registros horarios a resumen diario con
`src/pipelines/consolidar_temperatura_horaria.py`).

**Resultado:** 16/16 regiones con temperatura válida en 2024 y 2025, lo que
habilitó que todas participaran de train y test. Ese es el estado de partida de
v8 en adelante. La evidencia de la auditoría está en `ENTREGA/evidencias/`.

---

## v8 — Inercia: el modelo se quedó en 2024

**Problema.** Con las 16 regiones apareció un sesgo muy heterogéneo entre
regiones. La correlación entre el sesgo y el cambio real de volumen 2024→2025
es de **−0.66**:

| Región | Sesgo v7 | Volumen real 24→25 |
|---|---|---|
| Atacama | +28.4% | −17.3% |
| O'Higgins | +26.6% | −23.8% |
| Los Lagos | −10.1% | +3.4% |

El modelo aprende los *niveles* de 2024 y los proyecta. Cuando la demanda real
cae, queda alto; cuando sube, queda bajo. El signo del sesgo coincide con la
dirección del cambio real en 14 de 16 regiones.

**Se descartaron con evidencia** otras explicaciones: rotación de
establecimientos (Atacama y O'Higgins tienen 0 estabs nuevos; la caída ocurre
íntegramente en establecimientos comunes), zero-inflation (correlación 0.011) y
sobreajuste (el R2 no correlaciona con el sesgo).

**Decisión.** Cinco features de nivel y tendencia regional, todas con ventanas
que terminan en T−4: `Region_Total_Lag_4`, `Region_Media_28d_lag4`,
`Region_Trend_Ratio`, `Region_Level_vs_Train` (media regional de train 2024,
constante train-only) y `Estab_Media_28d_lag4`.

**Resultado.** MAE 8.550 → **8.009** / R2 0.7378 → 0.7648 / sesgo +5.69% →
+4.17%. El sesgo de Atacama baja +28.4 → +16.3 y el de O'Higgins +26.6 → +17.1.
`Estab_Media_28d_lag4` entra como segunda feature más importante del modelo.

---

## v9 — El día de la semana

**Problema.** El modelo no sabía qué día era. Y el patrón semanal es fuerte y
**estable entre años**: la correlación del perfil 2024 vs 2025 es 0.981
(Hospital 0.991, SAPU 0.987, SAR 0.963, SUR 0.985).

Lo decisivo: **Hospital y SAPU tienen perfiles opuestos**.

| Día | Hospital | SAPU |
|---|---|---|
| Lunes | **1.18×** | 1.07× |
| Viernes | 0.94× | **0.81×** |
| Domingo | 0.92× | **1.21×** |

El hospital concentra la demanda el lunes y cae el sábado; el SAPU es al revés.
Sin la feature del día, el RandomForest promediaba ambos perfiles y perdía la
señal completa.

**Decisión.** `DOW`, `DOW_Sin`/`DOW_Cos` (codificación cíclica), `Es_Finde` y
`DOW_Esperado` = media (establecimiento, día de semana) de TRAIN 2024 con
fallback jerárquico establecimiento → tipo×día → tipo → global.

**Resultado.** MAE 8.009 → **7.236** (−9.7%) / R2 0.7648 → 0.8066. El R2
mejora en las 16 regiones sin excepción. `DOW_Esperado` entra tercera en
importancia.

---

## v10 — Hipótesis de feriados (rechazada con evidencia)

**Hipótesis.** Los feriados mueven la demanda +11-12% de forma estable entre
años (ratio 2024 = 1.106, 2025 = 1.124) y varios de los días de mayor demanda
relativa del año son feriados. Parecía una mejora obvia.

**Implementación.** `Es_Feriado`, `Es_Feriado_Largo`, `Dias_Al_Feriado`
(víspera/resaca) y `Feriado_Irrumpido` (puentes), con el calendario declarado
en el código (Ley 19.973 y 20.215, sin dependencias externas).

**Resultado.** MAE 7.2358 → **7.2514: empeoró**. La prueba directa explica por
qué: el sesgo en días feriados ya era **+0.28%**, contra +4.77% en días
normales. v9 **ya resolvía** los feriados mediante `DOW_Esperado` y las
features de demanda reciente.

**Se conserva el script y su metadata como evidencia** de que la hipótesis se
probó y se descartó con datos, no por intuición.

---

## v11 — El modelo veía un punto, no la serie

**Problema.** Antes de cambiar el algoritmo se midió el techo. Sobre la misma
matriz de features se probaron y **descartaron**:

| Alternativa | MAE | R2 | Veredicto |
|---|---|---|---|
| v9 baseline (RF, MSE) | 7.236 | 0.8066 | referencia |
| RF sobre log1p | 7.199 | 0.7975 | +MAE pero −R2 y sesgo −3.1% |
| HistGradientBoosting L1 | 7.295 | 0.7961 | peor |
| ExtraTrees | 7.298 | 0.8001 | peor |
| RF profundo (hoja=4, mtry=0.5) | 7.394 | 0.7946 | peor |
| HistGradientBoosting L2 | 7.412 | 0.7911 | peor |
| Calibración isotónica | 7.198 | 0.8052 | −0.5% MAE pero −R2 |

Ninguna superó a v9 sin sacrificar R2. Eso estableció que **el techo estaba en
las features, no en el algoritmo**.

El diagnóstico que sí abrió camino: el residuo de v9 tiene **autocorrelación
lag-1 de +0.245** por establecimiento — había estructura temporal sin usar. El
modelo conocía la demanda de hace 4 días (un punto) y la media de 4 semanas. Le
faltaba la **forma** de la serie reciente.

**Decisión.** Ventanas móviles del establecimiento, todas con información ≤ T−4:
`L4..L10` (7 lags consecutivos), `W7_mean/std/min/max`, `W28_std/max`,
`L4_over_L10` y `W7_vs_W28`.

**Resultado.** MAE 7.236 → **6.787** (−6.2%) / RMSE 10.622 → 10.010 /
R2 0.8066 → **0.8283** / sesgo +4.25% → +2.57%. **Las 16 regiones mejoran**
en R2 y en sesgo. Las nuevas features ocupan 7 de los 10 primeros puestos de
importancia, con `W7_mean` como la número uno del modelo.

---

## Estado actual y camino pendiente

- **Versión actual:** **v11** (modelo directo + tendencia regional + patrón
  semanal + ventanas móviles del establecimiento): **MAE 6.787 / RMSE 10.010 /
  R2 0.8283 / sesgo +2.57%** sobre test 2025 (n = 226.003 filas de
  establecimiento-día), con **16/16 regiones** participantes.
- **Referencias superadas:** persistencia pura (MAE 11.074), media histórica
  del establecimiento (10.887), media por día de semana (10.908), sistema de
  dos etapas v5 (14.763) y la exploratoria post-hoc (12.785). El modelo supera
  al mejor baseline trivial en −34%.
- **Scripts:** `reentrenar_modelo_v8_tendencia.py`, `..._v9_calendario.py`,
  `..._v10_feriados.py`, `..._v11_ventanas.py`. Metadata en
  `artifacts/model_metadata_v{8,9,10,11}.json`.
- **Abierto — regresión a la media:** el modelo sobreestima los días de demanda
  muy baja (+121.7% en el quintil inferior) y subestima los picos (−9.2% en el
  quintil superior). Es una propiedad estructural del RandomForest con MSE; se
  probaron alternativas (L1, log1p, calibración) sin mejora neta. La salida
  natural es un enfoque de cuantiles o un clasificador de "día de pico".
- **Abierto — validación externa:** solo dos años de datos (2024-2025). Se
  requiere 2022-2023 para confirmar que la mejora no es específica de este
  split.
- **Abierto — sesgo regional residual:** O'Higgins +9.5% y Atacama +8.0%
  (bajaron fuerte desde +26.6 y +28.4 en v7, pero no cerraron).
- **Abierto — feriados regionales** (20-sep en Coquimbo, 21-may en Iquique):
  no modelados, el dataset no distingue comuna.

Los scripts de cada versión (`src/pipelines/reentrenar_modelo_v*.py`) y la
metadata completa (`artifacts/model_metadata_v*.json`) están versionados para
que este historial sea reproducible. La documentación de entrega, con el
resumen en lenguaje simple y las figuras, está en `ENTREGA/`.
