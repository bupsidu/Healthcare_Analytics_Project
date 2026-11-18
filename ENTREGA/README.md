# ENTREGA — Sistema de Alerta Temprana MINSAL

**Ignacio Fernández (Nafery)** — ML & Data Science Lead
**Última actualización:** 2026-11-18

---

## 👉 Empezá por acá

| Quiero... | Abrir |
|---|---|
| **Entender cómo evolucionó el modelo, paso a paso** | [**EVOLUCION.md**](EVOLUCION.md) ← *empezá acá* |
| **Entender el proyecto en 5 minutos** | [PROYECTO.md](PROYECTO.md) |
| **Ver los resultados del modelo** | [RESULTADOS.md](RESULTADOS.md) |
| **Ver qué se corrigió y por qué** | [CORRECCIONES.md](CORRECCIONES.md) |
| **Ver los diagramas UML del sistema** | [diagramas/](diagramas/) |
| **Ver las evidencias (logs, métricas)** | [evidencias/](evidencias/) |
| **Ver las figuras para la presentación** | [figuras/](figuras/) |
| **Ver el detalle técnico completo** | [../Modelo/docs/PROJECT_CONTEXT.md](../Modelo/docs/PROJECT_CONTEXT.md) · [../README.md](../README.md) · [../Modelo/docs/model_evolution.md](../Modelo/docs/model_evolution.md) |

---

## 📌 Resumen en 30 segundos

Modelo de **RandomForest** que predice la demanda diaria de urgencias
respiratorias por establecimiento con **96 horas (4 días)** de anticipación.

| | |
|---|---|
| **Modelo vigente** | **v12** (`../Modelo/models/model_rf_directo_v12.joblib`, se regenera) |
| **MAE** | **6.827** atenciones por establecimiento-día |
| **R2** | 0.8056 |
| **Sesgo** | +0.45% |
| **Cobertura** | **16/16 regiones** de Chile |
| **Datos** | 1.77M filas · 657 establecimientos · 12.5M atenciones |
| **Split** | train 2024-2025 / test 2026 (temporal estricto) |

---

## 📂 Estructura de esta carpeta

```
ENTREGA/
├── README.md          ← este archivo (índice)
├── EVOLUCION.md       ← la historia de v1 a v11, explicada simple
├── PROYECTO.md        ← qué es, cómo funciona, arquitectura
├── RESULTADOS.md      ← métricas, comparativas, análisis por región
├── CORRECCIONES.md    ← bugs encontrados y corregidos (evidencia de rigor)
├── diagramas/         ← UML: casos de uso, clases, secuencia, componentes, ER
│   ├── diagramas.md   ← documento con los 5 diagramas + mapa tecnológico
│   ├── base_de_datos.md ← esquema de la base (ER detallado)
│   ├── png/           ← diagramas renderizados en alta resolución
│   └── logos/         ← logos oficiales de las tecnologías (SVG)
├── evidencias/        ← logs de ejecución y artefactos de verificación
└── figuras/           ← gráficos para la presentación
```

### Código y datos (fuera de esta carpeta)

| Ruta | Qué hay |
|---|---|
| `src/pipelines/` | Pipeline completo: consolidación → unificación → features → modelos |
| `data/raw/` | Datos originales sin modificar |
| `data/processed/df_modelo.parquet` | Dataset final de modelado (1.77M filas) |
| `artifacts/` | Metadata de cada versión (versionada) + modelos de región |
| `../Modelo/models/` | Modelos `.joblib` pesados (no versionados; se regeneran) |
| `odd/tasks/` | Bitácora de decisiones técnicas del proyecto |

---

## 🔁 Reproducir desde cero

```bash
# 1. Consolidar temperatura horaria (solo si hay regiones con datos por hora)
python3 src/pipelines/consolidar_temperatura_horaria.py

# 2. Unificar fuentes (salud + clima + contaminación)
python3 src/pipelines/unificar_datos.py

# 3. Generar features
python3 src/pipelines/feature_engineering.py

# 4. Entrenar el modelo vigente (v12)
MODEL_TAG=v12 TRAIN_YEARS=2024,2025 TEST_YEAR=2026 \
  python3 src/pipelines/reentrenar_modelo_v11_ventanas.py
```

Tiempo total: ~2 minutos. Determinístico (semilla 42).
