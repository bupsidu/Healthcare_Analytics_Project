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
  2. *Temperatura (DMC/CR2):* Mínimas y máximas diarias por región.
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

## 🚀 6. Hoja de Ruta — Mejoras Futuras

### Estado actual: modelo v6 (directo a nivel establecimiento)
- Predicción del **total** de atenciones respiratorias a 96 horas con **un solo
  `RandomForest` a nivel establecimiento** (27 features: demanda reciente
  `Total_Lag_4`, cuota trailing, predicción regional, one-hot tipo/región,
  estacionalidad y clima regional sin contaminación). Reemplaza a la v5 de dos
  etapas: MAE **9.334** / R² **0.7231** / sesgo +9.77% vs 14.763 / 0.141 de v5
  (test 2025, nivel establecimiento+día).
- El proceso de iteración v1→v6, sus problemas y correcciones, está documentado
  en [`model_evolution.md`](model_evolution.md); el detalle técnico de la v6
  está en [`model_report.md`](model_report.md).

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
