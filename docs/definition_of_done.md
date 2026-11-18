# Definition of Done (DoD)
## Sistema de Alerta Temprana en Urgencias Respiratorias (96h)

* **Proyecto:** Healthcare Analytics Project — Demanda Respiratoria a 96h
* **Equipo 7:** Antonia Barrera, Ignacio Fernández, Matías Meneses
* **Asignatura:** Capstone — Duoc UC Sede Antonio Varas
* **Docente Guía:** Aldo Martínez
* **Metodología de Trabajo:** Kanban y CRISP-DM

---

Para asegurar un estándar de calidad consistente en todo el proyecto, el **Definition of Done** se divide en dos áreas de trabajo: los entregables de Desarrollo Web (Frontend y Backend) y los entregables de Ciencia de Datos y Machine Learning guiados por las fases de CRISP-DM. Ninguna tarjeta del tablero Kanban puede pasar a la columna **Terminado (Done)** sin cumplir los criterios de su área.

### 1. Criterios de Aceptación para Desarrollo Web (Frontend y Backend)
Una tarea de desarrollo web se considera finalizada únicamente cuando satisface los siguientes puntos:

* **Validación de funcionamiento:** Se comprobó que todas las funcionalidades implementadas (navegación, validaciones, formularios, consumo de APIs y visualización de datos) operen correctamente sin errores en consola ni fallos del servidor.
* **Diseño responsivo y navegación fluida:** Se verifica que la interfaz se adapte de forma correcta a diferentes tamaños de pantalla, asegurando que los botones, tablas y gráficos no presenten desbordamientos ni deformaciones visuales.
* **Pruebas y versionamiento:** Los casos de prueba asociados (unitarios o de integración según corresponda) fueron ejecutados con resultado satisfactorio y los cambios se encuentran integrados en el repositorio Git con mensajes de commit claros.
* **Despliegue verificado en entorno de pruebas:** La funcionalidad se encuentra probada exitosamente fuera del entorno aislado inicial, validando la comunicación real entre Frontend, Backend y base de datos.

### 2. Criterios de Aceptación para Machine Learning y Datos (CRISP-DM)
Una tarea analítica o de modelado predictivo se considera finalizada cuando cumple con los siguientes puntos técnicos:

* **Pipeline de datos reproducible y automatizado:** El script de extracción, limpieza y transformación de datos corre de principio a fin sin interrupciones, gestionando adecuadamente valores nulos o registros faltantes en las series temporales de clima, contaminación y consultas de salud.
* **Rendimiento del modelo validado:** El modelo entrenado supera formalmente la línea base de comparación (baseline), demostrando métricas de error aceptables (MAE, RMSE y $R^2$) frente a estimaciones simples o promedios históricos.
* **Coherencia lógica en las predicciones:** Se verificó que las salidas del modelo entreguen resultados epidemiológicamente coherentes, descartando predicciones anómalas (como valores negativos de consultas médicas o picos numéricos desmedidos).
* **Artefactos y trazabilidad documentada:** El modelo serializado (`.joblib`) y sus metadatos de métricas y variables quedan registrados y documentados para su consumo desde el Backend.
