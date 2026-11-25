# Plan de Pruebas de Rendimiento — Backend

* **Proyecto:** Healthcare Analytics Project — Demanda Respiratoria a 96h
* **Equipo 7:** Antonia Barrera, Ignacio Fernández, Matías Meneses
* **Docente Guía:** Aldo Martínez — Capstone, Duoc UC Sede Antonio Varas
* **Fecha de ejecución:** 25 de noviembre de 2026

## 1. Objetivo

Medir cuánto tarda la API, cómo responde con varios usuarios simultáneos y cómo se comporta con uso continuo.

## 2. Alcance

* **Incluye:** la API del backend (FastAPI) y su base de datos (PostgreSQL).
* **No incluye:** el modelo ML, el frontend ni las pruebas de seguridad.
* Solo se hicieron lecturas e inicios de sesión: no se modificaron datos.
* El clima y la proyección dependen de Open-Meteo, un servicio externo, y no se probaron bajo carga.

## 3. Entorno y herramientas

| Elemento | Detalle |
|---|---|
| Equipo | Intel i5-1335U (12 hilos), 8 GB de RAM, Windows 11 |
| API | Uvicorn, un proceso, sin recarga automática, local |
| Base de datos | PostgreSQL 18, local |
| Herramienta | Scripts en Python |

La API, la base de datos y los scripts corrieron en el mismo equipo.

## 4. Criterios de aceptación

* **RNF-06:** cada operación responde en menos de 2 segundos.
* Con carga normal (hasta 50 usuarios simultáneos) no hay errores.
* Durante el uso continuo los tiempos no empeoran.
* **OK:** cumple el criterio. **Error:** no lo cumple.

## 5. Resumen de resultados

| ID | Prueba | Resultado | Estado |
|---|---|---|---|
| RP-01 | Tiempo de respuesta por operación | Todas bajo 2 s | OK |
| RP-02 | Carga: 1, 10, 25 y 50 usuarios | 0 errores; máximo 953 ms | OK |
| RP-03 | Inicios de sesión simultáneos | 0 errores; máximo 1,5 s | OK |
| RP-04 | Duración: 5 minutos continuos | 80.011 solicitudes, 0 errores | OK |

## 6. Casos de prueba

### RP-01: Tiempo de respuesta por operación

**Procedimiento:** un usuario ejecuta cada operación varias veces seguidas.

| Operación | Mediciones | Mínimo | Promedio | Máximo |
|---|---|---|---|---|
| Estado del servicio | 20 | 2 ms | 3 ms | 4 ms |
| Inicio de sesión | 10 | 379 ms | 404 ms | 465 ms |
| Datos del usuario conectado | 20 | 7 ms | 11 ms | 40 ms |
| Catálogo de establecimientos | 20 | 7 ms | 16 ms | 79 ms |
| Historial de atenciones | 20 | 10 ms | 17 ms | 46 ms |
| Demanda diaria | 20 | 10 ms | 14 ms | 43 ms |
| Historial de clima | 20 | 10 ms | 13 ms | 22 ms |
| Historial de predicciones | 20 | 11 ms | 13 ms | 31 ms |
| Clima a 96 h (Open-Meteo) | 5 | 1,40 s | 1,60 s | 1,80 s |
| Proyección a 96 h | 5 | 1,62 s | 1,75 s | 1,88 s |

**Observación:** el clima y la proyección cumplen con poco margen. En una medición anterior del mismo día, desde el navegador, llegaron a 5,2 y 2,9 s. Dependen de la respuesta de Open-Meteo.

### RP-02: Carga con usuarios simultáneos

**Procedimiento:** 200 solicitudes por escenario.

| Operación | Usuarios | Errores | p95 | Máximo | Solicitudes/s |
|---|---|---|---|---|---|
| Historial de atenciones | 1 | 0 | 32 ms | 40 ms | 70 |
| Demanda diaria | 1 | 0 | 14 ms | 22 ms | 84 |
| Historial de atenciones | 10 | 0 | 218 ms | 325 ms | 107 |
| Demanda diaria | 10 | 0 | 256 ms | 493 ms | 86 |
| Historial de atenciones | 25 | 0 | 295 ms | 589 ms | 100 |
| Demanda diaria | 25 | 0 | 352 ms | 523 ms | 103 |
| Historial de atenciones | 50 | 0 | 642 ms | 953 ms | 111 |
| Demanda diaria | 50 | 0 | 707 ms | 953 ms | 100 |

*p95: el 95 % de las solicitudes respondió en ese tiempo o menos.*

### RP-03: Inicios de sesión simultáneos

**Procedimiento:** 60 inicios de sesión por escenario.

| Usuarios | Errores | p95 | Máximo |
|---|---|---|---|
| 1 | 0 | 400 ms | 562 ms |
| 10 | 0 | 621 ms | 675 ms |
| 30 | 0 | 1,39 s | 1,49 s |

El inicio de sesión es la operación local más lenta porque Bcrypt es lento a propósito, para proteger las contraseñas.

### RP-04: Duración

**Procedimiento:** 10 usuarios consultan sin pausa durante 5 minutos.

| Minuto | Solicitudes | Errores | p95 | Máximo |
|---|---|---|---|---|
| 1 | 15.851 | 0 | 50 ms | 200 ms |
| 2 | 15.882 | 0 | 51 ms | 227 ms |
| 3 | 16.264 | 0 | 47 ms | 230 ms |
| 4 | 16.004 | 0 | 49 ms | 201 ms |
| 5 | 16.010 | 0 | 49 ms | 211 ms |

Los tiempos se mantienen estables. La memoria de la API partió en 82 MB y no superó unos 312 MB durante las pruebas.

*Esta prueba reutiliza la conexión, como un navegador; por eso los tiempos son menores que en RP-02, que abre una conexión nueva en cada solicitud.*

## 7. Conclusiones

* La API cumple RNF-06 en condiciones normales y soporta 50 usuarios simultáneos sin errores.
* Con uso continuo no se degrada.
* Las operaciones más lentas dependen de un servicio externo (Open-Meteo).
