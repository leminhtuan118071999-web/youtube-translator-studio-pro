from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
Kind = Literal['full', 'translation', 'seo', 'characters', 'forms', 'images']

class SessionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='Phiên mới', min_length=1, max_length=200)
    source: str = Field(default='', max_length=350000)
    url: str = Field(default='', max_length=2048)
    title: str = Field(default='', max_length=2000)
    description: str = Field(default='', max_length=20000)
    language: str = Field(default='Tiếng Việt', min_length=1, max_length=80)
    style: str = Field(default='Hoạt hình 2D', min_length=1, max_length=500)
    duration_seconds: float | None = Field(default=None, gt=0, le=1920)

class SessionEdit(SessionInput):
    revision: int = Field(ge=0)
    translated: str = Field(default='', max_length=350000)

class JobInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Kind
    revision: int = Field(ge=0)
    request_id: UUID

class SettingsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    values: dict[str, str]
    version: int = Field(ge=0)

class ArtifactEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    field: Literal['new_title','new_description','seo_tags','character_bible','scene']
    value: str = Field(default='', max_length=100000)
    scene_number: int | None = Field(default=None, ge=1, le=240)
    prompt_field: Literal['image_prompt','visual_prompt','transition_to_next'] | None = None
