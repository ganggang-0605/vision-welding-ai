"""승인된 작업 결과 → 로봇 연계용 JSON (shared/schemas/robot_output.schema.json)"""
from app.schemas import Job, RobotOutput

REQUIRED_FIELDS = ("assembly_path", "marking", "welding_condition", "confidence", "approved_by")


def to_robot_json(job: Job) -> dict:
    """승인된 작업만 변환한다. 승인 전이거나 필수 해석 결과가 비어 있으면 ValueError."""
    if job.status != "approved":
        raise ValueError(f"승인된 작업만 내보낼 수 있습니다 (현재: {job.status})")
    missing = [name for name in REQUIRED_FIELDS if getattr(job, name) is None]
    if missing:
        raise ValueError(f"내보내기에 필요한 항목이 비어 있습니다: {', '.join(missing)}")
    return RobotOutput.model_validate({
        "job_id": job.id,
        "workspace_id": job.workspace_id,
        "project_id": job.project_id,
        "created_at": job.created_at,
        "assembly_path": job.assembly_path,
        "marking": job.marking,
        "welding_condition": job.welding_condition,
        "cell": job.cell,
        "leg_lengths": job.leg_lengths,
        "confidence": job.confidence,
        "evidence": job.evidence,
        "needs_review": job.needs_review,
        "approved": True,
        "approved_by": job.approved_by,
    }).model_dump(mode="json")
