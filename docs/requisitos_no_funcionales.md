# Requisitos No Funcionales (RNF)
## Sistema de Alerta Temprana en Urgencias Respiratorias (96h)

* **Proyecto:** Healthcare Analytics Project — Demanda Respiratoria a 96h
* **Equipo 7:** Antonia Barrera, Ignacio Fernández, Matías Meneses
* **Asignatura:** Capstone — Duoc UC Sede Antonio Varas
* **Docente Guía:** Aldo Martínez
* **Metodología de Trabajo:** Kanban y CRISP-DM

---

Para que esta plataforma sea realmente útil en contextos clínicos, el sistema debe ser confiable, seguro y fácil de usar en momentos de alta exigencia. Los requisitos no funcionales definen estos estándares: aseguran el resguardo legal de los datos, garantizan la continuidad operacional durante los meses más difíciles del invierno y permiten que los funcionarios y jefaturas interpreten la información proyectada en segundos, sin complicaciones técnicas.

### 1. Seguridad y Privacidad
* **RNF-01: Privacidad de datos de salud y protección de accesos**  
  El sistema operará exclusivamente con datos epidemiológicos agregados y consolidados (totales de consultas por rango etario y diagnósticos generales). Queda prohibido capturar, almacenar o procesar datos sensibles o identificadores directos de pacientes (como RUT, nombres o direcciones), asegurando el estricto cumplimiento de la Ley N° 19.628 sobre protección de la vida privada y la Ley N° 20.584 sobre derechos de los pacientes. Adicionalmente, las credenciales de los funcionarios se resguardan mediante cifrado irreversible (Bcrypt) y autenticación basada en tokens (JWT).  
  * **Criterio de aceptación:** El 100% de los datos almacenados en consultas y modelos carece de identificadores personales de pacientes, y ninguna contraseña se guarda en texto plano.

### 2. Confiabilidad y Disponibilidad
* **RNF-02: Alta disponibilidad en temporada crítica**  
  Dado el impacto sanitario de la Campaña de Invierno, la plataforma debe asegurar un funcionamiento continuo y estable durante los meses de mayor circulación viral (mayo a septiembre).  
  * **Criterio de aceptación:** Disponibilidad del servicio de al menos un 99.5% durante el período invernal, programando mantenimientos técnicos únicamente en horarios de madrugada.

### 3. Usabilidad e Interfaz
* **RNF-03: Interpretación rápida del panel predictivo**  
  La interfaz gráfica del Dashboard debe presentar de manera clara y jerarquizada la proyección de demanda a 96 horas, la serie histórica reciente y el contexto ambiental del establecimiento, permitiendo a los directivos y jefaturas evaluar el escenario operativo de forma inmediata según la capacidad propia de su recinto.  
  * **Criterio de aceptación:** El usuario debe poder identificar la tendencia proyectada y los indicadores ambientales del centro asistencial en un tiempo máximo de 20 segundos al ingresar a la pantalla principal.

* **RNF-04: Diseño responsivo y compatibilidad multiplataforma**  
  La aplicación web debe adaptarse visualmente a distintos tamaños de pantalla y funcionar de forma consistente en los navegadores web modernos (Google Chrome, Microsoft Edge, Mozilla Firefox y Safari).  
  * **Criterio de aceptación:** Navegación, formularios y gráficos legibles sin deformaciones ni desbordamientos tanto en computadores de escritorio institucionales como en notebooks y tablets.

### 4. Arquitectura, Escalabilidad y Mantenibilidad
* **RNF-05: Arquitectura modular y desacoplada**  
  La solución debe mantener separados de forma modular la interfaz de usuario (Frontend), la API del sistema (Backend) y el componente de Machine Learning, comunicándose mediante servicios web REST independientes.  
  * **Criterio de aceptación:** La ejecución de procesos analíticos o el reentrenamiento de modelos no debe bloquear la API principal ni congelar la navegación del usuario en el Dashboard.

### 5. Rendimiento
* **RNF-06: Tiempo de respuesta operacional**  
  El registro de atenciones en triage y la consulta de proyecciones deben responder de forma ágil para no entorpecer el flujo de trabajo en urgencias.  
  * **Criterio de aceptación:** Las operaciones de registro y consulta del Backend responden en menos de 2 segundos en condiciones normales de carga.
