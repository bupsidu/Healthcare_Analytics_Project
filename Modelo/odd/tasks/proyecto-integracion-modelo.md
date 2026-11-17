# Task: Pipeline de Integración y Modelado Predictivo MINSAL

## Objetivo
Construir un sistema de predicción de demanda en urgencias respiratorias con 96h de anticipación, escalable a nivel nacional (16 regiones x múltiples establecimientos).

## Arquitectura Modular
1. **unificar_datos.py** — Integra 3 fuentes a nivel establecimiento+fecha
2. **feature_engineering.py** — Lags, flags biológicos, discretización
3. **entrenamiento_modelo.py** — Entrenamiento RandomForest/XGBoost

## Tareas
1. [ ] Crear estructura de carpetas y mover datos raw a data/raw/
2. [ ] Implementar unificar_datos.py (salud + clima + contaminación)
3. [ ] Implementar feature_engineering.py (lags, flags, target encoding)
4. [ ] Crear notebook 01_eda_preparacion_de_datos.ipynb (sin outputs)
5. [ ] Crear notebook 02_modelado_predictivo.ipynb (con outputs)
6. [ ] Implementar entrenamiento_modelo.py (script ejecutable)
7. [ ] Entrenar y exportar model_rf_respiratorio.joblib

## Criterios de Aceptación
- Pipeline reproducible: ejecutar un solo script para generar dataset final
- Modelo entrenable independiente (5 min, sin rehacer EDA)
- Escalable: preparado para extensión multi-target (rango etario)
- Documentado en español (docstrings, README)
