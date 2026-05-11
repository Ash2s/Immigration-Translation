from fastapi import APIRouter, HTTPException

from app.models.schemas import FileUploadResponse

router = APIRouter()

@router.post("/upload/glossary")
async def upload_glossary():
    return {"glossary_id": "", "term_count": 0, "filename": ""}

@router.post("/upload/files", response_model=FileUploadResponse)
async def upload_files():
    return FileUploadResponse(file_id="", filename="", size=0)

@router.post("/translate")
async def translate():
    return {"job_id": "", "status": ""}

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    return {"job_id": job_id, "status": "pending"}

@router.get("/result/{job_id}")
async def get_result(job_id: str):
    return {"download_url": ""}

@router.post("/revise")
async def revise():
    return {"job_id": "", "status": ""}

@router.get("/glossary/{glossary_id}")
async def get_glossary(glossary_id: str):
    from app.services.glossary import GlossaryService
    service = GlossaryService()
    meta = service.get_metadata(glossary_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Glossary not found")
    return meta
