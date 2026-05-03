import os
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

PROVIDER_DEFAULTS = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-6"}


class ChatCreate(BaseModel):
    provider: str = Field(..., pattern="^(openai|anthropic)$")
    model: str | None = None
    title: str | None = None  # None means no explicit title; auto-title will apply


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    web_search_enabled: bool | None = None
    model: str | None = None
    provider: str | None = Field(default=None, pattern="^(openai|anthropic)$")

    @model_validator(mode="after")
    def model_requires_provider(self) -> "ChatUpdate":
        if self.model is not None and self.provider is None:
            raise ValueError("provider is required when changing model")
        return self


class ChatRead(BaseModel):
    id: int
    title: str
    provider: str
    model: str
    web_search_enabled: bool
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
            return {"prompt": data.prompt, "url": f"/generated/{os.path.basename(data.path)}"}
        return data


class MessageRead(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str
    created_at: datetime
    images: list[GeneratedImageEmbed] = Field(default=[], validation_alias="generated_images")

    model_config = {"from_attributes": True, "populate_by_name": True}


class AttachmentRead(BaseModel):
    id: int
    chat_id: int
    message_id: int | None
    filename: str
    mime_type: str
    size: int
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


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)
    avatar: int = Field(default=0, ge=0, le=99)


class ProfileRead(BaseModel):
    id: int
    name: str
    avatar: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    profile: ProfileRead


class ProfileAvatarUpdate(BaseModel):
    avatar: int = Field(..., ge=0, le=99)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=1)
