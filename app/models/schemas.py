from pydantic import BaseModel
from typing import Optional

class GlossaryUploadResponse(BaseModel):
    glossary_id: str
    term_count: int
    filename: str

class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int

class CustomAPIConfig(BaseModel):
    """User-provided API credentials for translation."""
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"

class TranslateRequest(BaseModel):
    file_ids: list[str]
    glossary_id: str
    custom_api: CustomAPIConfig | None = None

class JobResponse(BaseModel):
    job_id: str
    status: str

class RevisionRequest(BaseModel):
    job_id: str
    feedback: str
    custom_api: CustomAPIConfig | None = None
