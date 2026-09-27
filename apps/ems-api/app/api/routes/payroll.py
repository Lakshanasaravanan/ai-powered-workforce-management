from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.employee import Employee
from app.schemas.payroll import PayrollPreview
from app.services.payroll import payroll_preview


router = APIRouter(prefix="/api/v1/payroll", tags=["payroll"])


@router.get("/{employee_id}", response_model=PayrollPreview)
def preview(
    employee_id: str,
    year: int = Query(..., ge=2000, le=9999),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    _: Employee = Depends(require_admin),
):
    from app.api.routes.employees import employee_or_404
    return payroll_preview(db, employee_or_404(db, employee_id), year, month)
