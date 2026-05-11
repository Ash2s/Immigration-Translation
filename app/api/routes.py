from fastapi import APIRouter

router = APIRouter()

@router.post("/upload/glossary")
async def upload_glossary():
    return {"glossary_id": "", "term_count": 0, "filename": ""}

@router.post("/upload/files")
async def upload_files():
    return {"file_ids": []}

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
