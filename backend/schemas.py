import os
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


PROVIDER_DEFAULTS = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-6"}


class ChatCreate(BaseModel):
    provider: str = Field(..., pattern="^(openai|anthropic)$")
    model: Optional[str] = None
    title: Optional[str] = None  # None means no explicit title; auto-title will apply


class ChatUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    web_search_enabled: Optional[bool] = None
    model: Optional[str] = None
    provider: Optional[str] = Field(default=None, pattern="^(openai|anthropic)$")

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
    message_id: Optional[int]
    filename: str
    mime_type: str
    size: int
    created_at: datetime

    model_config = {"from_attributes": True}


class GeneratedImageRead(BaseModel):
    id: int
    chat_id: int
    message_id: Optional[int]
    prompt: str
    path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str
    attachment_ids: list[int] = []
