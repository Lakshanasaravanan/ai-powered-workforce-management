"""add chat persistence

Revision ID: 0005_chat
Revises: 0004_audit_idempotency
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_chat"
down_revision = "0004_audit_idempotency"
branch_labels = None
depends_on = None

def upgrade():
    conversation_type = postgresql.ENUM("DIRECT", "GROUP", name="conversationtype", create_type=False)
    conversation_type.create(op.get_bind(), checkfirst=True)
    op.create_table("chat_conversations", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("type", conversation_type, nullable=False), sa.Column("name", sa.String(120)), sa.Column("created_by", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("direct_key", sa.String(80), unique=True), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("chat_participants", sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), primary_key=True), sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), primary_key=True), sa.Column("joined_at", sa.DateTime(), nullable=False), sa.Column("last_read_at", sa.DateTime()))
    op.create_table("chat_messages", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("sender_employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])

def downgrade():
    op.drop_table("chat_messages"); op.drop_table("chat_participants"); op.drop_table("chat_conversations")
    sa.Enum(name="conversationtype").drop(op.get_bind(), checkfirst=True)
