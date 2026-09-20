from fastapi import FastAPI

app = FastAPI(
    title="Sistema Hospitalario de Alerta Temprana",
    description="API REST para el proyecto de título hospitalario",
    version="0.1.0"
)

@app.get("/")
def message():
    return {
        "status": "online",
        "mensaje": "Bienvenido al backend"
    }