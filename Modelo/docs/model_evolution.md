# Evolución del Modelo — v1 a v5

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
| **v5 (actual)** | Dos etapas, anomalías trailing | 14.763 | 0.141 | +21.01% |
| v5 sin contaminación | — | 13.285 | 0.1942 | +17.63% |

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

## v5 — Baseline adaptativo *trailing* (versión actual)

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
**+11.3%** — el mejor balance logrado. El frío, medido como anomalía, sí tiene
señal predictiva incremental.

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

---

## Regiones nuevas sin histórico

**Antofagasta y Atacama no existen en train 2024** (bug de los CSV SENAMHI
2024). Concentran los peores errores del sistema, porque la Etapa 1 no tiene
historial de esas regiones. El fallback actual asigna la mediana de cuotas por
tipo de establecimiento. Es un caso conocido y acotado, no un defecto general.

---

## Estado actual y camino pendiente

- **Versión commiteada:** v5 (arquitectura de dos etapas + baseline trailing).
- **Mejor métrica exploratoria:** clima + `Anom_TempMin` sin contaminación
  (R² 0.3277 establecimiento / 0.9037 región). *Post-hoc sobre test 2025, no
  validada fuera de este split.*
- **Decisión abierta:** qué configuración se promueve a oficial, y si se
  incorporan 2022–2023 para validar la hipótesis de la contaminación.

Los scripts de cada versión (`src/pipelines/reentrenar_modelo_v*.py`) y la
metadata completa (`artifacts/model_metadata_v*.json`) están versionados para
que este historial sea reproducible.
