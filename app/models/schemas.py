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

class TranslateRequest(BaseModel):
    file_ids: list[str]
    glossary_id: str

class JobResponse(BaseModel):
    job_id: str
    status: str

class RevisionRequest(BaseModel):
    job_id: str
    feedback: str
