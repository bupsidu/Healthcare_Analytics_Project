# Catálogo de Historias de Usuario
## Sistema de Alerta Temprana en Urgencias Respiratorias

* **Proyecto:** Healthcare Analytics Project — Demanda Respiratoria a 96h
* **Equipo 7:** Antonia Barrera, Ignacio Fernández, Matías Meneses
* **Asignatura:** Capstone — Duoc UC Sede Antonio Varas
* **Docente Guía:** Aldo Martínez
* **Metodología de Trabajo:** Kanban y CRISP-DM

---

## 1. Introducción y Usuarios Objetivo

El presente documento contiene la especificación formal de las **Historias de Usuario (HU)** prioritarias del Sistema de Alerta Temprana. 

El sistema está enfocado principalmente en los **funcionarios de centros de salud** de la red asistencial. La plataforma responde a dos necesidades operativas clave:
1. **Atención y registro en el box o ventanilla:** Facilitar el ingreso ágil de pacientes respiratorios en triage y la consulta del historial de atenciones del turno sin sobrecarga administrativa.
2. **Planificación y toma de decisiones:** Proveer a los funcionarios responsables de la gestión del centro una proyección de demanda a 96 horas y alertas semafóricas para organizar camas, insumos y refuerzos de personal antes de que ocurra una saturación.

A continuación, se presentan las historias de usuario que componen el flujo principal del sistema bajo el marco de trabajo **Kanban**, indicando los responsables directos dentro del equipo.

---

## 2. Fichas de Historias de Usuario Prioritarias (P0)

---

### HU-01: Autenticación y Carga del Entorno Clínico
* **Código Backlog Maestro:** P0-7 (Integración frontend–backend y autenticación).
* **Prioridad / Clase de Servicio:** P0 (Crítica / Bloqueante).
* **Estado en el Tablero Kanban:** Terminado (Done).
* **Responsables:** Antonia Barrera (Frontend) y Matías Meneses (Backend).

#### Narrativa de Usuario
> **Como** funcionario del centro de salud,  
> **quiero** iniciar sesión en la plataforma con mi correo institucional y contraseña,  
> **para** acceder de manera segura a mi espacio de trabajo con la información de mi establecimiento asignado.

#### Reglas de Negocio
1. Las contraseñas deben almacenarse bajo esquemas de cifrado criptográfico irreversible.
2. La sesión debe mantenerse activa durante la jornada y ser capaz de restaurarse si el funcionario recarga la página.
3. El sistema debe asociar al funcionario directamente con su centro de salud correspondiente.
4. Por seguridad, el sistema no debe revelar si lo que falló fue el correo o la clave al rechazar un intento de acceso.

#### Criterios de Aceptación
* **Criterio 1 (Acceso exitoso):** Al ingresar credenciales correctas, el sistema valida la cuenta, cierra la pantalla de acceso y abre el panel principal mostrando el nombre del funcionario, su rol, el centro de salud y el estado en vivo.
* **Criterio 2 (Validación de campos obligatorios):** Si se presiona el botón de acceso dejando campos en blanco, el sistema detiene el proceso y resalta los campos vacíos con mensajes de advertencia.
* **Criterio 3 (Credenciales erróneas):** Si se ingresa una contraseña no coincidente, la interfaz muestra una alerta visible indicando que las credenciales son incorrectas y deniega el ingreso.
* **Criterio 4 (Persistencia de sesión):** Si el funcionario recarga el navegador con una sesión activa, el sistema la reconoce y mantiene la vista de trabajo sin solicitar credenciales nuevamente.

#### Criterio de Salida (DoD específico)
Casos de prueba CP-01, CP-02, CP-03 y CP-04 del Plan de Pruebas ejecutados con resultado OK.

---

### HU-02: Registro de Atenciones de Urgencia en Triage
* **Código Backlog Maestro:** P0-6 (Formulario de registro de ingresos diarios).
* **Prioridad / Clase de Servicio:** P0 (Crítica).
* **Estado en el Tablero Kanban:** Terminado (Done).
* **Responsables:** Antonia Barrera (Frontend) y Matías Meneses (Backend).

#### Narrativa de Usuario
> **Como** funcionario del centro de salud encargado de la admisión o triage,  
> **quiero** registrar ágilmente cada consulta respiratoria clasificándola por grupo etario y patología sospechosa,  
> **para** mantener actualizada la afluencia operativa del centro sin recopilar información personal que vulnere la privacidad del paciente.

#### Reglas de Negocio
1. **Privacidad y confidencialidad médica (Leyes N° 20.584 y 19.628):** No se solicita ni almacena RUT, nombre, teléfono ni dirección de los pacientes atendidos.
2. **Estandarización edad:** Los rangos etarios corresponden a las categorías oficiales: Menores de 1 año, 1 a 4 años, 5 a 14 años, 15 a 64 años, y 65 años y más.
3. La selección del rango etario es obligatoria para poder registrar la atención.

#### Criterios de Aceptación
* **Criterio 1 (Registro exitoso):** Al seleccionar un rango etario y una enfermedad respiratoria, el sistema guarda la atención en la base de datos, muestra una confirmación en pantalla, restablece el formulario y actualiza la tabla del turno actual.
* **Criterio 2 (Validación obligatoria):** Si se intenta registrar sin seleccionar un rango etario, el sistema bloquea el envío y muestra un mensaje de advertencia bajo los botones de edad.
* **Criterio 3 (Trazabilidad interna):** Cada atención queda vinculada automáticamente a la fecha del día y al centro asistencial correspondiente.

#### Criterio de Salida (DoD específico)
Casos de prueba CP-05, CP-06 y CP-11 del Plan de Pruebas ejecutados con resultado OK.

---

### HU-03: Visualización del Historial de Atenciones del Turno
* **Código Backlog Maestro:** P0-6 (Historial de ingresos diarios).
* **Prioridad / Clase de Servicio:** P0 (Alta).
* **Estado en el Tablero Kanban:** Terminado (Done).
* **Responsables:** Antonia Barrera (Frontend) y Matías Meneses (Backend).

#### Narrativa de Usuario
> **Como** funcionario del centro de salud,  
> **quiero** consultar en una tabla el listado de las atenciones respiratorias ingresadas durante el día en mi establecimiento,  
> **para** monitorear el flujo de pacientes del turno y verificar los registros guardados.

#### Reglas de Negocio
1. **Aislamiento institucional:** Solo se muestran las atenciones pertenecientes al establecimiento del funcionario que tiene la sesión activa.
2. Los registros deben presentarse con su número correlativo, rango etario, diagnóstico y hora de ingreso.

#### Criterios de Aceptación
* **Criterio 1 (Despliegue de registros):** El sistema consulta la base de datos y presenta la tabla con cada atención del día ordenada cronológicamente.
* **Criterio 2 (Manejo de estado vacío):** Si en el día no se han registrado atenciones, el sistema muestra un mensaje informativo indicando que no hay registros para la fecha en el centro.
* **Criterio 3 (Actualización manual):** La interfaz dispone de un control de refresco que permite sincronizar la tabla con la base de datos en cualquier momento.

#### Criterio de Salida (DoD específico)
Caso de prueba CP-07 del Plan de Pruebas ejecutado con resultado OK.

---

### HU-04: Consulta de Condiciones Ambientales en Tiempo Real
* **Código Backlog Maestro:** P0-2 (Integración con API de clima y calidad del aire).
* **Prioridad / Clase de Servicio:** P0 (Alta).
* **Estado en el Tablero Kanban:** Terminado (Done).
* **Responsable:** Matías Meneses (Backend).

#### Narrativa de Usuario
> **Como** funcionario clínico del centro de salud,  
> **quiero** que la plataforma consulte automáticamente el pronóstico del clima y los niveles de contaminación del sector donde se ubica el centro asistencial,  
> **para** correlacionar las bajas temperaturas y la mala calidad del aire con el incremento de consultas respiratorias.

#### Reglas de Negocio
1. La consulta debe realizarse utilizando las coordenadas geográficas de la región correspondiente al establecimiento.
2. Los datos obtenidos deben abarcar una proyección de 96 horas en intervalos horarios adaptados a la zona horaria local.
3. El sistema debe tolerar demoras o caídas del servicio meteorológico externo sin interrumpir la operación del servidor hospitalario.

#### Criterios de Aceptación
* **Criterio 1 (Obtención horaria):** El sistema retorna registros que incluyen temperatura ambiente, precipitaciones acumuladas y concentración de material particulado.
* **Criterio 2 (Manejo de contingencias externas):** Si el proveedor meteorológico excede el tiempo límite de espera, el sistema responde de forma controlada indicando la indisponibilidad temporal sin colapsar el servicio.

#### Criterio de Salida (DoD específico)
Caso de prueba CP-08 del Plan de Pruebas ejecutado con resultado OK.

---

### HU-05: Inferencia Predictiva de Demanda Respiratoria a 96 Horas
* **Código Backlog Maestro:** P0-1 (Endpoint de predicción hospitalaria).
* **Prioridad / Clase de Servicio:** P0 (Crítica).
* **Estado en el Tablero Kanban:** En desarrollo (In Progress).
* **Responsables:** Ignacio Fernández (Modelo ML) y Matías Meneses (Backend).

#### Narrativa de Usuario
> **Como** funcionario a cargo de la gestión o jefatura del centro de salud,  
> **quiero** consultar la cantidad estimada de atenciones respiratorias que recibirá mi establecimiento dentro de las próximas 96 horas,  
> **para** planificar con anticipación la dotación de personal médico, insumos y disponibilidad de camas antes de que ocurra la saturación.

#### Reglas de Negocio
1. **Anticipación biológica:** El horizonte de predicción es de 96 horas (4 días), correspondiente a la ventana de incubación viral tras eventos de frío polar y polución.
2. La predicción debe devolver siempre un número entero no negativo de pacientes.
3. Cada predicción calculada debe quedar registrada en la base de datos para trazabilidad y auditoría.

#### Criterios de Aceptación
* **Criterio 1 (Generación de predicción):** A partir del historial de demanda del establecimiento y de las condiciones climáticas pronosticadas, el modelo calcula el volumen estimado de atenciones.
* **Criterio 2 (Registro histórico):** La estimación calculada se asocia al establecimiento y a la fecha consultada, quedando disponible para su consulta posterior.

#### Criterio de Salida (DoD específico)
Caso de prueba CP-09 del Plan de Pruebas ejecutado y validado de extremo a extremo.

---

### HU-06: Visualización Gráfica de Tendencia y Panel de Demanda en Dashboard
* **Código Backlog Maestro:** P0-4 y P0-5 (Gráficos predictivos y panel de monitoreo en Frontend).
* **Prioridad / Clase de Servicio:** P0 (Alta).
* **Estado en el Tablero Kanban:** En desarrollo (In Progress).
* **Responsable:** Antonia Barrera (Frontend).

#### Narrativa de Usuario
> **Como** funcionario a cargo de la gestión del centro de salud,  
> **quiero** visualizar en un gráfico interactivo la serie histórica de atenciones cruzada con la proyección a 96 horas y tarjetas de resumen,  
> **para** comprender la tendencia de demanda y el contexto ambiental de un solo vistazo.

#### Reglas de Negocio
1. El gráfico debe diferenciar visualmente los datos reales del historial reciente de la curva proyectada hacia el futuro.
2. El panel debe incorporar tarjetas informativas con la afluencia proyectada de hoy, el pronóstico térmico y la calidad del aire.

#### Criterios de Aceptación
* **Criterio 1 (Curva temporal):** Despliegue de un gráfico continuo con la serie histórica y la extensión a 96 horas proyectada por el modelo.
* **Criterio 2 (Indicadores clave):** Tarjetas superiores que muestran la demanda esperada, la temperatura mínima prevista y el nivel de riesgo ambiental.

#### Criterio de Salida (DoD específico)
Caso de prueba CP-12 del Plan de Pruebas verificado en la interfaz web.

---

## 3. Matriz de Trazabilidad (Historias vs. Pruebas)

| Código Historia | Módulo Funcional | Responsable Directo | Tarea en Backlog | Estado en Kanban | Caso de Prueba Asociado |
|---|---|---|---|---|---|
| **HU-01** | Autenticación y Acceso | Antonia Barrera (Frontend) y Matías Meneses (Backend) | P0-7 | Terminado (Done) | CP-01, CP-02, CP-03, CP-04 |
| **HU-02** | Registro en Triage | Antonia Barrera (Frontend) y Matías Meneses (Backend) | P0-6 | Terminado (Done) | CP-05, CP-06, CP-11 |
| **HU-03** | Historial de Atenciones | Antonia Barrera (Frontend) y Matías Meneses (Backend) | P0-6 | Terminado (Done) | CP-07 |
| **HU-04** | Clima y Contaminación | Matías Meneses (Backend) | P0-2 | Terminado (Done) | CP-08 |
| **HU-05** | Inferencia Predictiva 96h | Ignacio Fernández (Modelo ML) y Matías Meneses (Backend) | P0-1 | En desarrollo | CP-09 |
| **HU-06** | Dashboard Gráfico | Antonia Barrera (Frontend) | P0-4, P0-5 | En desarrollo | CP-12 |
