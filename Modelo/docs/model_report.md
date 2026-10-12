# Reporte del modelo v1

## Objetivo
Predecir la demanda diaria en urgencias respiratorias por establecimiento, con 96 horas de anticipación.

## Datos
- Entrenamiento: 2024
- Prueba: 2025
- Nivel: establecimiento + fecha
- Regiones: 8
- Establecimientos: 339

## Resultados
- MAE: 0.321
- RMSE: 0.980
- R2: 0.9956
- CV MAE registrado: 0.608 ± 0.300

## Evidencia incluida
- model_rf_respiratorio.joblib
- model_metadata.json
- features.json
- sample_predictions.csv

## Limitaciones
- El modelo depende de datos climáticos y de contaminación a nivel regional.
- Para inferencia se deben usar las mismas features y codificaciones.
