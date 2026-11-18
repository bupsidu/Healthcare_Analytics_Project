# Diagramas UML — Sistema de Alerta Temprana MINSAL

Diagramas basados en el **código real** del repositorio (verificado contra
`backend/app/api/`, `backend/app/models/` y `frontend/src/`).

> **Convención de idioma:** todo el contenido está en español, salvo los
> nombres de tecnologías, que se mantienen en su idioma original (React,
> PostgreSQL, FastAPI, etc.).

Los diagramas están en **Mermaid**, que se renderiza nativamente en GitHub.
Las versiones en PNG están en [`png/`](png/).

---

## 1. Diagrama de casos de uso

```mermaid
graph TB
    subgraph Actores
        MED(["👨‍⚕️ Médico"])
        ADM(["🛡️ Administrador"])
        API(["🌐 Open-Meteo<br/>sistema externo"])
    end

    subgraph Sistema["Sistema de Alerta Temprana MINSAL"]
        CU1["Registrarse en la plataforma"]
        CU2["Iniciar sesión"]
        CU3["Ver panel del hospital"]
        CU4["Consultar pronóstico del clima"]
        CU5["Ver proyección de demanda a 96 h"]
        CU6["Registrar atenciones del día"]
        CU7["Consultar historial de atenciones"]
        CU8["Gestionar usuarios y aprobaciones"]
        CU9["Consultar catálogo de establecimientos"]
        CU10["Editar datos del establecimiento"]
        CU11["Cargar demanda histórica"]
        CU12["Consultar historial de predicciones"]
    end

    MED --> CU1
    MED --> CU2
    MED --> CU3
    MED --> CU4
    MED --> CU5
    MED --> CU6
    MED --> CU7
    MED --> CU9
    MED --> CU12

    ADM --> CU2
    ADM --> CU3
    ADM --> CU4
    ADM --> CU5
    ADM --> CU8
    ADM --> CU9
    ADM --> CU10
    ADM --> CU11
    ADM --> CU12

    CU3 -.->|incluye| CU4
    CU3 -.->|incluye| CU5
    CU4 -.->|consulta| API
    CU5 -.->|depende de| CU4
```

**Notas de implementación:**

- **Médico**: solo accede a su propio hospital (función `hospital_scope`).
- **Administrador**: ve todos los establecimientos y gestiona usuarios.
- El registro (`POST /auth/register`) crea cuentas **inactivas**; un
  administrador debe aprobarlas (`PATCH /usuarios/{id}`) antes del primer inicio
  de sesión.
- El clima y la calidad del aire provienen de **Open-Meteo**, consultado en vivo
  desde el backend, no desde el navegador.

---

## 2. Diagrama de clases

Los nombres de clases y atributos corresponden a los del código Python
(`backend/app/models/`). Las columnas en inglés de la base de datos se indican
en los comentarios cuando difieren.

```mermaid
classDiagram
    class Usuario {
        +int id
        +str correo
        +str clave_hash
        +str nombre_completo
        +str rol
        +bool esta_activo
        +int establecimiento_id
        +autenticar(clave) bool
    }

    class Establecimiento {
        +int id
        +str id_establecimiento
        +str nombre
        +str comuna
        +str region
        +int capacidad_camas
        +str tipo
        +str dominio_correo
        +bool activo
    }

    class IngresoDiario {
        +int id
        +date fecha
        +int establecimiento_id
        +int casos_respiratorios
        +str grupo_etario
        +int creado_por_usuario_id
        +datetime creado_en
    }

    class DemandaDiaria {
        +str id_establecimiento
        +date fecha
        +int total
    }

    class ClimaDiario {
        +str region
        +date fecha
        +decimal temp_min
        +decimal temp_max
        +decimal precipitacion_mm
    }

    class PrediccionGuardada {
        +int id
        +str id_establecimiento
        +date fecha
        +int pacientes_predichos
        +str version_modelo
        +datetime fecha_hora_prediccion
    }

    Usuario "1" --> "0..*" IngresoDiario : registra
    Establecimiento "1" --> "0..*" IngresoDiario : recibe
    Establecimiento "1" --> "0..*" DemandaDiaria : tiene historia
    Establecimiento "1" --> "0..*" PrediccionGuardada : tiene predicciones
    Establecimiento "0..*" ..> "1..*" ClimaDiario : relacion logica por region
```

**Equivalencias con la base de datos:**

| Clase | Tabla | Nota |
|---|---|---|
| `Usuario` | `usuarios` | Columnas: `email`, `hashed_password`, `full_name`, `role`, `is_active` |
| `Establecimiento` | `establecimientos` | Columnas: `name`, `commune`, `bed_capacity` |
| `IngresoDiario` | `ingresos_diarios` | Columnas: `date`, `respiratory_cases`, `age_group` |
| `DemandaDiaria` | `demanda_diaria` | PK compuesta `(id_establecimiento, fecha)` |
| `ClimaDiario` | `clima_diario` | PK compuesta `(region, fecha)` |
| `PrediccionGuardada` | `predicciones` | Única por `(id_establecimiento, fecha, version_modelo)` |

**Relaciones clave para la defensa:**

| Relación | Tipo | Justificación |
|---|---|---|
| `Usuario` → `IngresoDiario` | Clave foránea real | `creado_por_usuario_id → usuarios.id` |
| `Establecimiento` → `IngresoDiario` | Clave foránea real | `establecimiento_id → establecimientos.id` |
| `Establecimiento` → `DemandaDiaria` | Clave foránea real | por `id_establecimiento` (código DEIS) |
| `Establecimiento` → `PrediccionGuardada` | Clave foránea real | por `id_establecimiento` |
| `Establecimiento` ↔ `ClimaDiario` | **Lógica, no clave foránea** | Se unen por el texto `region`. `clima_diario` tiene clave primaria compuesta `(region, fecha)` y `region` no es único, así que no puede ser destino de una clave foránea. La integridad se garantiza en la capa de aplicación. |

---

## 3. Diagrama de secuencia — funcionalidad principal

Caso de uso central: **un médico consulta el panel y ve la proyección de demanda
de su hospital**.

```mermaid
sequenceDiagram
    autonumber
    actor M as Médico
    participant FE as Interfaz web<br/>React
    participant BE as Servidor<br/>FastAPI
    participant BD as Base de datos<br/>PostgreSQL
    participant OM as Open-Meteo<br/>servicio externo
    participant ML as Modelo de ML<br/>v12

    M->>FE: Ingresa correo y contraseña
    FE->>BE: POST /auth/login
    BE->>BD: busca usuario por correo
    BD-->>BE: usuario con clave cifrada
    BE->>BE: verifica contraseña y estado activo
    BE-->>FE: token JWT
    FE->>FE: guarda el token en el navegador

    M->>FE: Abre el panel del hospital
    FE->>BE: GET /auth/me con token
    BE-->>FE: usuario y establecimiento asociado

    par Clima del hospital
        FE->>BE: GET /establecimientos/{id}/clima
        BE->>BD: consulta la región del establecimiento
        BE->>OM: solicita pronóstico por coordenadas
        OM-->>BE: pronóstico horario a 96 horas
        BE->>BD: guarda resumen diario en clima_diario
        BE-->>FE: temperatura, lluvia e índice de calidad del aire
    and Proyección de demanda
        FE->>BE: GET /predict/proyeccion-96h
        BE->>BD: consulta establecimiento
        BE->>BD: consulta demanda de los últimos 28 días
        BE->>BD: consulta predicciones guardadas
        alt Existe predicción guardada
            BD-->>BE: pacientes predichos por el modelo v12
        else No hay predicción guardada
            BE->>ML: calcula predicción con las variables
            ML-->>BE: pacientes estimados
        end
        BE-->>FE: días con clima, pacientes y semáforo
    end

    FE->>FE: calcula ocupación sobre capacidad de camas
    FE-->>M: muestra indicadores, semáforo y gráfico

    opt El médico registra las atenciones del día
        M->>FE: ingresa casos respiratorios
        FE->>BE: POST /ingresos
        BE->>BD: inserta en ingresos_diarios
        BD-->>BE: identificador creado
        BE-->>FE: 201 creado
    end
```

---

## 4. Diagrama de componentes

```mermaid
flowchart TB
    subgraph CLIENTE["Cliente"]
        NAV["Navegador web"]
    end

    subgraph FRONT["Interfaz web — React 18 + Vite"]
        direction TB
        VISTAS["Vistas<br/>InicioSesion · PanelHospital · RegistroAtenciones"]
        COMP["Componentes de interfaz<br/>TarjetasIndicador · Tarjeta · Boton · Selector"]
        GRAF["Gráficos con Recharts"]
        SERV["Capa de servicios<br/>clienteAuth · servicioPanel<br/>servicioEstablecimientos · servicioAtenciones"]
    end

    subgraph BACK["Servidor — FastAPI"]
        direction TB
        RUTAS["Rutas de la API<br/>autenticación · usuarios · atenciones<br/>datosML · predicciones · clima"]
        SEG["Seguridad<br/>JWT · bcrypt · alcance por hospital"]
        SERVML["Servicio de ML<br/>ml_service · entradas provisionales"]
        CLIMA["Cliente Open-Meteo<br/>open_meteo.py"]
        ORM["Capa ORM<br/>SQLAlchemy 2.0"]
    end

    subgraph DATOS["Persistencia"]
        PG[("PostgreSQL<br/>hospital_db")]
        ART[("Artefactos del modelo<br/>model_rf_directo_v12.joblib<br/>model_metadata_v12.json")]
    end

    subgraph EXTERNOS["Servicios externos"]
        OMF["Open-Meteo<br/>Pronóstico"]
        OMA["Open-Meteo<br/>Calidad del aire"]
    end

    subgraph PIPELINE["Procesamiento y entrenamiento (fuera de línea)"]
        direction TB
        DEIS["DEIS / MINSAL<br/>archivos de atenciones"]
        ETL["unificar_datos.py<br/>feature_engineering.py"]
        ENT["reentrenar_modelo_v*.py"]
    end

    NAV --> FRONT
    VISTAS --> COMP
    VISTAS --> GRAF
    VISTAS --> SERV
    SERV -->|"HTTP/JSON + JWT"| RUTAS
    RUTAS --> SEG
    RUTAS --> SERVML
    RUTAS --> CLIMA
    RUTAS --> ORM
    SERVML --> ART
    CLIMA --> OMF
    CLIMA --> OMA
    ORM --> PG

    DEIS --> ETL
    ETL --> ENT
    ENT -->|"joblib.dump"| ART
```

---

## 5. Mapa tecnológico

### 5.1 Mapa tecnológico

![Mapa tecnológico del sistema](png/mapa_tecnologico.png)

El diagrama muestra las **seis capas del sistema y cómo se conectan**, con los
logos oficiales de cada tecnología y el protocolo sobre cada flecha:

| Conexión | Protocolo |
|---|---|
| Navegador → React | HTML, CSS y JavaScript servidos por Vite |
| React → FastAPI | HTTP/JSON con token Bearer JWT (Axios) |
| FastAPI → PostgreSQL | SQLAlchemy 2.0 sobre psycopg2 |
| FastAPI → Open-Meteo | HTTPS |
| FastAPI → artefacto del modelo | `joblib` cargado en memoria al iniciar |
| Procesamiento → artefacto | `joblib.dump` tras el entrenamiento |
| DEIS/MINSAL → Procesamiento | archivos CSV con carga manual |

Las tecnologías sin logo publicado en Simple Icons — Uvicorn, Recharts,
python-jose, bcrypt, pgAdmin y joblib — se representan con su color de marca y
una abreviatura. Los logos de Open-Meteo y DEIS son SVG propios, porque esos
proyectos no publican uno oficial.

### 5.2 Tabla de tecnologías con justificación

| Capa | Tecnología | Versión | Por qué se eligió |
|---|---|---|---|
| **Interfaz web** | React | 18.2 | Componentes reutilizables, ecosistema maduro |
| | Vite | 5.4 | Compilación rápida y recarga instantánea en desarrollo |
| | Tailwind CSS | 3.4 | Estilos utilitarios sin hojas CSS dispersas |
| | Recharts | 3.10 | Gráficos declarativos integrados con React |
| | Axios | 1.20 | Cliente HTTP con interceptores para el token |
| | Lucide React | 1.55 | Iconografía consistente y liviana |
| **Servidor** | FastAPI | 0.141 | Asíncrono, validación automática, documentación OpenAPI |
| | Uvicorn | 0.30+ | Servidor ASGI de alto rendimiento |
| | SQLAlchemy | 2.0 | ORM tipado, control de transacciones |
| | Pydantic | 2.x | Validación de contratos en los bordes |
| | python-jose | 3.3+ | Firma de tokens JWT (HS256) |
| | bcrypt | 5.0+ | Cifrado de contraseñas con sal |
| | psycopg2 | 2.9+ | Controlador de PostgreSQL |
| **Base de datos** | PostgreSQL | — | Integridad referencial y `ON CONFLICT` para cargas idempotentes |
| **Aprendizaje automático** | scikit-learn | 1.7.2 | `RandomForestRegressor`, métricas y validación |
| | pandas | 2.3.3 | Manipulación de series temporales |
| | NumPy | 2.3.5 | Cálculo vectorizado |
| | joblib | 1.5.2 | Serialización eficiente del modelo |
| **Datos externos** | Open-Meteo Pronóstico | API | Clima y pronóstico sin clave de API |
| | Open-Meteo Calidad del aire | API | MP2.5 y MP10 por coordenada |
| | DEIS / MINSAL | Archivos CSV | Atenciones reales de urgencia respiratoria |
| **Herramientas** | Python | 3.13 | Entorno del procesamiento y del servidor |
| | Git / GitHub | — | Control de versiones y publicación de releases |
| | pgAdmin | — | Administración de PostgreSQL |
| | Jupyter | — | Análisis exploratorio y experimentación |

---

## Diagrama de base de datos

El esquema completo, con claves, restricciones y relaciones, está en
[`base_de_datos.md`](base_de_datos.md).

![Diagrama entidad-relación](png/base_de_datos.png)

---

## Imágenes exportadas

Los 6 diagramas están renderizados como PNG de alta resolución en [`png/`](png/):

| Archivo | Diagrama |
|---|---|
| [`png/casos_de_uso.png`](png/casos_de_uso.png) | Casos de uso |
| [`png/diagrama_de_clases.png`](png/diagrama_de_clases.png) | Diagrama de clases |
| [`png/secuencia_dashboard.png`](png/secuencia_dashboard.png) | Secuencia del panel |
| [`png/componentes.png`](png/componentes.png) | Componentes |
| [`png/mapa_tecnologico.png`](png/mapa_tecnologico.png) | Mapa tecnológico |
| [`png/base_de_datos.png`](png/base_de_datos.png) | Base de datos (ER) |
| [`png/base_de_datos_relaciones.png`](png/base_de_datos_relaciones.png) | Relaciones entre tablas |

Los **logos oficiales** en SVG están en [`logos/`](logos/), tomados de
[Simple Icons](https://simpleicons.org) (licencia CC0).

---

## Cómo exportar los diagramas

**GitHub**: los bloques Mermaid se renderizan automáticamente al ver este archivo.

**PNG o SVG**:

```bash
npx @mermaid-js/mermaid-cli -i diagrama.mmd -o diagrama.png -b white -s 2
```

**VS Code**: extensión *Markdown Preview Mermaid Support*.

---

## Nota sobre fidelidad al código

Cada elemento corresponde a código que existe:

- **Rutas de la API**: 20 rutas verificadas en `backend/app/api/*.py`.
- **Entidades**: `backend/app/models/{user,establishment,intake,ml_data}.py`.
- **Roles**: restricción real `CHECK role IN ('admin', 'medico')`.
- **Servicios externos**: URLs reales en `backend/app/services/open_meteo.py`.
- **Versiones**: `backend/requirements.txt` y `frontend/package.json`.

### ⚠️ Estado de las ramas

Este documento se generó sobre la rama `branch-nacho`, que **no incluye el
frontend más reciente** de la compañera de interfaz. Los componentes
`DashboardSection.jsx` y `KpiCards.jsx` existen en `origin/Branch-Anto` y están
reflejados en el diagrama de componentes, pero no están en este checkout local.

La rama `main` sí tiene el backend completo (`ml_service`, `ml_data`,
`predictions`, `open_meteo`). El frontend completo se integra al mergear
`Branch-Anto`.

Si el diagrama se presenta antes de ese merge, conviene aclarar que los
componentes de la interfaz corresponden al diseño ya implementado en la rama de
la compañera.

---

## Regenerar el mapa tecnológico

El mapa con logos está renderizado como PNG en `png/mapa_tecnologico.png`
(2512×1988 px). Para regenerarlo tras cambiar logos o tecnologías:

```bash
python3 docs/uml/generar_mapa_tecnologico.py
```

El script lee los SVG de `logos/` y compone la imagen por capas.

> Los logos se obtuvieron de [Simple Icons](https://simpleicons.org) (licencia
> CC0, uso libre) y se guardaron localmente para que el proyecto no dependa de
> un CDN externo.
