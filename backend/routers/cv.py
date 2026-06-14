"""
CV Router - Endpoints for uploading and parsing CV
"""
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from services.cv_parser import parse_cv_with_llm
from services.pdf_parser import extract_text_from_pdf
from services.session_store import (
    create_session,
    get_profile,
    save_cv_text,
    save_profile,
)

router = APIRouter()

MAX_FILE_SIZE_MB = 10


class ParseRequest(BaseModel):
    session_id: str


class ProfileResponse(BaseModel):
    session_id: str
    profile: dict


@router.post("/upload")
async def upload_cv(file: UploadFile = File(...)):
    """
    Upload a CV PDF file.
    
    - Accepts PDF files only
    - Returns a session_id to use in subsequent calls
    - Also extracts and parses the CV automatically
    """
    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF.")

    # Read file
    file_bytes = await file.read()

    # Validate file size
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File quá lớn. Tối đa {MAX_FILE_SIZE_MB}MB."
        )

    # Create session
    session_id = create_session()

    # Extract text from PDF
    try:
        cv_text = extract_text_from_pdf(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc PDF: {str(e)}")

    # Save raw text
    save_cv_text(session_id, cv_text)

    # Auto-parse the CV with LLM
    try:
        profile = parse_cv_with_llm(cv_text)
        save_profile(session_id, profile)
        parse_status = "success"
        parse_error = None
    except Exception as e:
        profile = None
        parse_status = "failed"
        parse_error = str(e)

    return {
        "session_id": session_id,
        "filename": file.filename,
        "file_size_kb": round(len(file_bytes) / 1024, 1),
        "pages_extracted": cv_text.count("--- Page "),
        "parse_status": parse_status,
        "parse_error": parse_error,
        "profile": profile,
    }


@router.get("/profile/{session_id}")
async def get_cv_profile(session_id: str):
    """
    Get the parsed CV profile for a session.
    """
    profile = get_profile(session_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy session '{session_id}'. Hãy upload CV trước."
        )
    return {
        "session_id": session_id,
        "profile": profile
    }


@router.post("/parse/{session_id}")
async def reparse_cv(session_id: str):
    """
    Re-parse CV for an existing session (useful if auto-parse failed).
    """
    from services.session_store import get_cv_text
    
    cv_text = get_cv_text(session_id)
    if cv_text is None:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy CV text cho session '{session_id}'."
        )

    try:
        profile = parse_cv_with_llm(cv_text)
        save_profile(session_id, profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi parse CV: {str(e)}")

    return {
        "session_id": session_id,
        "profile": profile
    }
