# 🏥 CONTEXTO Y ESPECIFICACIONES TÉCNICAS DEL PROYECTO DE TÍTULO
**Sistema de Alerta Temprana y Predicción de Demanda en Urgencias Respiratorias (MINSAL Chile)**

---

## 📌 1. Visión e Impacto del Proyecto
* **Cliente / Sponsor:** Ministerio de Salud de Chile (MINSAL) – Subsecretaría de Redes Asistenciales y DEIS.
* **Objetivo:** Pasa de la gestión reactiva tradicional de crisis respiratorias invernales a un **Sistema de Soporte a la Decisión Clínica (CDSS)** con alerta temprana a **96 horas (4 días)**.
* **Cobertura:** 16 regiones administrativas de Chile (años 2024 y 2025).

---

## 🔬 2. Especificaciones de Machine Learning & Data Engineering
* **Integrante a cargo (ML Lead):** Ignacio Fernández (Nafery).
* **Datasets Primarios (4 Fuentes Unificadas):**
  1. *Salud (DEIS/MINSAL):* Atenciones de urgencia respiratoria anonimizadas por establecimiento, fecha y grupo etario (`<1`, `1-4`, `5-14`, `15-64`, `65+`).
  2. *Temperatura (DMC/CR2/SENAMHI):* Mínimas y máximas diarias por región
     (16/16 regiones con cobertura válida en 2024 y 2025; las estaciones que
     faltaban se consolidaron desde registros horarios a resumen diario).
  3. *Precipitaciones (Open-Meteo):* Agua caída acumulada diaria en mm.
  4. *Contaminación Atmosférica (SINCA/Open-Meteo Air Quality):* Concentración diaria de MP2.5 y MP10 en $\mu g/m^3$.
* **Feature Engineering Biológico (Lags):**
  - `TempMin_Lag_4D` (`shift(4)`): Representa la incubación viral de 4 días tras frentes fríos polares ($\le 2^\circ\text{C}$).
  - `MP2_5_Lag_2D` (`shift(2)`): Representa el efecto acumulado de smog/humo de leña.
  - Banderas de riesgo: `Frio_Polar_Flag`, `Lluvia_Intensa_Flag`, `Alerta_MP25_Flag`.
* **Modelos & Evaluación:**
  - Regresión: `RandomForestRegressor` vs `XGBoost` (Métricas: MAE, RMSE, $R^2$, 5-Fold Cross Validation).
  - Clustering Descriptivo: `DBSCAN` para densidad de saturación hospitalaria.
  - Artefacto Exportado: `model_rf_respiratorio.joblib`.

---

## 🏛️ 3. Arquitectura del Sistema (3 Capas Desacoplada + MLOps)
```
[Frontend: React + Tailwind CSS] ──(JSON via Axios)──> [Backend: FastAPI + Pydantic + httpx]
                                                             │
                      ┌──────────────────────────────────────┴──────────────────────────────────────┐
                      ▼                                                                             ▼
          [APIs Clima/Aire: Open-Meteo]                                             [Persistencia: PostgreSQL + SQLAlchemy]
                                                                                                    │
                                                                                                    ▼
                                                                                   [MLOps: Script Re-entrenamiento]
                                                                                                    │
                                                                                                    ▼
                                                                                   [Motor IA: model_rf.joblib]
```

---

## 🛡️ 4. Privacidad y Seguridad (Privacy by Design)
* **Cumplimiento Legal:** Ley N° 20.584 y Ley N° 19.628 de Chile.
* **Anonimización:** Cero datos de identificación personal (PII) o Fichas Clínicas (Sin Nombres, Sin RUT, Sin Direcciones).
* **Captura Triage Rápida:** Entrada táctil anónima (Rango etario + causa respiratoria).
* **Seguridad Web:** Autenticación JWT, Hashing Bcrypt, HTTPS/TLS 1.3, SQLAlchemy ORM.

---

## 👥 5. Equipo y Roles (3 Integrantes)
1. **Integrante 1 (ML & Data Science Lead):** Datasets 2024-2025, Feature Engineering, Random Forest, DBSCAN, `.joblib`.
2. **Integrante 2 (Backend & Database Lead):** FastAPI REST API, PostgreSQL + SQLAlchemy, Open-Meteo HTTP Client, Docker Compose.
3. **Integrante 3 (Frontend & UI/UX Lead):** App Web React, Tailwind CSS, Formulario Triage, Dashboard 96h con Recharts.

---

## 🚀 6. Hoja de Ruta — Estado Actual y Mejoras Futuras

### Estado actual: modelo v11 (directo + ventanas del establecimiento, 16 regiones)
- Predicción del **total** de atenciones respiratorias por establecimiento a 96
  horas con **un solo `RandomForest` a nivel establecimiento** (60 features:
  ventana móvil del establecimiento `L4..L10`/`W7_*`/`W28_*`, patrón semanal
  `DOW_Esperado`, cuota trailing, predicción regional, nivel/tendencia
  regional, one-hot tipo/región, estacionalidad y clima regional sin
  contaminación).
- **Trayectoria**: v8 agregó nivel/tendencia regional (8.009), v9 el patrón
  semanal (7.236), v11 las ventanas móviles del establecimiento.
  Resultado en test 2025:
  **MAE 6.787 / RMSE 10.010 / R2 0.8283 / sesgo +2.57%** (n = 226.003).
- **Cobertura regional completa**: en la versión previa del dataset solo 8
  regiones llegaban al modelo. Antofagasta, Atacama, Los Lagos y Tarapacá
  quedaban fuera porque sus CSV de temperatura 2024 eran inválidos (archivos de
  precipitación horaria mal nombrados, estación sin registros o archivo
  ausente), además de cuatro bugs de normalización en el pipeline
  (NFD/NFC en nombres de carpeta, alias DEIS faltantes, fechas con hora).
  Corregido: hoy las **16 regiones** tienen observaciones de temperatura en
  2024 y 2025 y participan tanto de entrenamiento como de prueba.
- **Snapshots de trazabilidad**: v7 (8.550), v8 (8.009), v9 (7.236), v10
  (7.251, hipótesis de feriados rechazada y conservada como evidencia).
- **Impacto medido del cambio**: v6 E2 (8 regiones) → v11: MAE 9.334 → 6.787
  (−27.3%), R2 0.7231 → 0.8283, sesgo +9.77% → +2.57%, con un set de prueba que
  más que duplicó su tamaño (118.308 → 226.003 filas).

### Mejora 1 — Multi-target por rango etario
- Predecir la demanda por grupo etario (`<1`, `1-4`, `5-14`, `15-64`, `65+`).
- Las columnas ya están preservadas en el dataset; es la extensión más directa.

### Mejora 2 — Tipo de enfermedad
- Predecir la causa o grupo de enfermedad respiratoria (CIE-10 J00-J99).
- **Requisito previo:** análisis exploratorio de frecuencia por causa; el desbalance de
  clases puede volver inútil la predicción en enfermedades raras.
- **Enfoque recomendado:** partir con categorías agrupadas (agudas, crónicas, neumonía)
  en lugar de todas las causas del capítulo J.

### Mejora 3 — Rango etario × enfermedad
- Predicción combinada multidimensional. Es el punto final natural, pero el más complejo.

### Habilitador de precisión (futuro)
- Incorporar datos históricos de urgencias DEIS de **2022 y 2023** para ampliar la serie
  de entrenamiento y mejorar la precisión de las mejoras 1-3.

### Deuda técnica conocida
- **Regresión a la media**: el modelo sobreestima los días de demanda muy baja
  (+121.7% en el quintil inferior) y subestima los picos (−9.2% en el quintil
  superior). Es estructural del RandomForest con MSE; v11 la redujo pero no la
  eliminó. Los feriados NO son el problema (sesgo +0.28% en feriados).
- **Sesgo regional residual**: Atacama +8.0%, O'Higgins +9.5%, Ñuble +6.0%
  (bajaron fuerte desde +28.4/+26.6/+24.9 en v7).
- **Datos fuente anómalos**: el CSV de O'Higgins 2025 contiene dos días
  corruptos (−49.1 °C el 19-feb-2025 y −32.0 °C el 12-ago-2025) que afectan a
  348 filas (0.02% del dataset).
