from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


class RemainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: str
    image_url: str
    video_url: str
    analysis_time_days: int | None
    carbon_14_pmc: Decimal | None
    created_at: datetime
    published_at: datetime | None
    likes_count: int = 0
    is_liked: int = 0
    is_mine: int = 0


class RemainFeedResponse(BaseModel):
    id: int
    title: str
    video_url: str
    is_liked: int
    likes_count: int


class PublishRemainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=2000)]
    analysis_time_days: int = Field(gt=0, le=36500)
    carbon_14_pmc: Decimal = Field(ge=0, le=200, max_digits=7, decimal_places=3)


class LikeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liked: int = Field(ge=0, le=1)


class ResearcherCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=80)]
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    password: SecretStr = Field(min_length=8, max_length=128)


class ResearcherAuthRequest(BaseModel):
    username: str
    password: SecretStr


class ResearcherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str


class MessageResponse(BaseModel):
    message: str
    implemented: bool = True
