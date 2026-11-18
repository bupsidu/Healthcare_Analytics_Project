# CORRECCIONES — Bugs encontrados y corregidos

Este documento existe porque la defensa técnica de un modelo incluye **saber qué
estaba mal y cómo se detectó**. Cada corrección tiene evidencia verificable.

> Para el relato completo de la evolución (v1 → v11) en lenguaje simple, ver
> [EVOLUCION.md](EVOLUCION.md).

---

## Resumen

| # | Bug | Impacto | Estado |
|---|---|---|---|
| 1 | Lags climáticos sobre filas, no calendario | 97.8% de `TempMin_Lag_4D` era el valor del mismo día | ✅ Corregido (v7) |
| 2 | Rolling de 7 filas ≈ fracción de un día | `Region_Media_7d_*` no medía 7 días | ✅ Corregido (v7) |
| 3 | Umbral de lluvia calculado sobre todo el dataset | Data snooping (usaba test 2025) | ✅ Corregido (v7) |
| 4 | Nombres de región NFD vs NFC (macOS) | 6 regiones sin clima → merge fallido | ✅ Corregido |
| 5 | Alias de región DEIS faltantes | `Del Bíobío`, `De Aisén...` sin normalizar | ✅ Corregido |
| 6 | Fechas con hora en CSV de Valparaíso | 0% de match en el merge (731 vs 731, intersección 0) | ✅ Corregido |
| 7 | CSV de temperatura inexistentes o vacíos | 4 regiones fuera del modelo | ✅ Corregido (datos nuevos) |
| 8 | Inercia al nivel 2024 | Sesgo +28% en 4 regiones | ✅ Mitigado (v8) |
| 9 | Sin patrón semanal | Hospital y SAPU tienen perfiles opuestos; el modelo los promediaba | ✅ Corregido (v9) |
| 10 | Sin forma de la serie reciente | Solo conocía `Total_Lag_4` (1 día) | ✅ Corregido (v11) |
| 11 | Hipótesis feriados | **Rechazada con evidencia** (v10 no mejora) | ⛔ Descartada |

---

## 1–3. Bugs de features climáticas

**Cómo se detectó:** al inspeccionar `df_modelo.parquet` se vio que
`TempMin_Lag_4D` coincidía con `TempMin` del mismo día en el **97.8%** de las
filas. Un lag de 4 días no puede valer lo mismo que el día actual.

**Causa:** el dataset tiene ~152 filas por (Región, Fecha) porque cada fila es
una causa CIE-10 distinta. Un `shift(4)` sobre **filas** avanza 4 filas dentro
del mismo día, no 4 días. Igual con `rolling(7)`: 7 filas son una fracción de
un día.

**Corrección:** construir una serie calendario deduplicada (1 fila por
Región+Fecha), reindexarla al calendario completo y aplicar ahí el lag/rolling,
para luego mergear de vuelta. El tercer bug (umbral de lluvia) se corrigió
calculando el percentil 90 **solo con train 2024**.

**Evidencia:** `evidencias/log_feature_engineering.txt`

---

## 4. Nombres de región NFD vs NFC

**Cómo se detectó:** el modelo cubría solo 8 de 16 regiones. Al medir el % de
`TempMin` no-nulo por región, 8 regiones tenían **0% en ambos años** pese a que
sus CSV de temperatura existían en disco.

**Causa:** macOS entrega los nombres de carpeta en Unicode **NFD**
(`Valparaíso` = `U+0069 U+0301`), pero el `alias_map` del normalizador estaba
escrito en **NFC** (`U+00ED`). El lookup nunca matcheaba y la región quedaba con
el nombre de carpeta crudo, que no coincidía con el nombre DEIS del lado salud.
Resultado: merge de clima fallido → `TempMin` nulo → la región se caía en el
`dropna`.

**Corrección:** `unicodedata.normalize("NFC", ...)` al inicio de
`normalize_region_name()`.

**Evidencia:** `evidencias/auditoria_regiones.txt`

---

## 5. Alias de región faltantes

**Cómo se detectó:** tras el fix NFD/NFC, quedaron 2 regiones sin normalizar.

**Causa:** el DEIS envía `'Del Bíobío'` (con **í** acentuada, no "biobío" con
i) y `'De Aisén del Gral. C. Ibáñez del Campo'`. Ninguna de las dos formas
estaba en el `alias_map`.

**Corrección:** agregar las variantes exactas con sus códigos Unicode.

---

## 6. Fechas con hora en Valparaíso

**Cómo se detectó:** Valparaíso seguía con 0% de clima aunque su CSV tenía 731
días válidos.

**Causa:** su CSV trae `'2024-01-01 15:00'` mientras el resto trae
`'01-01-2024'`. `normalize_date` no truncaba la hora, así que los strings de
clima nunca coincidían con los de salud: **731 fechas de clima vs 731 de salud,
intersección = 0**.

**Corrección:** regex que trunca `[ T]HH:MM(:SS)?`.

**Evidencia:** `evidencias/auditoria_regiones.txt`

---

## 7. CSV de temperatura faltantes o vacíos

**Cómo se detectó:** auditoría archivo por archivo de las 16 carpetas de región.

| Región | Año | Problema encontrado |
|---|---|---|
| Antofagasta | 2024 | archivo inexistente |
| Atacama | 2024 | el archivo era de **precipitación horaria** (`CodigoNacional;Instante;RRR6;Traza`) |
| Los Lagos | 2024, 2025 | columnas `Minima`/`Maxima` **100% vacías** (estación sin registros) |
| Tarapacá | 2024 | archivo inexistente |

**Corrección:** descarga de los registros de SENAMHI y consolidación de datos
**horarios** a resumen diario con
`src/pipelines/consolidar_temperatura_horaria.py` (min/max/media por día).
Los originales horarios se preservaron en `data/raw/_hourly_sources/` y los
archivos inválidos se movieron a `data/raw/_replaced_invalid/`.

**Evidencia:** `evidencias/log_consolidacion_temperatura.txt`

---

## 8. Inercia al nivel 2024 (sesgo regional)

**Cómo se detectó:** con las 16 regiones, el sesgo por región quedó muy
heterogéneo. La correlación entre sesgo y cambio real de volumen 2024→2025 es
**−0.66**: el modelo proyecta los niveles de 2024 y, cuando la demanda cae, queda
alto.

**Lo que se descartó con datos:**

| Hipótesis | Evidencia que la descarta |
|---|---|
| Rotación de establecimientos | Atacama y O'Higgins: 0 estabs nuevos; la caída es 100% en estabs comunes |
| Zero-inflation | correlación sesgo vs % días-cero = 0.011 |
| Sobreajuste | el R2 no correlaciona con el sesgo |

**Corrección (v8):** 5 features de nivel y tendencia regional con ventanas
que terminan en T−4. Resultado: **−12.0 pp de sesgo en Atacama, −10.4 en Ñuble,
−10.2 en Coquimbo, −9.5 en O'Higgins**; 14 de 16 regiones mejoran.

**Evidencia:** `evidencias/metadata_v8.json` (sección `sesgo_por_region_vs_v7`)

---

## 9. Sin patrón semanal (v9)

**Cómo se detectó:** el perfil de demanda por día de la semana correlaciona
**0.981 entre 2024 y 2025** (Hospital 0.991, SAPU 0.987), y los perfiles de
Hospital y SAPU son **opuestos**: Hospital pega el lunes (1.18×) y cae el sábado
(0.86×); SAPU cae el viernes (0.81×) y pega el domingo (1.21×). Sin la feature
de día, el modelo promediaba ambos perfiles.

**Corrección:** `DOW`, `DOW_Sin/Cos`, `Es_Finde` y `DOW_Esperado` (media
estab×dow de train 2024 con fallback jerárquico).
**Resultado:** MAE 8.009 → 7.236 (−9.7%), R2 0.7648 → 0.8066, R2 mejora en
16/16 regiones.

---

## 10. Sin forma de la serie reciente (v11)

**Cómo se detectó:** el residuo de v9 tenía **autocorrelación lag-1 de +0.245**
por establecimiento: había estructura temporal que el modelo no capturaba. El
modelo solo conocía un punto (`Total_Lag_4`) y una media (`Estab_Media_28d_lag4`).

**Antes de cambiar el algoritmo se descartaron** (misma matriz, mismo split):
RF profundo (7.394), ExtraTrees (7.298), HGB L1 (7.295), HGB L2 (7.412),
log1p (7.199 pero −R2) y calibración isotónica (7.198 pero −R2). **El techo
estaba en las features.**

**Corrección:** 7 lags consecutivos (T−4..T−10), estadísticos de ventana de 7 y
28 días, y dos razones de cambio.
**Resultado:** MAE 7.236 → 6.787 (−6.2%), R2 0.8066 → 0.8283, mejora en 16/16
regiones. **7 de las 10 features más importantes son nuevas.**

---

## 11. Hipótesis de feriados (RECHAZADA — se conserva como evidencia)

**Hipótesis:** los feriados mueven la demanda +11-12% de forma estable entre
años (2024 ratio 1.106, 2025 ratio 1.124), así que modelarlos debería mejorar.

**Implementación:** v10 agregó `Es_Feriado`, `Es_Feriado_Largo`,
`Dias_Al_Feriado` y `Feriado_Irrumpido`.

**Resultado:** MAE 7.2358 → **7.2514 (empeoró)**. Y la prueba directa:
el sesgo en feriados ya era **+0.28%** frente a +4.77% en días normales — v9
**ya resolvía** los feriados vía `DOW_Esperado` y las features de demanda
reciente.

**Lección:** una hipótesis plausible y bien fundamentada puede estar ya cubierta
por features existentes. Se conserva v10 en el repo como evidencia de que se
probó y se descartó con datos.

---

## Bugs que quedaron abiertos (transparencia)

| Tema | Por qué no se corrigió |
|---|---|
| Días corruptos en O'Higgins 2025 (−49.1 °C, −32.0 °C) | Es dato fuente del CSV de SENAMHI; imputar inventaría información. Afecta 348 filas (0.02%). |
| Regresión a la media (sobreestima días flojos +122%, subestima picos −9.2%) | Estructural del RF con MSE. Se probaron alternativas (L1, log1p, calibración); ninguna mejora sin sacrificar R2. Requiere enfoque de clasificación de picos o cuantiles. |
| Sesgo residual (O'Higgins +9.5%, Atacama +8.0%) | Bajó fuerte desde +26.6/+28.4, pero no se cerró. |
| Falta validación con 2022–2023 | Los datos no están disponibles en el dataset actual. |
