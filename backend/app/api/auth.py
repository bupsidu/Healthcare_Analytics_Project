from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserRegister, UserResponse, Token
from app.core.security import get_password_hash, verify_password, create_access_token
from app.api.deps import get_current_user
from app.api.usuarios import hospital_for_email

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def registrar_usuario(user_in: UserRegister, db: Session = Depends(get_db)):
    """Registro abierto con aprobación: crea un médico INACTIVO en el hospital del dominio de su correo.

    No puede iniciar sesión hasta que un administrador lo active (PATCH /usuarios/{id}).
    El rol y el hospital no se pueden elegir aquí."""
    email = str(user_in.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo electrónico ya se encuentra registrado")
    hospital = hospital_for_email(db, email)
    nuevo = User(
        email=email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role="medico",
        is_active=False,
        establecimiento_id=hospital.id,
    )
    try:
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo electrónico ya se encuentra registrado") from exc
    return nuevo


@router.post("/login", response_model=Token)
def iniciar_sesion(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = db.query(User).filter(User.email == form_data.username.lower()).first()
    if not usuario or not verify_password(form_data.password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas (email o contraseña inválidos)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Su cuenta está inactiva o pendiente de aprobación por un administrador")

    token_acceso = create_access_token(data={"sub": usuario.email, "role": usuario.role})
    return {"access_token": token_acceso, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def obtener_usuario_actual(usuario: User = Depends(get_current_user)):
    """Devuelve el perfil del usuario con su rol y su hospital."""
    return usuario
