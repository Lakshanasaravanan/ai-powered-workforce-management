from alembic import op
import sqlalchemy as sa

revision = "0012_payroll_snapshots"
down_revision = "0011_overtime_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payroll_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("payroll_year", sa.Integer(), nullable=False), sa.Column("payroll_month", sa.Integer(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finalized_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("working_days", sa.Integer(), nullable=False), sa.Column("present_days", sa.Integer(), nullable=False),
        sa.Column("paid_leave_days", sa.Integer(), nullable=False), sa.Column("explicit_absent_days", sa.Integer(), nullable=False), sa.Column("missing_attendance_days", sa.Integer(), nullable=False),
        sa.Column("total_regular_qualifying_minutes", sa.Integer(), nullable=False), sa.Column("total_regular_deficit_minutes", sa.Integer(), nullable=False),
        sa.Column("total_deficit_recovery_minutes", sa.Integer(), nullable=False), sa.Column("total_unrecovered_deficit_minutes", sa.Integer(), nullable=False),
        sa.Column("total_raw_overtime_minutes", sa.Integer(), nullable=False), sa.Column("total_paid_overtime_minutes", sa.Integer(), nullable=False),
        sa.Column("late_deduction_days", sa.Integer(), nullable=False), sa.Column("absence_deduction_days", sa.Integer(), nullable=False),
        sa.Column("total_late_deduction", sa.Numeric(14, 2), nullable=False), sa.Column("total_absence_deduction", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_overtime_pay", sa.Numeric(14, 2), nullable=False), sa.Column("regular_salary_after_absence", sa.Numeric(14, 2), nullable=False), sa.Column("payable_salary", sa.Numeric(14, 2), nullable=False),
        sa.Column("compensation_breakdown", sa.JSON(), nullable=False), sa.Column("daily_breakdown", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]), sa.ForeignKeyConstraint(["finalized_by_admin_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("employee_id", "payroll_year", "payroll_month", name="uq_payroll_snapshot_employee_month"),
    )
    op.create_index("ix_payroll_snapshots_employee_id", "payroll_snapshots", ["employee_id"])
    op.create_index("ix_payroll_snapshots_finalized_by_admin_id", "payroll_snapshots", ["finalized_by_admin_id"])


def downgrade():
    op.drop_index("ix_payroll_snapshots_finalized_by_admin_id", table_name="payroll_snapshots")
    op.drop_index("ix_payroll_snapshots_employee_id", table_name="payroll_snapshots")
    op.drop_table("payroll_snapshots")
