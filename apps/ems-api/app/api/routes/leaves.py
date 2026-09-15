from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.employee import Employee, Role
from app.models.leave import DecisionSource, LeaveRequest, LeaveStatus, LeaveType
from app.models.notification import NotificationCategory
from app.schemas.leaves import EmployeeSummary, LeaveCreate, LeaveDecision, LeaveResponse
from app.services.notifications import create_notification


router = APIRouter(prefix="/api/v1/leaves", tags=["leaves"])


def leave_response(
    request: LeaveRequest,
    employee: Employee,
    manager_notification_delivered: bool | None = None,
) -> LeaveResponse:
    return LeaveResponse(
        id=request.id,
        employee=EmployeeSummary(
            id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
        ),
        leave_type=request.leave_type,
        status=request.status,
        start_date=request.start_date,
        end_date=request.end_date,
        duration=request.duration,
        half_day_period=request.half_day_period,
        reason=request.reason,
        approval_required=request.approval_required,
        decided_by_id=request.decided_by_id,
        decided_at=request.decided_at,
        decision_note=request.decision_note,
        decision_source=request.decision_source,
        manager_notification_delivered=manager_notification_delivered,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def get_leave_or_404(db: Session, leave_id: str) -> LeaveRequest:
    try:
        request = db.get(LeaveRequest, UUID(leave_id))
    except ValueError:
        request = None
    if request is None:
        raise HTTPException(404, "Leave request not found")
    return request


def get_employee_or_404(db: Session, employee_id: UUID) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(404, "Leave requester not found")
    return employee


def can_view_leave(user: Employee, requester: Employee) -> bool:
    return (
        user.id == requester.id
        or user.role is Role.ADMIN
        or (user.role is Role.MANAGER and requester.manager_id == user.id)
    )


@router.post("", response_model=LeaveResponse, status_code=201)
def create_leave(
    body: LeaveCreate,
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveResponse:
    automatically_approved = body.leave_type is LeaveType.MEDICAL
    request = LeaveRequest(
        employee_id=user.id,
        leave_type=body.leave_type,
        status=LeaveStatus.APPROVED if automatically_approved else LeaveStatus.PENDING,
        start_date=body.start_date,
        end_date=body.end_date,
        duration=body.duration,
        half_day_period=body.half_day_period,
        reason=body.reason,
        approval_required=not automatically_approved,
        decided_at=datetime.now(timezone.utc).replace(tzinfo=None) if automatically_approved else None,
        decision_source=DecisionSource.AUTOMATIC_POLICY if automatically_approved else None,
    )
    db.add(request)
    db.flush()
    manager = db.get(Employee, user.manager_id) if user.manager_id else None
    manager_notification_delivered = bool(manager and manager.is_active)
    if manager_notification_delivered:
        if automatically_approved:
            title = "Medical leave recorded"
            message = (
                f"{user.full_name} submitted automatically approved MEDICAL leave "
                f"for {body.start_date} to {body.end_date}."
            )
        else:
            title = "Leave approval required"
            message = (
                f"{user.full_name} submitted {body.leave_type.value} leave for "
                f"{body.start_date} to {body.end_date}; approval is required."
            )
        create_notification(
            db,
            recipient_id=manager.id,
            category=NotificationCategory.LEAVE,
            title=title,
            message=message,
            related_entity_type="LEAVE_REQUEST",
            related_entity_id=request.id,
        )
    db.commit()
    db.refresh(request)
    return leave_response(request, user, manager_notification_delivered)


@router.get("/me", response_model=list[LeaveResponse])
def my_leaves(
    user: Employee = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[LeaveResponse]:
    requests = db.query(LeaveRequest).filter_by(employee_id=user.id).all()
    return [leave_response(request, user) for request in requests]


@router.get("/team", response_model=list[LeaveResponse])
def team_leaves(
    user: Employee = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[LeaveResponse]:
    if user.role is not Role.MANAGER:
        raise HTTPException(403, "Manager role required")
    requests = db.query(LeaveRequest).join(
        Employee, LeaveRequest.employee_id == Employee.id
    ).filter(Employee.manager_id == user.id).all()
    return [leave_response(request, get_employee_or_404(db, request.employee_id)) for request in requests]


@router.get("/{leave_id}", response_model=LeaveResponse)
def get_leave(
    leave_id: str,
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveResponse:
    request = get_leave_or_404(db, leave_id)
    requester = get_employee_or_404(db, request.employee_id)
    if not can_view_leave(user, requester):
        raise HTTPException(403, "Not authorized to view this leave request")
    return leave_response(request, requester)


def apply_manager_decision(
    db: Session,
    request: LeaveRequest,
    manager: Employee,
    status: LeaveStatus,
    decision_note: str | None,
) -> bool:
    result = db.execute(
        update(LeaveRequest)
        .where(
            LeaveRequest.id == request.id,
            LeaveRequest.status == LeaveStatus.PENDING,
            LeaveRequest.approval_required.is_(True),
        )
        .values(
            status=status,
            decided_by_id=manager.id,
            decided_at=datetime.now(timezone.utc).replace(tzinfo=None),
            decision_note=decision_note,
            decision_source=DecisionSource.MANAGER,
        )
    )
    return result.rowcount == 1


def decide_leave(
    leave_id: str,
    body: LeaveDecision,
    status: LeaveStatus,
    user: Employee,
    db: Session,
) -> LeaveResponse:
    request = get_leave_or_404(db, leave_id)
    requester = get_employee_or_404(db, request.employee_id)
    if (
        user.role is not Role.MANAGER
        or user.id == requester.id
        or requester.manager_id != user.id
    ):
        raise HTTPException(403, "Only the direct Manager may decide this leave request")
    if request.status is not LeaveStatus.PENDING or not request.approval_required:
        raise HTTPException(409, "Leave request cannot be decided in its current state")
    if not apply_manager_decision(db, request, user, status, body.decision_note):
        db.rollback()
        raise HTTPException(409, "Leave request was already decided")
    db.refresh(request)
    action = "approved" if status is LeaveStatus.APPROVED else "rejected"
    note_suffix = f" Note: {body.decision_note}" if body.decision_note else ""
    create_notification(
        db,
        recipient_id=requester.id,
        category=NotificationCategory.LEAVE,
        title=f"Leave {action}",
        message=(
            f"{user.full_name} {action} your {request.leave_type.value} leave for "
            f"{request.start_date} to {request.end_date}.{note_suffix}"
        ),
        related_entity_type="LEAVE_REQUEST",
        related_entity_id=request.id,
    )
    db.commit()
    db.refresh(request)
    return leave_response(request, requester)


@router.post("/{leave_id}/approve", response_model=LeaveResponse)
def approve_leave(
    leave_id: str,
    body: LeaveDecision,
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveResponse:
    return decide_leave(leave_id, body, LeaveStatus.APPROVED, user, db)


@router.post("/{leave_id}/reject", response_model=LeaveResponse)
def reject_leave(
    leave_id: str,
    body: LeaveDecision,
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveResponse:
    return decide_leave(leave_id, body, LeaveStatus.REJECTED, user, db)
