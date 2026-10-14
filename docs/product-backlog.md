# Product Backlog Priorizado — Sistema de Alerta Temprana

> Artefacto Kanban #2 del anexo metodológico: **Product Backlog priorizado (historias de usuario)**.
> Formato de historia: *Como [rol], quiero [acción], para [beneficio]*.
> Prioridad: **P0** = bloquea el producto · **P1** = calidad y despliegue · **P2** = artefactos de metodología y cierre.
> Estado: ✅ hecho · 🔄 en curso · ⬜ pendiente.

---

## Estado actual (lo que ya está hecho)

| Fase | Actividad | Estado |
|---|---|---|
| 1 | Inicio, levantamiento de requerimientos, documentación y alcances | ✅ |
| 2 | Integración de datos → limpieza → features → EDA → entrenamiento → evaluación → exportación | ✅ **Completa** (modelo v6, MAE 9.33 / R² 0.72 test 2025) |
| 3.0 | Configuración FastAPI (JWT, CORS, OpenAPI) | ✅ |
| 3.1 | Base de datos PostgreSQL (usuarios, establecimientos, ingresos) | ✅ |
| 3.2 | Endpoints de registro e historial de ingresos | ✅ |
| 4.0 | Configuración React + Vite + Tailwind + Recharts | ✅ |
| 4.1 / 4.2 | Estructura de la app / formulario de registro | 🔄 Parcial |
| — | README (raíz, backend, frontend) + documentación de arquitectura y modelo | ✅ / 🔄 |

---

## P0 — Producto funcional

> Sin estas historias no hay sistema que mostrar: conectan el modelo con el usuario.

### P0-1. Endpoint de predicción
> **Como** usuario del sistema, **quiero** consultar la predicción de urgencias respiratorias a 96 horas por establecimiento, **para** anticipar picos de demanda.
- [ ] FastAPI carga el modelo v6 (`model.joblib` + metadata) y expone `POST/GET /prediccion`
- [ ] Respuesta por establecimiento con fecha y valor predicho (96h)
- [ ] Prueba manual: devuelve la misma magnitud que las métricas oficiales
- **Refs:** Gantt 3.4 · `api_flujo.md` (flujo previsto)
- **Responsable sugerido:** Backend

### P0-2. Integración con API de clima y calidad del aire
> **Como** sistema, **quiero** obtener datos de clima y contaminación desde sus fuentes externas, **para** enriquecer las predicciones con contexto ambiental.
- [ ] Servicio en el backend que consulta/clama las fuentes de clima y aire
- [ ] Fallback documentado si la fuente no responde (la ingesta histórica es batch)
- **Refs:** Gantt 3.3
- **Responsable sugerido:** Backend

### P0-3. Lógica de alertas (backend)
> **Como** jefe de urgencias, **quiero** que el sistema evalúe las predicciones contra umbrales y genere alertas, **para** actuar antes del pico.
- [ ] Endpoint de alertas con reglas de umbral configurables
- [ ] Registro de alertas emitidas (historial)
- **Refs:** Gantt 3.5
- **Responsable sugerido:** Backend

### P0-4. Gráficos predictivos (frontend)
> **Como** usuario, **quiero** ver la serie histórica y la proyección a 96h en un gráfico por establecimiento, **para** entender la tendencia de un vistazo.
- [ ] Consumo del endpoint de predicción (reemplaza los datos de prueba hardcodeados)
- [ ] Gráfico con histórico + predicción
- **Refs:** Gantt 4.4
- **Responsable sugerido:** Frontend

### P0-5. Panel de alertas (frontend)
> **Como** usuario, **quiero** ver un panel con las alertas activas, **para** priorizar la atención.
- [ ] Lista de alertas con fecha, establecimiento y severidad
- **Refs:** Gantt 4.3
- **Responsable sugerido:** Frontend

### P0-6. Formulario de registro de ingresos
> **Como** personal de establecimiento, **quiero** registrar los ingresos diarios desde la interfaz, **para** que los datos lleguen a la base sin tocar la API directamente.
- [ ] Formulario completo conectado a `POST /ingresos` con validación y manejo de errores
- **Refs:** Gantt 4.2 (en curso)
- **Responsable sugerido:** Frontend

### P0-7. Integración frontend–backend
> **Como** equipo, **quiero** que la aplicación consuma la API real con autenticación, **para** dejar el modo mock atrás.
- [ ] Login real con JWT guardado, rutas protegidas
- [ ] Todas las pantallas hablando con la API (variables `VITE_API_URL` ya existen)
- **Refs:** Gantt 4.5
- **Responsable sugerido:** Frontend + Backend

---

## P1 — Calidad y despliegue

### P1-1. Reentrenamiento del modelo
> **Como** equipo, **quiero** un proceso de reentrenamiento repetible con datos nuevos, **para** que el modelo no se quede obsoleto.
- [ ] Pipeline ejecutable de reentrenamiento (la base ML ya existe) + trigger documentado
- **Refs:** Gantt 3.6 · `src/pipelines/` (ML)
- **Responsable sugerido:** ML + Backend

### P1-2. Docker y despliegue del sistema
> **Como** evaluador, **quiero** levantar el sistema completo con Docker, **para** verificar que el despliegue es parte del proyecto.
- [ ] Dockerfile(s) backend (+ frontend si aplica)
- [ ] `docker-compose` con API, base de datos y variables de entorno
- [ ] Sección "cómo levantar" en el README
- **Refs:** Anexo elemento 5 · manual kanban #8
- **Responsable sugerido:** Backend

### P1-3. Plan de pruebas + evidencias
> **Como** evaluador, **quiero** pruebas automatizadas con resultados ejecutables, **para** confiar en la calidad del sistema.
- [ ] Unitarias (backend y lógica de alertas)
- [ ] Integración (endpoints + modelo)
- [ ] Rendimiento y seguridad (mínimo documentados)
- **Refs:** Anexo elemento 6 · kanban #7 · Gantt 5.0
- **Responsable sugerido:** Backend (con apoyo ML)

### P1-4. Documento de diseño completo
> **Como** evaluador, **quiero** el diseño formal del sistema, **para** comprender la solución sin leer el código.
- [x] Arquitectura (diagrama, componentes, comunicación) → `docs/arquitectura.md` ✅
- [x] **Modelo de datos:** tablas y diccionario → "Diseño del Proyecto.docx" ✅ (falta diagrama ER visual)
- [ ] **UML mínimos:** casos de uso (pendiente post-presentación), clases, secuencia de la funcionalidad principal, componentes
- [x] **Requisitos no funcionales:** RNF-01 a RNF-05 con criterios → "Especificación del Producto e Innovación.docx" ✅
- **Refs:** Anexo elementos 1–4 (1 ✅, 4 ✅, 2 parcial) · kanban #5
- **Responsable sugerido:** Backend (ER/UML) + equipo

### P1-5. Despliegue del frontend
> **Como** usuario, **quiero** la interfaz publicada y accesible, **para** usar el sistema desde el navegador sin configurar nada local.
- **Refs:** Gantt 4.6
- **Responsable sugerido:** Frontend

### P1-6. Corrección de errores finales
> **Como** equipo, **quiero** una pasada de bugs críticos antes del cierre, **para** que la demo no falle.
- **Refs:** Gantt 5.1 (depende de 5.0)
- **Responsable sugerido:** Todos

---

## P2 — Artefactos de metodología y cierre

### P2-1. Product Vision ✅
> **Como** equipo, **quiero** un documento de 2 páginas con problema, usuarios y propuesta de valor, **para** alinear las decisiones del producto.
- [x] Cubierto por "Especificación del Producto e Innovación.docx" (equipo): problema, usuarios, propuesta de valor
- **Refs:** Kanban #1 · se nutre del README y `PROJECT_CONTEXT.md`
- **Responsable sugerido:** Todos

### P2-2. Sprint Backlogs (por sprint)
> **Como** equipo, **quiero** registrar qué se desarrolló en cada sprint, **para** evidenciar el trabajo ágil.
- **Refs:** Kanban #3
- **Responsable sugerido:** Todos

### P2-3. Definition of Done ✅
> **Como** equipo, **quiero** criterios de aceptación claros por historia, **para** saber cuándo algo está realmente terminado.
- [x] Cubierto por "Especificación del Producto e Innovación.docx": DoD web (frontend/backend) + DoD ML (CRISP-DM)
- **Refs:** Kanban #4 · puede derivarse de esta carta Gantt + anexo
- **Responsable sugerido:** Todos

### P2-4. Evidencia de retrospectivas
> **Como** equipo, **quiero** registro de qué mejoró cada retrospectiva, **para** mostrar mejoras de proceso.
- **Refs:** Kanban #6
- **Responsable sugerido:** Todos

### P2-5. Manual técnico / despliegue
> **Como** evaluador, **quiero** un manual de instalación, variables de entorno y ejecución, **para** reproducir el sistema.
- [ ] Complementar READMEs con variables de entorno y flujo completo (tras P1-2 Docker)
- **Refs:** Kanban #8 · Anexo README obligatorio (README ✅)
- **Responsable sugerido:** Backend

### P2-6. Sección de Innovación (documento final de cierre) ✅
> **Como** equipo, **quiero** responder ¿qué problema resuelve? ¿qué hace diferente? ¿qué valor agrega?, **para** cumplir el requisito de solución innovadora.
- [x] Cubierto por "Especificación del Producto e Innovación.docx": problema, diferencial (96h predictivo vs. reporte semanal reactivo), valor (decisiones logísticas anticipadas)
- **Refs:** Anexo elemento 7
- **Responsable sugerido:** Todos

### P2-7. Documentación final, presentación y defensa
> **Como** equipo, **quiero** cerrar la documentación y preparar la defensa, **para** entregar el proyecto completo.
- **Refs:** Gantt 5.2 · 5.3 · 5.4
- **Responsable sugerido:** Todos

---

## Resumen de cobertura

| Requisito origen | Historias |
|---|---|
| Carta Gantt (faltantes) | 3.3→P0-2 · 3.4→P0-1 · 3.5→P0-3 · 3.6→P1-1 · 4.3→P0-5 · 4.4→P0-4 · 4.5→P0-7 · 4.6→P1-5 · 5.0→P1-3 · 5.1→P1-6 · 5.2/5.3/5.4→P2-7 |
| Anexo elementos comunes | 1→P1-4 ✅ · 2→P1-4 parcial · 3→P1-4 · 4→P1-4 ✅ · 5→P1-2 · 6→P1-3 · 7→P2-6 ✅ · README→✅ |
| Kanban Opción 2 | #1→P2-1 ✅ · #2→este documento ✅ · #3→P2-2 · #4→P2-3 ✅ · #5→P1-4 · #6→P2-4 · #7→P1-3 · #8→P2-5 |
