from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.establishment import Establishment
from app.models.user import User
from app.schemas.user import UserRole


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No fue posible validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not isinstance(email, str):
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Permite el paso solo a administradores (ej. crear usuarios)."""
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede realizar esta acción",
        )
    return user


def hospital_scope(user: Annotated[User, Depends(get_current_user)]) -> Establishment | None:
    """Define qué hospital puede ver el usuario.

    - Admin: devuelve None, es decir, sin restricción (ve todos los hospitales).
    - Médico: devuelve su hospital; las rutas filtran los datos con él.
    - Médico sin hospital asignado, o con su hospital desactivado: se bloquea.
    - Cualquier otro rol: se bloquea.
    """
    if user.role == UserRole.ADMIN.value:
        return None
    # Lista cerrada: un rol desconocido nunca se trata como médico.
    if user.role != UserRole.MEDICO.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol de usuario no reconocido; contacte al administrador",
        )
    if user.establecimiento is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su usuario no tiene un hospital asignado; contacte al administrador",
        )
    if not user.establecimiento.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El hospital de su usuario está desactivado; contacte al administrador",
        )
    return user.establecimiento
