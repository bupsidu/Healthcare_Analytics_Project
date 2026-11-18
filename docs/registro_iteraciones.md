# Registro de Entregas e Iteraciones (Tablero Kanban)
## Sistema de Alerta Temprana en Urgencias Respiratorias (96h)

* **Proyecto:** Healthcare Analytics Project — Demanda Respiratoria a 96h
* **Equipo 7:** Antonia Barrera, Ignacio Fernández, Matías Meneses
* **Asignatura:** Capstone — Duoc UC Sede Antonio Varas
* **Docente Guía:** Aldo Martínez
* **Metodología de Trabajo:** Kanban y CRISP-DM
* **Fecha de Corte:** 18/11/2026

---

## 1. Flujo de Trabajo Kanban

Dado que el equipo gestiona el desarrollo bajo **Kanban** (en conjunto con **CRISP-DM** para el componente analítico), el seguimiento del avance no se organiza en sprints cerrados de duración fija, sino mediante un flujo continuo de entregas estructurado en cuatro estados del tablero:

1. **Por Hacer:** Tareas priorizadas pendientes de iniciar.
2. **En Desarrollo:** Tareas actualmente en ejecución por un integrante o por el equipo.
3. **En Revisión:** Actividades de seguimiento continuo o entregables en validación antes de su cierre.
4. **Terminado:** Tareas que cumplen con los criterios establecidos en el `Definition of Done`.

---

## 2. Resumen de Avance y Desviación del Cronograma

Con fecha de corte **18/11/2026**, el proyecto registra un **atraso leve y controlable de 2 tareas (-6.5 puntos porcentuales)** respecto al avance planificado en la Carta Gantt, compensado parcialmente por el inicio anticipado de las pruebas integrales.

### Indicadores Globales (al 18/11/2026)

| Indicador | Valor | Porcentaje |
|---|---:|---:|
| **Tiempo transcurrido del proyecto** (12/08 al 15/12/2026) | 98 / 125 días | 78.4% |
| **Avance planificado** (tareas que debían terminar antes del 18/11) | 24 / 31 tareas | 77.4% |
| **Avance real** (tareas en estado Terminado) | 22 / 31 tareas | 71.0% |
| **Brecha de cumplimiento (Real vs. Planificado)** | **-2 tareas** | **-6.5 puntos porcentuales (Atraso leve)** |

### Distribución Actual del Tablero Kanban

| Estado en Tablero Kanban | Cantidad de Tareas | Porcentaje |
|---|---:|---:|
| **Terminado** | 22 | 71.0% |
| **En Revisión** | 1 | 3.2% |
| **En Desarrollo** | 3 | 9.7% |
| **Por Hacer** | 5 | 16.1% |
| **Total** | **31** | **100.0%** |

### Avance por Área del Equipo

| Área / Responsable | Terminadas / Total | Avance | Situación frente al cronograma |
|---|---:|---:|---|
| **Ciencia de Datos y Machine Learning** (Ignacio Fernández) | 8 / 8 | 100.0% | Completado en plazo |
| **Backend y Base de Datos** (Matías Meneses) | 6 / 7 | 85.7% | 1 tarea con atraso en desarrollo |
| **Frontend** (Antonia Barrera) | 5 / 7 | 71.4% | 1 tarea con atraso en cierre y 1 inicio diferido |
| **Gestión, Pruebas y Cierre** (Equipo Completo) | 3 / 9 | 33.3% | Pruebas integrales adelantadas; cierre en plazo |

### Detalle de Desviaciones (Atrasos y Adelantos)

* **Tareas con atraso respecto a su fecha de término (2):**
  * **Implementación del reentrenamiento del modelo** (Matías Meneses): estado `En Desarrollo`, fecha de fin planificada `10/11/2026` (**8 días de atraso**).
  * **Integración Frontend-Backend** (Antonia Barrera): estado `En Desarrollo`, fecha de fin planificada `14/11/2026` (**4 días de atraso**).
* **Tarea con inicio diferido dentro de su ventana vigente (1):**
  * **Despliegue Frontend** (Antonia Barrera): estado `Por Hacer`, ventana planificada `15/11/2026` al `21/11/2026` (**3 días de retraso en su inicio**, aún dentro de su plazo límite y sujeta al cierre de la integración Frontend-Backend).
* **Tarea adelantada respecto al cronograma (1):**
  * **Pruebas integrales del sistema** (Equipo Completo): ya en estado `En Desarrollo`, con fecha de inicio planificada `22/11/2026` (**4 días de adelanto**).

---

## 3. Registro de Entregas por Etapa

### Etapa 1: Inicio, Requerimientos y Gestión Continua
*Responsable principal: Equipo Completo*

| Actividad | Prioridad | Responsable | Estado | Inicio | Fin |
|---|---|---|---|---|---|
| Inicio del Proyecto | Primera Prioridad | Equipo Completo | Terminado | 12/08/2026 | 12/08/2026 |
| Levantamiento de requerimientos | Primera Prioridad | Equipo Completo | Terminado | 19/08/2026 | 25/08/2026 |
| Documentación y alcances | Primera Prioridad | Equipo Completo | Terminado | 26/08/2026 | 29/08/2026 |
| Reuniones cada 2 semanas | Primera Prioridad | Equipo Completo | En Revisión | 12/08/2026 | 02/12/2026 |

---

### Etapa 2: Ciencia de Datos y Modelado Predictivo (CRISP-DM)
*Responsable principal: Ignacio Fernández (Machine Learning)*

| Actividad | Prioridad | Responsable | Estado | Inicio | Fin |
|---|---|---|---|---|---|
| Integración de datasets | Primera Prioridad | Ignacio Fernández | Terminado | 30/08/2026 | 02/09/2026 |
| Limpieza y procesamiento de datos | Primera Prioridad | Ignacio Fernández | Terminado | 02/09/2026 | 08/09/2026 |
| Ingeniería de características | Primera Prioridad | Ignacio Fernández | Terminado | 09/09/2026 | 12/09/2026 |
| Generación de variables categóricas | Primera Prioridad | Ignacio Fernández | Terminado | 09/09/2026 | 12/09/2026 |
| Análisis de los datos (EDA) | Primera Prioridad | Ignacio Fernández | Terminado | 09/09/2026 | 15/09/2026 |
| Entrenamiento y comparación de modelos | Primera Prioridad | Ignacio Fernández | Terminado | 13/09/2026 | 22/10/2026 |
| Evaluación y selección del modelo | Primera Prioridad | Ignacio Fernández | Terminado | 23/10/2026 | 26/10/2026 |
| Exportación del modelo predictivo seleccionado | Primera Prioridad | Ignacio Fernández | Terminado | 27/10/2026 | 29/10/2026 |

---

### Etapa 3: Desarrollo Backend, API y Base de Datos
*Responsable principal: Matías Meneses (Backend)*

| Actividad | Prioridad | Responsable | Estado | Inicio | Fin |
|---|---|---|---|---|---|
| Configuración del proyecto FastAPI | Primera Prioridad | Matías Meneses | Terminado | 09/09/2026 | 12/09/2026 |
| Implementación de base de datos | Primera Prioridad | Matías Meneses | Terminado | 20/09/2026 | 26/09/2026 |
| Desarrollo de endpoint de registros e historial | Primera Prioridad | Matías Meneses | Terminado | 27/09/2026 | 03/10/2026 |
| Integración con API de clima y calidad del aire | Primera Prioridad | Matías Meneses | Terminado | 04/10/2026 | 10/10/2026 |
| Desarrollo endpoint de predicción | Primera Prioridad | Matías Meneses | Terminado | 11/10/2026 | 17/10/2026 |
| Implementación de lógica de alertas | Primera Prioridad | Matías Meneses | Terminado | 18/10/2026 | 27/10/2026 |
| Implementación del reentrenamiento del modelo | Primera Prioridad | Matías Meneses | En Desarrollo | 01/11/2026 | 10/11/2026 |

---

### Etapa 4: Desarrollo Frontend e Interfaz Web
*Responsable principal: Antonia Barrera (Frontend)*

| Actividad | Prioridad | Responsable | Estado | Inicio | Fin |
|---|---|---|---|---|---|
| Configuración del proyecto React | Primera Prioridad | Antonia Barrera | Terminado | 30/09/2026 | 03/10/2026 |
| Diseño de estructura de la aplicación | Primera Prioridad | Antonia Barrera | Terminado | 04/10/2026 | 10/10/2026 |
| Desarrollo del formulario de registro | Primera Prioridad | Antonia Barrera | Terminado | 11/10/2026 | 17/10/2026 |
| Desarrollo de sistema de alertas | Primera Prioridad | Antonia Barrera | Terminado | 18/10/2026 | 27/10/2026 |
| Desarrollo de gráficos predictivos | Primera Prioridad | Antonia Barrera | Terminado | 28/10/2026 | 07/11/2026 |
| Integración Frontend-Backend | Primera Prioridad | Antonia Barrera | En Desarrollo | 08/11/2026 | 14/11/2026 |
| Despliegue Frontend | Primera Prioridad | Antonia Barrera | Por Hacer | 15/11/2026 | 21/11/2026 |

---

### Etapa 5: Pruebas Integrales, Documentación y Cierre
*Responsable principal: Equipo Completo*

| Actividad | Prioridad | Responsable | Estado | Inicio | Fin |
|---|---|---|---|---|---|
| Pruebas integrales del sistema | Segunda Prioridad | Equipo Completo | En Desarrollo | 22/11/2026 | 28/11/2026 |
| Corrección de errores finales | Primera Prioridad | Equipo Completo | Por Hacer | 29/11/2026 | 01/12/2026 |
| Documentación final | Primera Prioridad | Equipo Completo | Por Hacer | 29/11/2026 | 05/12/2026 |
| Preparación de presentación y defensa | Primera Prioridad | Equipo Completo | Por Hacer | 06/12/2026 | 08/12/2026 |
| Entrega final del proyecto | Primera Prioridad | Equipo Completo | Por Hacer | 09/12/2026 | 15/12/2026 |

---

## 4. Foco Actual del Tablero (Trabajo en Curso y Próximos Pasos)

* **En Desarrollo (3):**
  * Implementación del reentrenamiento del modelo — Matías Meneses.
  * Integración Frontend-Backend — Antonia Barrera.
  * Pruebas integrales del sistema — Equipo Completo.
* **En Revisión (1):**
  * Reuniones de seguimiento quincenales — Equipo Completo.
* **Por Hacer (5):**
  * Despliegue Frontend — Antonia Barrera.
  * Corrección de errores finales, Documentación final, Preparación de presentación y defensa, y Entrega final del proyecto — Equipo Completo.
