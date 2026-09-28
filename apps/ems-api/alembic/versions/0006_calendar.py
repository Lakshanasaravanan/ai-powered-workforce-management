from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0006_calendar';down_revision='0005_chat';branch_labels=None;depends_on=None
def upgrade():
 e=postgresql.ENUM('MEETING','TRAINING','COMPANY_EVENT','HOLIDAY','GENERAL',name='eventtype',create_type=False);e.create(op.get_bind(),checkfirst=True)
 op.create_table('calendar_events',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('title',sa.String(200),nullable=False),sa.Column('description',sa.Text()),sa.Column('event_type',e,nullable=False),sa.Column('start_at',sa.DateTime(timezone=True),nullable=False),sa.Column('end_at',sa.DateTime(timezone=True),nullable=False),sa.Column('all_day',sa.Boolean(),nullable=False),sa.Column('location',sa.String(200)),sa.Column('created_by',sa.Uuid(),sa.ForeignKey('employees.id'),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
def downgrade(): op.drop_table('calendar_events');postgresql.ENUM(name='eventtype').drop(op.get_bind(),checkfirst=True)
