"""Administración de usuarios: solo un administrador puede crear y listar cuentas."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.establishment import Establishment
from app.models.user import User
from app.schemas.user import UserCreate, UserPatch, UserResponse, UserRole


router = APIRouter(
    prefix="/usuarios",
    tags=["Administración de usuarios"],
    dependencies=[Depends(require_admin)],
)


def hospital_for_email(db: Session, email: str) -> Establishment:
    """Hospital activo asociado al dominio del correo; 422 si no hay ninguno."""
    dominio = email.split("@", 1)[1]
    hospital = (
        db.query(Establishment)
        .filter(Establishment.dominio_correo == dominio, Establishment.activo.is_(True))
        .first()
    )
    if hospital is None:
        raise HTTPException(
            422,
            f"El dominio @{dominio} no está asociado a ningún hospital activo. "
            "Asigne el dominio al hospital o indique establecimiento_id.",
        )
    return hospital


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def crear_usuario(user_in: UserCreate, db: Session = Depends(get_db)):
    """Crea un usuario. El hospital de un médico se deduce del @ de su correo."""
    email = str(user_in.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo electrónico ya se encuentra registrado")

    establecimiento_id = None
    if user_in.role == UserRole.ADMIN:
        if user_in.establecimiento_id is not None:
            raise HTTPException(422, "Un administrador no pertenece a un hospital")
    elif user_in.establecimiento_id is not None:
        # Asignación explícita: manda sobre el dominio del correo.
        hospital = db.get(Establishment, user_in.establecimiento_id)
        if hospital is None or not hospital.activo:
            raise HTTPException(422, "El hospital indicado no existe o está desactivado")
        establecimiento_id = hospital.id
    else:
        establecimiento_id = hospital_for_email(db, email).id

    nuevo = User(
        email=email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role.value,
        establecimiento_id=establecimiento_id,
    )
    try:
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo electrónico ya se encuentra registrado") from exc
    return nuevo


@router.get("", response_model=list[UserResponse])
def listar_usuarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return (
        db.query(User)
        .options(joinedload(User.establecimiento))
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.patch("/{user_id}", response_model=UserResponse)
def actualizar_usuario(
    user_id: int,
    data: UserPatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Desactiva o reactiva una cuenta, cambia su hospital o su contraseña (solo admin).

    Desactivar es mejor que borrar: la base no deja borrar a quien registró ingresos.
    """
    usuario = db.get(User, user_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El usuario indicado no existe")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("is_active") is False and usuario.id == admin.id:
        raise HTTPException(422, "No puede desactivar su propia cuenta")
    if "establecimiento_id" in changes:
        if usuario.role == UserRole.ADMIN.value:
            raise HTTPException(422, "Un administrador no pertenece a un hospital")
        hospital = db.get(Establishment, changes["establecimiento_id"])
        if hospital is None or not hospital.activo:
            raise HTTPException(422, "El hospital indicado no existe o está desactivado")
        usuario.establecimiento_id = hospital.id
    if "is_active" in changes:
        usuario.is_active = changes["is_active"]
    if "password" in changes:
        usuario.hashed_password = get_password_hash(changes["password"])
    db.commit()
    db.refresh(usuario)
    return usuario
