"""
Question bank CRUD schemas for Ultimate Showdown.
"""
from pydantic import BaseModel, Field


class QuestionBase(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    option_a: str = Field(..., min_length=1, max_length=255)
    option_b: str = Field(..., min_length=1, max_length=255)
    option_c: str = Field(..., min_length=1, max_length=255)
    option_d: str = Field(..., min_length=1, max_length=255)
    correct_option: str = Field(..., pattern="^[a-dA-D]$")  # A/B/C/D (case-insensitive, normalized to uppercase)
    time_limit: int = Field(default=20, ge=1, le=120)  # seconds
    category: str | None = Field(default="general", max_length=64)
    score: int = Field(default=1000, ge=0, le=10000)  # base points for a correct answer


class QuestionCreate(QuestionBase):
    pass


class QuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    option_a: str | None = Field(default=None, min_length=1, max_length=255)
    option_b: str | None = Field(default=None, min_length=1, max_length=255)
    option_c: str | None = Field(default=None, min_length=1, max_length=255)
    option_d: str | None = Field(default=None, min_length=1, max_length=255)
    correct_option: str | None = Field(default=None, pattern="^[a-dA-D]$")
    time_limit: int | None = Field(default=None, ge=1, le=120)
    category: str | None = Field(default=None, max_length=64)
    score: int | None = Field(default=None, ge=0, le=10000)


class QuestionResponse(QuestionBase):
    id: int

    model_config = {"from_attributes": True}
