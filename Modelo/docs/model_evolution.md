# Evolución del Modelo — v1 a v6

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
| **v6 E2 (actual)** | **Directo, 1 RF a nivel establecimiento** | **9.334** | **0.7231** | **+9.77%** |

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

## v6 — Del sistema de dos etapas al modelo directo (versión actual)

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
| A — Absolutas (v6 actual) | 9.3338 | 13.0481 | 0.7231 | +9.77% |
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
  intacta; es candidato a fix futuro con reindex al calendario, que exige
  reentrenar todas las versiones para mantener la comparación.
- **La contaminación sigue sin aportar:** E2 la excluye de sus features y aun
  así logra el mejor resultado de la serie; el único rol de la contaminación en
  v6 es dentro de `Pred_Region` (config trailing de v5). La hipótesis sigue
  abierta: validarla requiere DEIS 2022–2023.

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

## Estado actual y camino pendiente

- **Versión actual:** **v6** (modelo directo a nivel establecimiento, E2):
  MAE 9.334 / R² 0.7231 / sesgo +9.77%. Documentación en T8; el commit lo
  realiza el usuario.
- **Referencias fuertes que v6 debe seguir superando:** la persistencia pura
  (MAE 11.074 / R² 0.584) y la exploratoria post-hoc (12.785 / 0.3277),
  seleccionada con el test a la vista.
- **Mejor métrica exploratoria previa:** clima + `Anom_TempMin` sin
  contaminación (R² 0.3277 establecimiento / 0.9037 región). *Post-hoc sobre
  test 2025, no validada fuera de este split.*
- **Abierto:** validación con años adicionales (2022–2023) para confirmar que
  la mejora no es específica de este split y para testear la hipótesis de la
  contaminación; fix del lag de clima por calendario (`TempMin_Lag_4D`);
  Atacama; optimización de hiperparámetros de v6 (hasta ahora congelados a los
  de v5 para aislar el efecto de la arquitectura).

Los scripts de cada versión (`src/pipelines/reentrenar_modelo_v*.py`) y la
metadata completa (`artifacts/model_metadata_v*.json`) están versionados para
que este historial sea reproducible.
