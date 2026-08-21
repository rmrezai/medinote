from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)


class BootstrapAdminRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    email: str
    password: str = Field(min_length=12, max_length=200)
    display_name: str | None = None


class UserCreateRequest(BaseModel):
    email: str
    password: str = Field(min_length=12, max_length=200)
    display_name: str | None = None
    role: str = 'attending'


class UserRead(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    display_name: str | None
    role: str
    active: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    model_config = {'from_attributes': True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_at: datetime
    user: UserRead
