# Plan de Pruebas y Evidencias de Aseguramiento de Calidad (QA)
## Sistema de Alerta Temprana en Urgencias Respiratorias

* **Proyecto:** Healthcare Analytics Project — Demanda Respiratoria a 96h
* **Equipo 7:** Antonia Barrera, Ignacio Fernández, Matías Meneses
* **Asignatura:** Capstone — Duoc UC Sede Antonio Varas
* **Docente Guía:** Aldo Martínez
* **Metodología de Trabajo:** Kanban y CRISP-DM

---

## 1. Introducción

La finalidad del Plan de Pruebas y Aseguramiento de Calidad (QA) del Sistema de Alerta Temprana para la predicción de demanda en urgencias respiratorias es planificar, estructurar y evidenciar los procedimientos de prueba aplicados sobre la solución de software, garantizando que los módulos desarrollados cumplan con los requerimientos clínicos y funcionales comprometidos en el Product Backlog.

### 1.1 Alcance del Plan
El alcance de este plan contempla:
1. **Pruebas Funcionales de Integración e Interfaz:** Derivadas directamente de las Historias de Usuario prioritarias (P0), abarcando el flujo de inicio de sesión del personal de salud, el módulo de captura de atenciones en Triage, la consulta en tiempo real de condiciones ambientales mediante Open-Meteo y la inferencia predictiva a 96 horas.
2. **Pruebas de Seguridad y Privacidad Clínica:** Validación del cifrado de contraseñas y certificación de cumplimiento de la legislación chilena (Leyes N° 20.584 y 19.628) respecto al no almacenamiento de datos de identificación personal de los pacientes.

### 1.2 Criterios de Estado de las Pruebas
Para la calificación del estado de cada caso de prueba se adoptan tres estados formales:
* **OK:** El caso de prueba fue ejecutado manualmente y su resultado coincide plenamente con el comportamiento esperado y visible en el sistema.
* **Error:** La prueba fue ejecutada y se detectó una discrepancia, fallo o comportamiento anómalo que requiere corrección.
* **No ejecutada:** Funcionalidad planificada en el backlog que se encuentra en fase de integración o pendiente de despliegue final en la interfaz.

---

## 2. Entorno y Herramientas de Pruebas Manuales

Las pruebas fueron ejecutadas de forma manual en un entorno local de desarrollo utilizando las siguientes herramientas:

* **Navegador Web:** Utilizado para interactuar directamente con la interfaz de usuario, completando formularios, navegando entre vistas y verificando los mensajes y validaciones del sistema.
* **Herramientas de Desarrollador del Navegador:** Utilizadas para verificar la persistencia de la sesión en el almacenamiento local del cliente y comprobar el correcto intercambio de información con el servidor.
* **Administrador de Base de Datos:** Utilizado para consultar directamente las tablas del sistema y comprobar que los datos se almacenen de forma íntegra, con contraseñas encriptadas y sin datos personales.
* **Terminal de Ejecución:** Utilizada para iniciar los servicios del sistema y observar el comportamiento general y registros operativos durante las pruebas.

---

## 3. Matriz de Casos de Prueba

---

### CP-01: Inicio de sesión exitoso y cambio al panel principal
* **Historia de Usuario:** P0-7 (Integración frontend–backend y autenticación).
* **Tipo de Prueba:** Integración (Frontend / Backend / Base de Datos).
* **Precondición:** Servidor y base de datos en funcionamiento. Existe un usuario activo registrado con credenciales autorizadas.
* **Datos de Entrada:**
  * Correo: `[Correo institucional de un usuario activo]`
  * Contraseña: `[Contraseña válida asociada a la cuenta]`
* **Pasos de Ejecución:**
  1. Ingresar el correo del funcionario en el campo "Correo Institucional".
  2. Ingresar la contraseña correspondiente en el campo "Contraseña".
  3. Presionar el botón "Iniciar Sesión".
* **Resultado Esperado:**
  * El sistema valida las credenciales y autoriza el acceso de forma inmediata.
  * La pantalla de acceso se cierra y se despliega el panel principal del centro de salud.
  * En la barra superior se visualiza la identificación del usuario, su rol asignado y el nombre del establecimiento de salud.
  * Se activa el indicador de estado en vivo con la hora local sincronizada.
* **Estado:** OK

---

### CP-02: Validación local en Frontend de campos obligatorios en Login
* **Historia de Usuario:** P0-7 (Validación de interfaz de acceso).
* **Tipo de Prueba:** Unitaria / Validación de interfaz (Frontend).
* **Precondición:** El usuario se encuentra en el formulario de inicio de sesión con los campos limpios.
* **Datos de Entrada:**
  * Correo: ` ` (vacío)
  * Contraseña: ` ` (vacía)
* **Pasos de Ejecución:**
  1. Dejar ambos campos sin texto.
  2. Presionar el botón "Iniciar Sesión".
* **Resultado Esperado:**
  * El sistema detiene el proceso antes de realizar cualquier envío al servidor.
  * Los campos requeridos se resaltan visualmente en color de advertencia.
  * Bajo cada campo se despliegan mensajes claros indicando que el correo institucional y la contraseña son obligatorios.
* **Estado:** OK

---

### CP-03: Rechazo de credenciales incorrectas en inicio de sesión
* **Historia de Usuario:** P0-7 (Seguridad de autenticación).
* **Tipo de Prueba:** Integración (Frontend / Backend / Seguridad).
* **Precondición:** El usuario se encuentra en la pantalla de inicio de sesión.
* **Datos de Entrada:**
  * Correo: `[Correo institucional registrado]`
  * Contraseña: `[Contraseña incorrecta / no coincidente]`
* **Pasos de Ejecución:**
  1. Ingresar el correo del funcionario.
  2. Ingresar una contraseña que no coincida con la registrada.
  3. Presionar "Iniciar Sesión".
* **Resultado Esperado:**
  * El servidor rechaza la solicitud al no coincidir la clave con el registro encriptado.
  * La interfaz mantiene al usuario en la pantalla de acceso y despliega una alerta visible indicando que las credenciales son incorrectas.
  * No se guarda sesión en el navegador ni se permite el ingreso al panel hospitalario.
* **Estado:** OK

---

### CP-04: Persistencia de sesión activa al recargar el navegador
* **Historia de Usuario:** P0-7 (Persistencia de sesión en cliente).
* **Tipo de Prueba:** Integración (Frontend / Almacenamiento local).
* **Precondición:** El usuario ha iniciado sesión previamente y cuenta con una sesión activa en el navegador.
* **Datos de Entrada:** Acción de recargar página (F5 o botón de recarga del navegador).
* **Pasos de Ejecución:**
  1. Estando dentro del panel clínico, presionar F5 en el teclado.
* **Resultado Esperado:**
  * El sistema detecta la existencia de una sesión válida previamente guardada en el navegador.
  * La aplicación restaura de inmediato el panel de trabajo del centro de salud, evitando que el usuario sea expulsado o tenga que volver a escribir sus credenciales.
* **Estado:** OK

---

### CP-05: Validación de selección obligatoria en formulario de Triage
* **Historia de Usuario:** P0-6 (Validación clínica en formulario de Triage).
* **Tipo de Prueba:** Unitaria / Validación de interfaz (Frontend).
* **Precondición:** El usuario se encuentra en la sección de Triage del panel clínico.
* **Datos de Entrada:**
  * Rango Etario: Sin seleccionar
  * Causa Consulta: `Neumonía / Sospecha de Neumonía`
* **Pasos de Ejecución:**
  1. No hacer clic en ningún botón de grupo etario.
  2. Seleccionar una patología en el selector de causas.
  3. Presionar el botón "Registrar Atención".
* **Resultado Esperado:**
  * El sistema bloquea el registro de la atención y despliega una advertencia en pantalla indicando que es obligatorio seleccionar un rango etario antes de continuar.
  * El formulario permanece activo para permitir la corrección sin enviar datos a la base de datos.
* **Estado:** OK

---

### CP-06: Registro exitoso de atención de urgencia en Triage
* **Historia de Usuario:** P0-6 (Registro de ingresos diarios).
* **Tipo de Prueba:** Integración (Frontend / Backend / Base de Datos).
* **Precondición:** Usuario autenticado en el panel clínico con un establecimiento de salud asociado.
* **Datos de Entrada:**
  * Rango Etario seleccionado: `1-4` (botón "1 a 4 años")
  * Causa seleccionada: `Bronquitis / Bronquiolitis aguda`
* **Pasos de Ejecución:**
  1. En la botonera de rangos etarios, seleccionar la opción "1 a 4 años".
  2. Seleccionar la patología en el selector de causas.
  3. Presionar el botón "Registrar Atención".
* **Resultado Esperado:**
  * El botón de acción muestra brevemente un estado de guardado.
  * La atención se almacena exitosamente en la base de datos.
  * La interfaz despliega una notificación de confirmación informando que la atención fue registrada correctamente.
  * El formulario se restablece y el nuevo ingreso aparece reflejado de inmediato en la tabla del turno actual.
* **Estado:** OK

---

### CP-07: Consulta y despliegue del historial de atenciones del turno
* **Historia de Usuario:** P0-6 (Historial de ingresos diarios).
* **Tipo de Prueba:** Integración (Frontend / Backend / Base de Datos).
* **Precondición:** Existen registros guardados previamente para el establecimiento activo.
* **Datos de Entrada:** Carga de la vista de Triage o clic en el botón de refrescar historial.
* **Pasos de Ejecución:**
  1. El sistema realiza la consulta del historial de ingresos del día.
* **Resultado Esperado:**
  * El sistema consulta las atenciones del centro y despliega la tabla actualizada con las atenciones del día, indicando el número correlativo, rango etario, diagnóstico y la hora de registro.
  * En caso de no existir ingresos previos en el día, se muestra un mensaje informativo indicando que no hay atenciones registradas hoy en el centro.
* **Estado:** OK

---

### CP-08: Consulta del pronóstico meteorológico a 96 horas (Open-Meteo)
* **Historia de Usuario:** P0-2 (Integración con API de clima y calidad del aire).
* **Tipo de Prueba:** Integración (Backend / Servicio Meteorológico Externo).
* **Precondición:** Conexión a internet disponible en el servidor.
* **Datos de Entrada:** Coordenadas geográficas válidas correspondientes a la Región Metropolitana.
* **Pasos de Ejecución:**
  1. Enviar la consulta de información ambiental desde el sistema.
* **Resultado Esperado:**
  * El servidor se conecta al servicio meteorológico externo y obtiene un pronóstico completo de 96 horas adaptado a la hora local.
  * La información contiene los valores horarios de temperatura, precipitaciones y concentración de material particulado.
* **Estado:** OK

---

### CP-09: Inferencia predictiva a 96 horas con el modelo RandomForest v6
* **Historia de Usuario:** P0-1 (Endpoint de predicción hospitalaria).
* **Tipo de Prueba:** Integración (Servidor / Modelo Predictivo / Base de Datos).
* **Precondición:** El modelo predictivo oficial y sus metadatos se encuentran cargados en el servidor.
* **Datos de Entrada:** Parámetros de demanda histórica y condiciones climáticas proyectadas para el centro asistencial.
* **Pasos de Ejecución:**
  1. Ejecutar la solicitud de predicción de demanda a 96 horas.
* **Resultado Esperado:**
  * El sistema procesa los datos epidemiológicos y meteorológicos mediante el modelo predictivo, devolviendo la cantidad estimada de pacientes respiratorios a 96 horas y guardando el registro para fines de auditoría.
* **Estado:** No ejecutada (Módulo probado internamente en el backend; integración completa con el Dashboard de usuario pendiente de despliegue).

---

### CP-10: Cifrado irreversible de contraseñas con Bcrypt en base de datos
* **Historia de Usuario:** Seguridad (Protección de credenciales).
* **Tipo de Prueba:** Seguridad / Base de Datos.
* **Precondición:** Conexión disponible a la base de datos del sistema.
* **Datos de Entrada:** Creación de una cuenta de usuario con una contraseña establecida.
* **Pasos de Ejecución:**
  1. Registrar un usuario con contraseña.
  2. Consultar directamente en la base de datos el registro almacenado para la cuenta.
* **Resultado Esperado:**
  * La contraseña se procesa con un algoritmo criptográfico seguro (Bcrypt con sal aleatoria).
  * En la base de datos solo se almacena una cadena hash irreversible de longitud fija; en ningún lugar del sistema ni en los registros queda constancia de la clave en texto plano.
* **Estado:** OK

---

### CP-11: Verificación de no almacenamiento de datos de identificación personal
* **Historia de Usuario:** Cumplimiento de leyes chilenas de salud (Leyes N° 20.584 y 19.628).
* **Tipo de Prueba:** Seguridad / Privacidad de datos.
* **Precondición:** Estructura de tablas del sistema y formulario de Triage disponibles.
* **Datos de Entrada:** Inspección del diseño de la base de datos y de los campos solicitados en pantalla.
* **Pasos de Ejecución:**
  1. Auditar los campos solicitados en la interfaz de atención de Triage.
  2. Auditar las columnas existentes en las tablas de atenciones en la base de datos.
* **Resultado Esperado:**
  * La base de datos y la interfaz solo manejan variables operativas generales (fecha, centro de salud, grupo etario y cantidad de atenciones).
  * No existen campos ni registros de identificación personal (sin RUT, nombres, direcciones ni fichas clínicas), garantizando el cumplimiento del secreto médico y la privacidad del paciente.
* **Estado:** OK

---

### CP-12: Visualización gráfica de la proyección a 96 horas en el Dashboard
* **Historia de Usuario:** P0-4 y P0-5 (Gráficos predictivos y panel de monitoreo en Frontend).
* **Tipo de Prueba:** Integración / Visualización (Frontend).
* **Precondición:** Usuario autenticado visualizando el panel principal.
* **Datos de Entrada:** Carga del espacio superior del Dashboard.
* **Pasos de Ejecución:**
  1. Revisar la integración del componente de gráficos proyectando las próximas 96 horas y las tarjetas resumen superiores.
* **Resultado Esperado:**
  * Despliegue de la serie de tiempo histórica junto a la proyección a 96 horas y las tarjetas resumen de afluencia esperada y condiciones ambientales.
* **Estado:** No ejecutada (El espacio superior se encuentra actualmente reservado como contenedor de desarrollo, correspondiente a las tareas del backlog en curso).

---

## 4. Resumen y Conclusiones del Ciclo de Pruebas

* **Total de casos de prueba definidos:** 12
* **Casos con estado OK:** 10 (83.3%)
* **Casos con estado Error:** 0 (0.0%)
* **Casos con estado No ejecutada:** 2 (16.7% — correspondientes a la integración gráfica del modelo y el dashboard superior en el frontend).
