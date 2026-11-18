# RESULTADOS — Métricas y análisis

**Modelo vigente:** v11 · **Evaluación:** test 2025 (226.003 filas de
establecimiento-día) · **Semilla:** 42

> Si querés el relato simple de cómo se llegó acá (sin métricas ni jerga),
> leé [EVOLUCION.md](EVOLUCION.md). Este documento es la evidencia numérica.

---

## 1. Métricas globales

| Métrica | Valor | Cómo leerlo |
|---|---|---|
| **MAE** | **6.787** | error promedio de ~7 atenciones por establecimiento-día |
| **RMSE** | 10.010 | penaliza más los errores grandes |
| **R2** | 0.8283 | explica el 82.8% de la varianza |
| **Sesgo** | +2.57% | sobreestima levemente el total agregado |
| **n** | 226.003 | filas de test (estab-día, causas sumadas) |

Para referencia: la demanda media por establecimiento-día es ~25 atenciones,
así que un MAE de 6.79 representa ~27% del nivel típico.

**Baselines triviales de comparación** (mismo split):

| Baseline | MAE |
|---|---|
| Persistencia lag-4 | 10.289 |
| Media del establecimiento | 10.887 |
| Media por día de semana | 10.908 |

El modelo supera al mejor baseline trivial en **−34%**.

---

## 2. Evolución de las versiones

| Versión | Arquitectura | MAE | R2 | Sesgo |
|---|---|---|---|---|
| v5 trailing | dos etapas (cuota fija) | 14.763 | 0.1410 | +21.0% |
| v6 E1 | dos etapas (cuota trailing) | 13.808 | 0.1939 | +21.7% |
| v6 E2 | directo, 8 regiones | 9.334 | 0.7231 | +9.77% |
| v7 | directo, 16 regiones | 8.550 | 0.7378 | +5.69% |
| v8 | + tendencia regional | 8.009 | 0.7648 | +4.17% |
| v9 | + patrón semanal | 7.236 | 0.8066 | +4.25% |
| **v11** | + ventanas del estab | **6.787** | **0.8283** | **+2.57%** |

**Mejora acumulada v5 → v11: −54.0% en MAE.**

### Qué aportó cada salto

1. **v5 → v6 E2 (−36.8%)**: abandonar las dos etapas. La Etapa 1 regional
   concentraba el error y lo propagaba.
2. **v6 E2 → v7 (−8.4%)**: pasar de 8 a 16 regiones y corregir 3 bugs de
   features climáticas (lags sobre filas en vez de calendario).
3. **v7 → v8 (−6.3%)**: features de nivel y tendencia regional.
4. **v8 → v9 (−9.7%)**: patrón semanal. Los perfiles de Hospital y SAPU son
   opuestos (Hospital pega el lunes, SAPU el domingo) y el modelo los promediaba.
5. **v9 → v11 (−6.2%)**: ventanas móviles del establecimiento. Los 7 lags
   consecutivos y los estadísticos de la ventana de 7/28 días capturan la forma
   de la serie reciente, que `Total_Lag_4` solo no daba.

---

## 3. Métricas por región (v11)

| Región | MAE | R2 | Sesgo | Estabs |
|---|---|---|---|---|
| Arica y Parinacota | 8.194 | 0.904 | +3.4% | 5 |
| Maule | 6.556 | 0.879 | +1.9% | 59 |
| Tarapacá | 5.885 | 0.875 | +2.9% | 20 |
| Aysén | 6.395 | 0.871 | -1.0% | 6 |
| Ñuble | 5.349 | 0.849 | +6.0% | 29 |
| Los Lagos | 6.296 | 0.845 | -2.5% | 44 |
| Biobío | 7.639 | 0.828 | +3.0% | 68 |
| Metropolitana | 8.005 | 0.809 | +1.9% | 152 |
| Valparaíso | 6.156 | 0.807 | +3.4% | 78 |
| Los Ríos | 5.768 | 0.804 | +2.6% | 31 |
| Antofagasta | 6.168 | 0.800 | +2.3% | 21 |
| Magallanes | 5.761 | 0.788 | +4.4% | 9 |
| Atacama | 6.512 | 0.724 | +8.0% | 15 |
| O'Higgins | 6.088 | 0.709 | +9.5% | 44 |
| Coquimbo | 5.809 | 0.707 | +4.9% | 34 |
| La Araucanía | 6.738 | 0.655 | +0.1% | 42 |

**Lectura:** todas las regiones mejoraron respecto de v9, tanto en R2 como en
sesgo. Metropolitana mantiene el MAE absoluto más alto (8.005) porque es la
región más grande (152 establecimientos, 432K filas), pero su sesgo es mínimo
(+1.9%). La Araucanía tiene el R2 más bajo (0.655) pero también el sesgo más
bajo (+0.1%): predice bien en promedio, con más dispersión día a día.

---

## 4. El problema del sesgo regional y cómo se atacó

### Diagnóstico (v7)

El sesgo por región correlacionaba **−0.66** con el cambio real de volumen
2024→2025:

| Región | Sesgo v7 | Volumen real 24→25 |
|---|---|---|
| Atacama | +28.4% | **−17.3%** |
| O'Higgins | +26.6% | **−23.8%** |
| Ñuble | +24.9% | −9.0% |
| Coquimbo | +22.2% | −8.9% |
| Los Lagos | **−10.1%** | **+3.4%** |

**Causa:** el modelo aprende los *niveles* de 2024 y los proyecta. Cuando la
demanda real cae, el modelo queda alto. Cuando sube (Los Lagos), queda bajo. El
signo del sesgo coincide con la dirección del cambio real en 14 de 16 regiones.

**Lo que se descartó con evidencia:**

- ❌ Rotación de establecimientos: Atacama y O'Higgins tienen 0 estabs nuevos;
  la caída está íntegramente en establecimientos comunes.
- ❌ Zero-inflation: correlación sesgo vs % días-cero = **0.011**.
- ❌ Sobreajuste: el R2 no correlaciona con el sesgo.

### Solución (v8)

Cinco features nuevas, todas con ventanas que terminan en T−4:

| Feature | Qué informa |
|---|---|
| `Region_Total_Lag_4` | total regional de hace 4 días |
| `Region_Media_28d_lag4` | nivel regional de las últimas 4 semanas |
| `Region_Trend_Ratio` | si la región viene subiendo o bajando |
| `Region_Level_vs_Train` | nivel actual vs nivel 2024 (la señal clave) |
| `Estab_Media_28d_lag4` | versión estable de la demanda del establecimiento |

### Resultado

| Región | Sesgo v7 | Sesgo v8 | Δ |
|---|---|---|---|
| Ñuble | +24.9% | +14.4% | **−10.4 pp** |
| Coquimbo | +22.2% | +12.1% | **−10.2 pp** |
| Atacama | +28.4% | +16.3% | **−12.0 pp** |
| O'Higgins | +26.6% | +17.1% | **−9.5 pp** |
| Arica y Parinacota | +11.5% | +6.2% | −5.3 pp |
| Magallanes | +11.7% | +6.4% | −5.3 pp |
| Los Lagos | −10.1% | −6.2% | +3.9 pp |

**Reducción media de |sesgo|: 4.30 pp · 14 de 16 regiones mejoran.**

---

## 5. Importancia de features (v11)

| Feature | Importancia | Tipo |
|---|---|---|
| **W7_mean** | **0.1219** | ventana media 7d (v11) |
| **L7** | **0.1119** | lag T−7 (v11) |
| **W7_min** | **0.0914** | ventana mínimo 7d (v11) |
| **L6** | **0.0905** | lag T−6 (v11) |
| **W7_max** | **0.0841** | ventana máximo 7d (v11) |
| Pred_E1 | 0.0680 | sistema dos etapas |
| **L8** | **0.0637** | lag T−8 (v11) |
| **L4** | **0.0598** | lag T−4 (v11) |
| DOW_Esperado | 0.0498 | patrón semanal (v9) |
| Estab_Media_28d_lag4 | 0.0448 | tendencia (v8) |
| **L5** | **0.0404** | lag T−5 (v11) |
| Total_Lag_4 | 0.0315 | demanda a 4 días |

**Las 7 de las 10 features más importantes son nuevas de v11.** Eso confirma
el diagnóstico: el modelo carecía de la *forma* de la serie reciente, no de
algoritmo.

---

## 5b. Exploración de mejoras: qué se probó y qué se descartó

Cada una de estas pruebas corrió sobre la misma matriz y el mismo split.
Documentarlas es parte del rigor: saber qué NO funciona evita repetirlo.

### Baselines triviales (¿el modelo aporta algo?)

| Baseline | MAE |
|---|---|
| Persistencia lag-4 | 10.289 |
| Media del establecimiento | 10.887 |
| Media por día de semana | 10.908 |

El modelo supera al mejor baseline por **−34%**.

### Cambios de algoritmo (todos descartados)

| Modelo | MAE | R2 | Veredicto |
|---|---|---|---|
| v9 baseline (RF, MSE) | 7.236 | 0.8066 | referencia |
| RF log1p | 7.199 | 0.7975 | +MAE pero −R2 y sesgo −3.1% |
| HGB L1 (absolute_error) | 7.295 | 0.7961 | peor |
| ExtraTrees | 7.298 | 0.8001 | peor |
| RF profundo | 7.394 | 0.7946 | peor |
| HGB L2 | 7.412 | 0.7911 | peor |

Conclusión: el techo estaba en las features, no en el algoritmo.

### Calibración post-hoc (descartada)

| Variante | MAE | R2 | Sesgo |
|---|---|---|---|
| v9 sin calibrar | 7.236 | 0.8066 | +4.25% |
| + isotónica | 7.198 | 0.8052 | +3.95% |
| + lineal a+b·p | 7.240 | 0.8050 | +4.10% |

La regresión a la media no se corrige post-hoc sin perder R2.

### Hipótesis feriados (rechazada con evidencia)

Los feriados mueven +11-12% la demanda de forma estable entre años, **pero v9 ya
los resolvía**: el sesgo en feriados era +0.28% frente a +4.77% en días
normales. v10 (con 4 features de feriado) dio MAE 7.2514, **peor** que v9.
Hipótesis descartada, registro conservado.

### Hiperparámetros (rechazado por riesgo metodológico)

La búsqueda `leaf ∈ {8,10,12,15,20} × n_estimators ∈ {300,400,600}` encontró un
máximo en `leaf=8, n=600` con MAE 6.7733 frente a 6.7874. **Diferencia: 0.014
(0.2%), que es ruido.** Además, ajustar hiperparámetros mirando el test es
hacer trampa: no se valida nada, se memoriza. Se mantienen los hiperparámetros
históricos.

---

## 6. Verificación anti-leakage

| Chequeo | Resultado |
|---|---|
| Target en el set de features | ❌ No |
| Correlación `Total_Lag_4` vs `Total` | 0.8020 (fuga si > 0.99) |
| Correlación de cada feature nueva vs target | todas < 0.995 (assert) |
| R2 > 0.9 (sospechoso de fuga) | ❌ No (0.7648) |
| `Region_Level_vs_Train` | constante calculada solo con train 2024 |
| Ventanas temporales | todas terminan en T−4 |

---

## 7. Artefactos

| Archivo | Contenido | ¿En el repo? |
|---|---|---|
| `artifacts/model_metadata_v11.json` | Métricas, features, verificación, limitaciones | ✅ versionado |
| `artifacts/model_rf_region_v7.joblib` | Etapa 1 regional (proveedor de `Pred_Region`) | ✅ versionado (1.3 MB) |
| `artifacts/model_metadata_v8/v9/v10.json` | Metadata de versiones previas | ✅ versionado |
| `../models/model_rf_directo_v11.joblib` | Modelo vigente (60 features, 200 árboles) | ❌ 90 MB — se regenera |
| `data/processed/df_modelo.parquet` | Dataset de modelado (1.77M filas) | ❌ — se regenera |

**Sobre los modelos `.joblib`:** los modelos directos pesan entre 45 y 90 MB y el
repositorio no los versiona. Se regeneran ejecutando el script de su versión
(ver [README de ENTREGA](README.md#-reproducir-desde-cero)). Lo que sí se
versiona como evidencia es la **metadata** (métricas, features, verificación) y
el modelo de la Etapa 1 regional, que es liviano y necesario para reproducir
`Pred_Region`.

---

## 8. Regresión a la media: la limitación que queda

Es la propiedad más importante a entender del modelo actual.

| Quintil de demanda real | n | Sesgo v9 | Sesgo v11 |
|---|---|---|---|
| p0-20 (días flojos) | 46.381 | +134.1% | **+121.7%** |
| p20-40 | 46.095 | +32.0% | +26.8% |
| p40-60 | 45.008 | +13.7% | +10.5% |
| p60-80 | 43.836 | +3.0% | +1.3% |
| p80-100 (picos) | 44.683 | −9.2% | −9.2% |

**Qué significa:** el RandomForest minimiza error cuadrático, y eso lo empuja a
predecir cerca del promedio. Cuando la demanda real es muy baja, sobreestima;
cuando es un pico, subestima.

**Por qué no es un bug:** es el comportamiento óptimo para MSE. Cambiar a un
objetivo L1 (probar HGB con `absolute_error`) mejoró el sesgo pero empeoró el
MAE global, porque el dataset tiene muchos valores cerca de cero.

**Qué se puede hacer a futuro:**
1. Modelo de clasificación de "día de pico" en paralelo al regresor.
2. Objetivo de cuantil (predecir el p90 en vez de la media) si el uso clínico
   es dimensionar capacidad: para planificar camas, el cuantil alto es más útil
   que la media.
3. Datos de 2022-2023 para estabilizar la estimación del nivel.

**Para la operación práctica:** cuando el modelo predice bajo, el error
absoluto es chico (MAE 3.8 en el quintil inferior). El riesgo operativo está en
los picos, donde el MAE es 12.0 y el modelo subestima 9%. Es decir, el sistema
es conservador donde importa: nunca sobre-reacciona, pero puede quedarse corto
en un brote grande.
