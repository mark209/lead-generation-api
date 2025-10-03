import re
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


_PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{7,14}$")
_POSTAL_PATTERN = re.compile(r"^[A-Za-z0-9\-\s]{3,12}$")


class Lead(BaseModel):
    """Validated payload for inbound lead submissions."""

    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True, extra="forbid")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., description="E.164 formatted phone number")
    email: EmailStr
    address: str | None = Field(default=None, max_length=255)
    state: str = Field(..., min_length=2, max_length=50)
    postal: str = Field(..., description="Postal or ZIP code")
    jornaya: str | None = Field(default=None, description="Jornaya or Trusted Form token")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not _PHONE_PATTERN.match(value):
            raise ValueError("phone must be in international format, e.g. +15551234567")
        return value

    @field_validator("postal")
    @classmethod
    def validate_postal(cls, value: str) -> str:
        if not _POSTAL_PATTERN.match(value):
            raise ValueError("postal must be 3-12 characters, alphanumeric, spaces, or dashes")
        return value

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return value.upper()


class LeadResponse(BaseModel):
    """Successful lead response envelope."""

    status: str = Field(default="success")
    message: str
    data: Lead


class ErrorResponse(BaseModel):
    """Error response envelope to keep errors consistent."""

    status: str = Field(default="error")
    message: str
    details: Any | None = None