"""add mutation idempotency and audit events"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_audit_idempotency"
down_revision = "0003_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    source = postgresql.ENUM("UI", "AI_AGENT", name="audit_source", create_type=False)
    outcome = postgresql.ENUM("SUCCEEDED", name="audit_outcome", create_type=False)
    source.create(op.get_bind(), checkfirst=True)
    outcome.create(op.get_bind(), checkfirst=True)
    op.create_table("audit_events", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("actor_employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("operation", sa.String(80), nullable=False), sa.Column("target_type", sa.String(80), nullable=False), sa.Column("target_id", sa.Uuid(), nullable=False), sa.Column("source", source, nullable=False), sa.Column("outcome", outcome, nullable=False), sa.Column("correlation_id", sa.String(128)), sa.Column("idempotency_key_hash", sa.String(64)), sa.Column("before_state", sa.JSON()), sa.Column("after_state", sa.JSON()), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_audit_events_actor_employee_id", "audit_events", ["actor_employee_id"])
    op.create_table("mutation_idempotency", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("actor_employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("operation", sa.String(80), nullable=False), sa.Column("idempotency_key", sa.String(256), nullable=False), sa.Column("request_fingerprint", sa.String(64), nullable=False), sa.Column("target_id", sa.Uuid(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("actor_employee_id", "operation", "idempotency_key", name="uq_mutation_idempotency_actor_operation_key"))


def downgrade() -> None:
    op.drop_table("mutation_idempotency")
    op.drop_index("ix_audit_events_actor_employee_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.execute("DROP TYPE IF EXISTS audit_outcome")
    op.execute("DROP TYPE IF EXISTS audit_source")
