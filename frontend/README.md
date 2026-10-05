# Guía de ejecución local

Esta guía permite abrir sólo la interfaz React o ejecutar el sistema completo
con FastAPI y PostgreSQL. Abra PowerShell en la carpeta raíz del proyecto.

## Opción A: ver sólo el frontend, sin base de datos

Esta opción sirve para comprobar que React, el diseño y el formulario de login
se ven correctamente. No permite iniciar sesión, porque la API necesita una
base de datos.

```powershell
cd frontend
npm install
npm run dev
```

Vite mostrará una dirección, normalmente `http://localhost:5173`. Ábrala en
el navegador. Si se intenta iniciar sesión sin el backend, aparecerá un mensaje
de error de conexión; es el resultado esperado en esta opción.

## Opción B: ejecutar el sistema completo

### 1. Instalar requisitos

- Node.js 18 o superior.
- Python 3.10 o superior.
- PostgreSQL y pgAdmin.

Compruebe Node.js y Python desde PowerShell:

```powershell
node --version
python --version
```

### 2. Crear la base de datos

Abra pgAdmin, conéctese a su servidor PostgreSQL, haga clic derecho en
`Databases`, seleccione `Create` y luego `Database`. Asigne este nombre:

```text
hospital_db
```

Guarde la base sin cambiar otras opciones. No es necesario crear tablas
manualmente en una base nueva: FastAPI las creará al iniciar.

### 3. Configurar y ejecutar el backend

Abra una primera terminal en la raíz del proyecto y ejecute:

```powershell
cd backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

El primer comando entra a la carpeta del backend. El segundo busca el archivo
`.env`; si no existe, crea una copia de `.env.example`. Si ya existe, no lo
modifica, para no borrar las credenciales locales.

Abra `backend/.env` y ajuste al menos estas líneas según su instalación:

```text
SECRET_KEY=una_clave_larga_local_y_privada
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=SU_CONTRASENA_DE_POSTGRESQL
POSTGRES_DB=hospital_db
```

No suba `.env` a Git: contiene una contraseña y una clave privada.

Desde la misma terminal, instale las dependencias e inicie la API:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

La primera vez que se inicia con una base nueva, el backend crea las tablas
`usuarios`, `establecimientos` e `ingresos_diarios`. La API queda disponible en
`http://127.0.0.1:8000` y Swagger en `http://127.0.0.1:8000/docs`.

### 4. Ejecutar el frontend

Abra una segunda terminal en la raíz del proyecto y ejecute:

```powershell
cd frontend
npm install
npm run dev
```

Abra la dirección indicada por Vite, normalmente `http://localhost:5173`.
El frontend usa por defecto la API local en `http://localhost:8000`.

Si el backend se ejecuta en otra dirección, cree `frontend/.env` y reinicie
Vite:

```text
VITE_API_URL=http://DIRECCION_DEL_BACKEND:PUERTO
```

### 5. Comprobación rápida

1. Abra `http://127.0.0.1:8000/docs`.
2. Use `POST /api/auth/register` para crear un usuario de prueba.
3. Abra el frontend en la dirección indicada por Vite.
4. Inicie sesión con el correo y contraseña creados.
5. Debe mostrarse el mensaje `Sistema hospitalario funcionando`.
