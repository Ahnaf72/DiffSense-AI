from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.deps import get_current_user, get_report_service, get_chunk_service
from app.core.exceptions import NotFoundError, require_owner_or_admin
from app.schemas.report import MatchResponse, ReportResponse
from app.schemas.user import TokenData
from app.services.report_service import ReportService
from app.services.chunk_service import ChunkService
from app.db.supabase_client import task_db

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=list[ReportResponse])
async def list_my_reports(
    current_user: TokenData = Depends(get_current_user),
    svc: ReportService = Depends(get_report_service),
):
    return svc.list_user_reports(current_user.user_id)


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: ReportService = Depends(get_report_service),
):
    report = svc.get_report(report_id)
    if not report:
        raise NotFoundError("Report not found")
    require_owner_or_admin(report["user_id"], current_user.user_id, current_user.role)
    return report


@router.get("/{report_id}/detailed")
async def get_report_detailed(
    report_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: ReportService = Depends(get_report_service),
    chunk_svc: ChunkService = Depends(get_chunk_service),
):
    """Get detailed report with color-coded matched segments and sources.

    Returns:
        - overall_score: Final weighted score (0-1)
        - breakdown: Score breakdown by detection method
        - matches: List of color-coded matched segments with sources
        - segments: Grouped segments by severity (high, medium, low)
    """
    report = svc.get_report(report_id)
    if not report:
        raise NotFoundError("Report not found")
    require_owner_or_admin(report["user_id"], current_user.user_id, current_user.role)

    matches = svc.get_matches(report_id)

    # Fetch chunk details for matches
    upload_chunk_ids = [str(m["upload_chunk_id"]) for m in matches]
    ref_chunk_ids = [str(m["reference_chunk_id"]) for m in matches]

    # Get chunk contents using repo layer for consistency
    upload_chunks = {}
    ref_chunks = {}

    for uid in upload_chunk_ids:
        chunk = chunk_svc._repo.get_by_id(UUID(uid))
        if chunk:
            upload_chunks[uid] = chunk
    for rid in ref_chunk_ids:
        chunk = chunk_svc._repo.get_by_id(UUID(rid))
        if chunk:
            ref_chunks[rid] = chunk

    # Build color-coded matches
    color_coded_matches = []
    for m in matches:
        uid = str(m["upload_chunk_id"])
        rid = str(m["reference_chunk_id"])
        score = m["similarity_score"]

        # Color coding based on severity
        if score >= 0.8:
            color = "#ef4444"  # red - high severity (plagiarism)
            severity = "high"
        elif score >= 0.5:
            color = "#f59e0b"  # yellow/amber - medium (paraphrase)
            severity = "medium"
        else:
            color = "#22c55e"  # green - low (semantic)
            severity = "low"

        upload_chunk = upload_chunks.get(uid, {})
        ref_chunk = ref_chunks.get(rid, {})

        color_coded_matches.append({
            "id": str(m["id"]),
            "upload_chunk_id": uid,
            "upload_content": upload_chunk.get("content", ""),
            "upload_chunk_index": upload_chunk.get("chunk_index", 0),
            "reference_chunk_id": rid,
            "reference_content": ref_chunk.get("content", ""),
            "reference_chunk_index": ref_chunk.get("chunk_index", 0),
            "reference_source_id": ref_chunk.get("source_id", ""),
            "reference_source_type": ref_chunk.get("source_type", ""),
            "similarity_score": round(score, 4),
            "color": color,
            "severity": severity,
        })

    # Group by severity
    segments_by_severity = {
        "high": [m for m in color_coded_matches if m["severity"] == "high"],
        "medium": [m for m in color_coded_matches if m["severity"] == "medium"],
        "low": [m for m in color_coded_matches if m["severity"] == "low"],
    }

    # Extract unique sources
    sources = list(set(m["reference_source_id"] for m in color_coded_matches if m["reference_source_id"]))

    return {
        "report_id": str(report_id),
        "document_id": str(report["document_id"]),
        "overall_score": report.get("overall_score", 0.0),
        "total_matches": len(matches),
        "score_breakdown": report.get("score_breakdown", {}),
        "matches": color_coded_matches,
        "segments": segments_by_severity,
        "sources": sources,
        "status": report.get("status"),
        "created_at": report.get("created_at"),
    }


@router.get("/{report_id}/matches", response_model=list[MatchResponse])
async def get_report_matches(
    report_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: ReportService = Depends(get_report_service),
):
    report = svc.get_report(report_id)
    if not report:
        raise NotFoundError("Report not found")
    require_owner_or_admin(report["user_id"], current_user.user_id, current_user.role)
    return svc.get_matches(report_id)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: ReportService = Depends(get_report_service),
):
    report = svc.get_report(report_id)
    if not report:
        raise NotFoundError("Report not found")
    require_owner_or_admin(report["user_id"], current_user.user_id, current_user.role)
    svc.delete_report(report_id)
