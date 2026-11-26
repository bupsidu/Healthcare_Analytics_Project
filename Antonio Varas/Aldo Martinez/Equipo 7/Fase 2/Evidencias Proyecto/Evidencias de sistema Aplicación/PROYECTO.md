# PROYECTO — Qué es y cómo funciona

## 1. El problema

Las urgencias respiratorias en Chile tienen picos estacionales (otoño-invierno)
que saturan hospitales y SAPU. La gestión tradicional es **reactiva**: se
refuerza personal cuando el pico ya ocurrió.

Este proyecto entrega un **Sistema de Soporte a la Decisión Clínica (CDSS)** que
anticipa la demanda con **96 horas (4 días)** de margen, por establecimiento y
por día, para que la red asistencial pueda adelantar camas, turnos e insumos.

---

## 2. Datos

| Fuente | Contenido | Cobertura |
|---|---|---|
| **DEIS/MINSAL** | Atenciones de urgencia respiratoria (CIE-10 J00–J99) por establecimiento, fecha y grupo etario | 12.5M atenciones · 657 establecimientos · 16 regiones |
| **SENAMHI/DMC** | Temperatura mínima y máxima diaria por región | 16/16 regiones · 2024 y 2025 completos |
| **Open-Meteo** | Precipitación acumulada diaria (mm) | 16 regiones · 731 días |
| **Open-Meteo Air Quality** | MP2.5 y MP10 diarios | 16 regiones · 731 días |

**Período:** 2024-01-05 → 2025-12-31 · **Split temporal estricto:** train 2024, test 2025.

---

## 3. Fundamento biológico de las features

El modelo no es una caja negra arbitraria: las variables se eligieron por
mecanismos epidemiológicos documentados.

| Feature | Mecanismo |
|---|---|
| `TempMin_Lag_4D` | Incubación viral: el efecto de un frente frío (≤2 °C) aparece ~4 días después |
| `MP2_5_Lag_2D` | El smog y el humo de leña tienen efecto acumulado a 2 días |
| `Frio_Polar_Flag` | Marca días de frío extremo (≤2 °C) |
| `Lluvia_Intensa_Flag` | Precipitación sobre el percentil 90 **de train** (no transductivo) |
| `Alerta_MP25_Flag` | MP2.5 sobre el umbral OMS de 15 μg/m³ |

---

## 4. Arquitectura del modelo (v11)

> Para ver el contraste entre la arquitectura de dos etapas y el modelo único
> actual, con la evolución del error, ver
> [EVOLUCION.md](EVOLUCION.md#vista-general-en-una-imagen).

```
┌─────────────────────────────────────────────────────────────┐
│  FUENTES                                                    │
│  Salud (DEIS) · Temperatura · Precipitación · Contaminación  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  unificar_datos.py                                          │
│  Merge por (Región, Fecha) → clima heredado a cada estab     │
│  Salida: df_unificado.parquet (1.81M filas)                 │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  feature_engineering.py                                     │
│  Lags de CALENDARIO · flags · rolling 7d · estacionalidad    │
│  Salida: df_modelo.parquet (1.77M filas, 27 cols)           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  reentrenar_modelo_v8_tendencia.py                          │
│                                                             │
│  Etapa 1 (regional) ──► Pred_Region                         │
│  Demanda propia     ──► Total_Lag_4, Estab_Media_28d_lag4   │
│  Cuota trailing     ──► Share_Trailing, Pred_E1             │
│  Nivel regional     ──► Region_Media_28d_lag4,              │
│                         Region_Level_vs_Train,              │
│                         Region_Trend_Ratio                  │
│  Patrón semanal     ──► DOW, DOW_Esperado, Es_Finde         │
│  Ventana del estab  ──► L4..L10, W7_mean/std/min/max,       │
│                         W28_std/max, W7_vs_W28              │
│  Contexto            ──► one-hot tipo/región, clima, DOY    │
│                           ▼                                 │
│              RandomForestRegressor (60 features)            │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
              Predicción: Total(establecimiento, día)
                     a 96 horas de horizonte
```

### Por qué un solo modelo y no dos etapas

Las versiones v5/E1 usaban dos etapas: predecir el total regional y luego
repartirlo con una cuota. El diagnóstico mostró que **la Etapa 1 concentraba
~6.4 MAE del error total** y esa cadena propagaba el error hasta el
establecimiento. El modelo directo aprende a corregir ese sistema en lugar de
depender de él, y bajó el MAE de 13.8 a 8.0.

### Anti-leakage

Toda feature se construye con información **≤ T−4**:

- Los lags y medias móviles operan sobre el **calendario**, no sobre filas
  (el dataset tiene ~152 filas por región-fecha por las causas CIE-10).
- `Region_Level_vs_Train` usa una constante calculada **solo con train 2024**.
- `Lluvia_Intensa_Flag` usa el percentil 90 de train, no del dataset completo.
- Hay asserts que fallan si alguna correlación feature-target supera 0.995.

---

## 5. Resultados

Ver **[RESULTADOS.md](RESULTADOS.md)** para el detalle completo, y
**[EVOLUCION.md](EVOLUCION.md)** para entender cómo se llegó acá paso a paso.

| Modelo | MAE | R2 | Sesgo |
|---|---|---|---|
| v7 (16 regiones) | 8.550 | 0.7378 | +5.69% |
| v8 (+ tendencia regional) | 8.009 | 0.7648 | +4.17% |
| v9 (+ patrón semanal) | 7.236 | 0.8066 | +4.25% |
| v11 (+ ventanas del estab) | 6.787 | 0.8283 | +2.57% |
| **v12 (validado en 2026)** | **6.827** | **0.8056** | **+0.45%** |

**Nota sobre v11 vs v12:** el MAE de v12 es apenas mayor porque se valida sobre
2026, un año que el modelo nunca vio, en lugar de 2025. Es una medición más
exigente y más representativa del uso real.

---

## 6. Limitaciones

1. **Tres años de datos** (2024-2026): v12 entrena con 2024-2025 y valida
   sobre 2026. La incorporación de 2022-2023 sigue siendo el siguiente paso.
2. **Split temporal único**: el test es un solo año, así que la comparación
   entre versiones es sólida pero no mide robustez interanual.
3. **Regresión a la media** en los extremos: el modelo sobreestima los días de
   demanda muy baja (+122% en el quintil inferior) y subestima los picos
   (−9.2% en el quintil superior). Es una propiedad estructural del
   RandomForest con MSE. v11 la redujo (desde +134%) pero no la eliminó.
4. **Cobertura de estaciones**: la temperatura es de una estación por región; no
   captura microclimas dentro de la región.
5. **Datos fuente anómalos**: O'Higgins 2025 tiene dos días con valores
   corruptos (−49.1 °C y −32.0 °C), 0.02% del dataset.

---

## 7. Deuda técnica conocida

| Tema | Estado |
|---|---|
| Bug de temperatura SENAMHI (4 regiones sin CSV válido) | ✅ Corregido |
| Normas de nombre de región (NFD/NFC macOS) | ✅ Corregido |
| Fechas con hora en CSV de Valparaíso | ✅ Corregido |
| Inercia al nivel 2024 (sesgo regional) | ✅ Mitigado en v8 (falta cerrar O'Higgins/Atacama) |
| Días corruptos en O'Higgins | ⚠ Pendiente (dato fuente) |
| Datos 2022–2023 | ⚠ Pendiente (no disponibles) |
