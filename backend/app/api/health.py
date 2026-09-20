from fastapi import ApiRouter

router = ApiRouter()

@router.get("/healthcheck")
def health_check ():
    return {
        "status": "ok",
        "servicio": "Backend Hospitalario",
        "base_de_datos": "pendiente_conexion"
    }