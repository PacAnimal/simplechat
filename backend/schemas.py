import os
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import settings

PROVIDER_DEFAULTS = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-6", "ollama": ""}


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class DatasetFileMeta(BaseModel):
    id: int
    dataset_id: int
    filename: str
    mime_type: str
    size: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetRead(BaseModel):
    id: int
    name: str
    created_at: datetime
    index_status: str = "ready"
    indexed_chunks: int = 0
    files: list[DatasetFileMeta] = []

    model_config = {"from_attributes": True}


class ChatCreate(BaseModel):
    provider: str = Field(..., pattern="^(openai|anthropic|ollama)$")
    model: str | None = None
    title: str | None = None  # None means no explicit title; auto-title will apply
    dataset_id: int | None = None


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    web_search_enabled: bool | None = None
    model: str | None = None
    provider: str | None = Field(default=None, pattern="^(openai|anthropic|ollama)$")
    dataset_id: int | None = Field(default=None)

    @model_validator(mode="after")
    def model_and_provider_must_change_together(self) -> "ChatUpdate":
        if self.model is not None and self.provider is None:
            raise ValueError("provider is required when changing model")
        if self.provider is not None and self.model is None:
            raise ValueError("model is required when changing provider")
        return self


class ChatRead(BaseModel):
    id: int
    title: str
    provider: str
    model: str
    web_search_enabled: bool
    dataset_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GeneratedImageEmbed(BaseModel):
    prompt: str
    url: str = ""

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def derive_url(cls, data: object) -> object:
        if hasattr(data, "path"):
            return {
                "prompt": data.prompt,
                "url": f"/api/generated/{os.path.basename(data.path)}",
            }
        return data


class AttachmentRead(BaseModel):
    id: int
    chat_id: int
    message_id: int | None
    filename: str
    mime_type: str
    size: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageRead(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str
    thinking: str | None = None
    created_at: datetime
    images: list[GeneratedImageEmbed] = Field(
        default=[], validation_alias="generated_images"
    )
    attachments: list[AttachmentRead] = []

    model_config = {"from_attributes": True, "populate_by_name": True}


class MessageSearchResult(BaseModel):
    message_id: int
    chat_id: int
    chat_title: str
    chat_provider: str
    chat_model: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GeneratedImageRead(BaseModel):
    id: int
    chat_id: int
    message_id: int | None
    prompt: str
    path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str
    attachment_ids: list[int] = []


def _validate_password(v: str) -> str:
    min_len = settings.password_min_length
    if min_len == 0:
        return v
    if len(v) < min_len:
        raise ValueError(f"Password must be at least {min_len} characters")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"[0-9]", v):
        raise ValueError("Password must contain at least one digit")
    return v


def _validate_name(v: str) -> str:
    stripped = v.strip()
    if not stripped:
        raise ValueError("Name cannot be blank")
    return stripped


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str
    avatar: int = Field(default=0, ge=0, le=50)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password(v)


class ProfileRead(BaseModel):
    id: int
    name: str
    avatar: int
    avatar_color: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    profile: ProfileRead


class ProfileAvatarUpdate(BaseModel):
    avatar: int = Field(..., ge=0, le=50)
    avatar_color: str | None = Field(default=None, max_length=20)


class ProfileNameUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        return _validate_name(v)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password(v)
