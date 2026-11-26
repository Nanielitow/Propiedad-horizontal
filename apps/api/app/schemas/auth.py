import uuid

from pydantic import BaseModel, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)


class MembershipOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    role: UserRole
    is_demo: bool = False  # conjunto de ejemplo


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_platform_admin: bool = False


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  (tipo de token OAuth2, no un secreto)
    expires_in: int
    refresh_token: str
    refresh_expires_in: int


class LoginResponse(MeResponse, TokenPair):
    pass


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=2000)
