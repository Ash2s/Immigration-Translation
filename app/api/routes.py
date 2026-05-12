"""API routes for immigration document translation service."""

import os
import json
import uuid
import asyncio
import re
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.services.glossary import GlossaryService
from app.services.document_parser import DocumentParser
from app.services.translator import TranslatorService
from app.models.schemas import (
    GlossaryUploadResponse,
    TranslateRequest,
    JobResponse,
    RevisionRequest,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Module-level service singletons
# ---------------------------------------------------------------------------
glossary_service = GlossaryService()
translator_service = TranslatorService()
doc_parser = DocumentParser()

# ---------------------------------------------------------------------------
# Storage directories
# ---------------------------------------------------------------------------
UPLOAD_DIR = settings.UPLOAD_DIR
JOBS_DIR = settings.JOBS_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(JOBS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# File-backed job tracking
# ---------------------------------------------------------------------------
# Every mutation to jobs or original_filenames is written to disk so state
# survives a process restart as long as the filesystem remains intact.
jobs: dict[str, dict] = {}
original_filenames: dict[str, str] = {}


def _load_all_jobs() -> None:
    """Populate *jobs* and *original_filenames* from disk on startup."""
    fnames_path = os.path.join(JOBS_DIR, "_filenames.json")
    if os.path.exists(fnames_path):
        try:
            with open(fnames_path, "r", encoding="utf-8") as f:
                original_filenames.update(json.load(f))
        except Exception:
            pass

    for name in os.listdir(JOBS_DIR):
        if not name.endswith(".json") or name == "_filenames.json":
            continue
        job_id = name[:-5]  # strip ".json"
        try:
            with open(os.path.join(JOBS_DIR, name), "r", encoding="utf-8") as f:
                jobs[job_id] = json.load(f)
        except Exception:
            pass


def _save_job(job_id: str, data: dict) -> None:
    """Write a single job to disk."""
    path = os.path.join(JOBS_DIR, f"{job_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)


def _delete_job(job_id: str) -> None:
    """Remove a job file from disk."""
    path = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(path):
        os.remove(path)


def _save_filenames() -> None:
    """Persist the original_filenames mapping to disk."""
    path = os.path.join(JOBS_DIR, "_filenames.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(original_filenames, f, ensure_ascii=False, default=str)


# Load existing jobs on startup
_load_all_jobs()

# Regex for Chinese punctuation detection (used for term-only heuristic)
_CN_PUNCT_RE = re.compile(
    r"["
    r"　-〿"   # CJK symbols and punctuation
    r"＀-￯"   # Fullwidth forms
    r"‘-‟"   # Curly quotes / general punctuation
    r"　-〿"   # CJK symbols and punctuation (duplicate for clarity)
    r"＀-￯"   # Fullwidth forms (duplicate)
    r"一-鿿"   # Catch CJK Unified ideographs as well (any Chinese char means translate)
    r"]"
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload/glossary", response_model=GlossaryUploadResponse)
async def upload_glossary(file: UploadFile = File(...)):
    """Upload a glossary CSV or XLSX file.

    Returns a ``GlossaryUploadResponse`` with a generated glossary ID,
    term count, and original filename.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in (".csv", ".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Only .csv and .xlsx files are supported",
        )

    # Save the uploaded file to a temporary path
    temp_path = os.path.join(UPLOAD_DIR, f"glossary_{uuid.uuid4()}{ext}")
    content = await file.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    try:
        glossary_id = glossary_service.load_glossary(temp_path, file.filename)
        term_count = glossary_service.get_term_count(glossary_id)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return GlossaryUploadResponse(
        glossary_id=glossary_id,
        term_count=term_count,
        filename=file.filename,
    )


@router.post("/upload/files")
async def upload_files(files: list[UploadFile] = File(...)):
    """Upload one or more .docx files for translation.

    Returns a plain JSON dict with a ``file_ids`` list (UUIDs assigned to
    each uploaded file).  The FileUploadResponse schema is *not* used here
    because the response shape differs (multiple file IDs).
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    file_ids: list[str] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".docx"):
            raise HTTPException(
                status_code=400,
                detail=f"Only .docx files are supported, got: {f.filename}",
            )
        file_id = str(uuid.uuid4())
        dest = os.path.join(UPLOAD_DIR, f"{file_id}.docx")
        content = await f.read()
        with open(dest, "wb") as out:
            out.write(content)
        original_filenames[file_id] = os.path.splitext(f.filename)[0]
        file_ids.append(file_id)

    _save_filenames()
    return {"file_ids": file_ids}


@router.post("/translate", response_model=JobResponse)
async def translate(req: TranslateRequest):
    """Start an async translation job for the given files and glossary.

    Returns immediately with a ``job_id`` and ``status="processing"``.
    The actual translation runs in a background ``asyncio.Task``.
    """
    custom_api = req.custom_api.model_dump() if req.custom_api else None
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "processing",
        "file_ids": req.file_ids,
        "glossary_id": req.glossary_id,
        "custom_api": custom_api,
    }
    _save_job(job_id, jobs[job_id])
    asyncio.create_task(
        run_translation(job_id, req.file_ids, req.glossary_id, custom_api=custom_api)
    )
    return JobResponse(job_id=job_id, status="processing")


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """Poll the status of a translation job."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "results": job.get("results", []),
    }


@router.get("/result/{job_id}")
async def get_result(job_id: str, file_id: str | None = None):
    """Download a translated .docx file for a job.

    If *file_id* is provided, only that file is downloaded.
    Otherwise the first completed result is returned.
    """
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not yet completed")

    results = job.get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="No results found")

    if file_id:
        results = [r for r in results if r["file_id"] == file_id]

    for entry in results:
        if entry.get("status") == "completed":
            file_path = os.path.join(UPLOAD_DIR, f"{entry['file_id']}_EN.docx")
            if os.path.exists(file_path):
                base_name = original_filenames.get(
                    entry["file_id"], entry["file_id"]
                )
                return FileResponse(
                    file_path,
                    media_type=(
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                    filename=f"{base_name}-EN.docx",
                )

    raise HTTPException(status_code=404, detail="No completed result files found")


@router.get("/preview/{job_id}")
async def preview_result(job_id: str, file_id: str | None = None):
    """Return the translated text content for preview."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not yet completed")

    results = job.get("results", [])
    previews = []
    for entry in results:
        if entry.get("status") == "completed":
            file_path = os.path.join(UPLOAD_DIR, f"{entry['file_id']}_EN.docx")
            if os.path.exists(file_path):
                doc = doc_parser.read_document(file_path)
                paragraphs = doc_parser.extract_paragraphs(doc)
                previews.append({
                    "file_id": entry["file_id"],
                    "text": "\n\n".join(p["text"] for p in paragraphs),
                })
            else:
                previews.append({
                    "file_id": entry["file_id"],
                    "text": "[File not found]",
                })

    if file_id:
        previews = [p for p in previews if p["file_id"] == file_id]

    return {"job_id": job_id, "previews": previews}


@router.post("/revise", response_model=JobResponse)
async def revise(req: RevisionRequest):
    """Re-translate an existing job with user feedback.

    Creates a *new* job based on the original job's file list and glossary,
    and launches a background translation that includes the feedback text
    in every DeepSeek API call.
    """
    original = jobs.get(req.job_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Original job not found")

    new_job_id = str(uuid.uuid4())
    file_ids = original.get("file_ids", [])
    glossary_id = original.get("glossary_id", "")
    custom_api = (
        req.custom_api.model_dump()
        if req.custom_api
        else original.get("custom_api")
    )

    jobs[new_job_id] = {
        "status": "processing",
        "file_ids": file_ids,
        "glossary_id": glossary_id,
        "custom_api": custom_api,
    }

    _save_job(new_job_id, jobs[new_job_id])

    asyncio.create_task(
        run_translation_with_feedback(
            new_job_id, file_ids, glossary_id, req.feedback, custom_api=custom_api
        )
    )

    return JobResponse(job_id=new_job_id, status="processing")


@router.get("/glossary/{glossary_id}")
async def get_glossary(glossary_id: str):
    """Return a glossary's metadata and term mapping."""
    try:
        terms = glossary_service.get_glossary(glossary_id)
        metadata = glossary_service.get_metadata(glossary_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"glossary_id": glossary_id, "terms": terms, **metadata}


# ---------------------------------------------------------------------------
# Background translation tasks
# ---------------------------------------------------------------------------

async def _translate_paragraphs(
    paragraphs: list[dict],
    glossary: dict[str, str],
    feedback: str | None = None,
    custom_api: dict | None = None,
) -> list[dict]:
    """Translate extracted paragraphs, return formatted texts with run data.

    Each returned dict mirrors the input paragraph dict but with a
    ``translated_text`` key added.
    """
    api_kw = (
        {
            "api_key": custom_api["api_key"],
            "base_url": custom_api.get("base_url"),
            "model": custom_api.get("model"),
        }
        if custom_api
        else {}
    )
    result = []
    for para_data in paragraphs:
        text = para_data["text"]
        runs_data = para_data["runs"]

        if not text.strip():
            result.append({**para_data, "translated_text": text})
            continue

        # Term-only heuristic: short text without Chinese characters/punctuation
        if len(text) < 100 and not _CN_PUNCT_RE.search(text):
            translated = translator_service.replace_with_glossary(text, glossary)
        else:
            # Build prompt text, optionally including revision feedback
            prompt_text = text
            if feedback:
                prompt_text = (
                    f"{text}\n\n"
                    f"[REVISION_INSTRUCTION]\n"
                    f"{feedback}\n"
                    f"[/REVISION_INSTRUCTION]\n"
                    f"Apply the above revision instruction when translating."
                )
            translated = translator_service.translate_text(prompt_text, glossary, **api_kw)

            # Check for Chinese residue and re-translate with stronger hint
            residue = TranslatorService.detect_chinese_residue(translated)
            if residue:
                retry_prompt = text
                if feedback:
                    retry_prompt = (
                        f"{text}\n\n"
                        f"[REVISION_INSTRUCTION]\n"
                        f"{feedback}\n"
                        f"[/REVISION_INSTRUCTION]"
                    )
                translated = translator_service.translate_text(
                    "Please fully translate the following Chinese to English "
                    "(no Chinese characters should remain):\n"
                    f"{retry_prompt}",
                    glossary,
                    **api_kw,
                )

        # Fix any remaining Chinese formatting labels
        translated = TranslatorService.fix_cn_labels(translated)

        # Strip any revision instruction residue the model preserved
        translated = re.sub(
            r'\s*\[/?REVISION_INSTRUCTION\].*?\[/REVISION_INSTRUCTION\]\s*',
            '',
            translated,
            flags=re.DOTALL,
        ).strip()
        translated = re.sub(
            r'\s*\[/?REVISION_INSTRUCTION\].*',
            '',
            translated,
            flags=re.DOTALL,
        ).strip()

        # Strip markdown bold/italic markers (**text**) that the model
        # sometimes adds — formatting is applied via run-level properties.
        translated = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', translated, flags=re.DOTALL)
        translated = re.sub(r'\*\*(.+?)\*\*', r'\1', translated, flags=re.DOTALL)
        translated = re.sub(r'\*(.+?)\*', r'\1', translated, flags=re.DOTALL)

        result.append({**para_data, "translated_text": translated})

    return result


async def _process_file(
    file_id: str,
    glossary: dict[str, str],
    feedback: str | None = None,
    custom_api: dict | None = None,
) -> dict:
    """Translate a single .docx file and write the output.

    Returns a result dict with status ``"completed"`` or ``"failed"``.
    """
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.docx")
    translated_path = os.path.join(UPLOAD_DIR, f"{file_id}_EN.docx")
    if not os.path.exists(file_path):
        return {"file_id": file_id, "status": "failed", "error": "Source file not found"}

    try:
        # --- Model-based formatting interpretation ---
        fmt_actions: list[dict] = []
        needs_retranslation = True

        if feedback:
            src_doc = doc_parser.read_document(file_path)
            body_paras = doc_parser.extract_paragraphs(src_doc)
            all_texts = [p["text"] for p in body_paras]
            table_cells = doc_parser.extract_table_cells(src_doc)
            all_texts.extend(c["text"] for c in table_cells)

            fmt_result = translator_service.interpret_formatting_feedback(
                feedback,
                all_texts,
                **(custom_api or {}),
            )
            fmt_actions = fmt_result.get("actions", [])
            needs_retranslation = fmt_result.get("needs_retranslation", True)

        # --- Decide source: translate from Chinese or reuse translated doc ---
        if needs_retranslation:
            doc = doc_parser.read_document(file_path)
            paragraphs = doc_parser.extract_paragraphs(doc)
            translated = await _translate_paragraphs(paragraphs, glossary, feedback, custom_api)

            for idx, entry in enumerate(translated):
                if idx < len(doc.paragraphs):
                    doc_parser.apply_formatting(
                        doc.paragraphs[idx],
                        entry["runs"],
                        entry["translated_text"],
                    )
                    doc_parser.set_line_spacing(doc.paragraphs[idx], True)

            # Translate table cells
            table_cells = doc_parser.extract_table_cells(doc)
            if table_cells:
                translated_cells = await _translate_paragraphs(
                    table_cells, glossary, feedback
                )
                for entry in translated_cells:
                    doc_parser.apply_formatting(
                        entry["paragraph"],
                        entry["runs"],
                        entry["translated_text"],
                    )
                    doc_parser.set_line_spacing(entry["paragraph"], False)

            # Translate text boxes
            textbox_paras = doc_parser.extract_textbox_paragraphs(doc)
            if textbox_paras:
                translated_tb = await _translate_paragraphs(
                    textbox_paras, glossary, feedback
                )
                for entry in translated_tb:
                    doc_parser.apply_textbox_formatting(
                        entry["element"],
                        entry["runs"],
                        entry["translated_text"],
                    )
                    doc_parser.set_textbox_line_spacing(entry["element"])

            doc_parser.clear_background_shading(doc)

        elif os.path.exists(translated_path):
            # Formatting-only revision: read already-translated doc
            doc = doc_parser.read_document(translated_path)

        else:
            # First translation: no translated doc yet, translate now
            doc = doc_parser.read_document(file_path)
            paragraphs = doc_parser.extract_paragraphs(doc)
            translated = await _translate_paragraphs(paragraphs, glossary, feedback, custom_api)

            for idx, entry in enumerate(translated):
                if idx < len(doc.paragraphs):
                    doc_parser.apply_formatting(doc.paragraphs[idx], entry["runs"], entry["translated_text"])
                    doc_parser.set_line_spacing(doc.paragraphs[idx], True)

            table_cells = doc_parser.extract_table_cells(doc)
            if table_cells:
                translated_cells = await _translate_paragraphs(table_cells, glossary, feedback, custom_api)
                for entry in translated_cells:
                    doc_parser.apply_formatting(entry["paragraph"], entry["runs"], entry["translated_text"])
                    doc_parser.set_line_spacing(entry["paragraph"], False)

            textbox_paras = doc_parser.extract_textbox_paragraphs(doc)
            if textbox_paras:
                translated_tb = await _translate_paragraphs(textbox_paras, glossary, feedback, custom_api)
                for entry in translated_tb:
                    doc_parser.apply_textbox_formatting(entry["element"], entry["runs"], entry["translated_text"])
                    doc_parser.set_textbox_line_spacing(entry["element"])

            doc_parser.clear_background_shading(doc)

        # --- Apply targeted formatting ---
        applied: list[str] = []
        if fmt_actions:
            applied = doc_parser.apply_targeted_formatting(doc, fmt_actions)
        elif feedback:
            applied = doc_parser.apply_formatting_instructions(doc, feedback)

        output_path = translated_path
        doc_parser.save_document(doc, output_path)

        # Post-translation quality check
        cn_warnings = doc_parser.verify_no_cn(output_path)

        result = {"file_id": file_id, "status": "completed"}
        if cn_warnings:
            result["cn_warnings"] = cn_warnings
        if applied:
            result["formatting_applied"] = applied
        return result
    except Exception as e:
        return {"file_id": file_id, "status": "failed", "error": str(e)}


async def run_translation(
    job_id: str,
    file_ids: list[str],
    glossary_id: str,
    custom_api: dict | None = None,
) -> None:
    """Background task: translate all files in a job."""
    try:
        glossary = glossary_service.get_glossary(glossary_id)
    except ValueError as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        _save_job(job_id, jobs[job_id])
        return

    results = []
    for file_id in file_ids:
        result = await _process_file(file_id, glossary, custom_api=custom_api)
        results.append(result)

    jobs[job_id]["status"] = "completed"
    jobs[job_id]["results"] = results
    _save_job(job_id, jobs[job_id])


async def run_translation_with_feedback(
    job_id: str,
    file_ids: list[str],
    glossary_id: str,
    feedback: str,
    custom_api: dict | None = None,
) -> None:
    """Background task: re-translate all files with user feedback."""
    try:
        glossary = glossary_service.get_glossary(glossary_id)
    except ValueError as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        _save_job(job_id, jobs[job_id])
        return

    results = []
    for file_id in file_ids:
        result = await _process_file(
            file_id, glossary, feedback=feedback, custom_api=custom_api
        )
        results.append(result)

    jobs[job_id]["status"] = "completed"
    jobs[job_id]["results"] = results
    _save_job(job_id, jobs[job_id])
