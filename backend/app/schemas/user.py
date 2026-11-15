from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.ml_data import EstablishmentSummary


class UserRole(str, Enum):
    ADMIN = "admin"
    MEDICO = "medico"


def _fits_bcrypt(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes")
    return value


class UserCreate(BaseModel):
    """Datos para que un administrador cree un usuario."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: UserRole = UserRole.MEDICO
    # Opcional: fija el hospital a mano (dominios compartidos). Si no viene, se deduce del @.
    establecimiento_id: Optional[int] = Field(default=None, gt=0)

    _password_fits_bcrypt = field_validator("password")(_fits_bcrypt)

class UserRegister(BaseModel):
    """Registro abierto: solo correo, clave y nombre. El rol y el hospital NO se aceptan (extra=forbid)."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid")
    _password_fits_bcrypt = field_validator("password")(_fits_bcrypt)


class UserPatch(BaseModel):
    """Cambios que un administrador puede hacer a una cuenta (todos opcionales)."""

    is_active: Optional[bool] = None
    establecimiento_id: Optional[int] = Field(default=None, gt=0)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

    model_config = ConfigDict(extra="forbid")
    _password_fits_bcrypt = field_validator("password")(lambda value: value if value is None else _fits_bcrypt(value))

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo para actualizar")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("No se admiten valores nulos")
        return self


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    is_active: bool
    # Hospital del usuario (None para los admin). Lo usa el front para mostrar el centro.
    establecimiento: Optional[EstablishmentSummary] = None

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
