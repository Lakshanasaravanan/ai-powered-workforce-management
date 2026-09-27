from alembic import op
import sqlalchemy as sa

revision='0011_overtime_sessions'
down_revision='0010_attendance_foundation'
branch_labels=None
depends_on=None

def upgrade():
 op.create_table('overtime_sessions',sa.Column('id',sa.Uuid(),nullable=False),sa.Column('employee_id',sa.Uuid(),nullable=False),sa.Column('attendance_date',sa.Date(),nullable=False),sa.Column('check_in_at',sa.DateTime(timezone=True),nullable=False),sa.Column('check_out_at',sa.DateTime(timezone=True),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.ForeignKeyConstraint(['employee_id'],['employees.id']),sa.PrimaryKeyConstraint('id'))
 op.create_index('ix_overtime_employee_date','overtime_sessions',['employee_id','attendance_date'],unique=False)
 op.create_index('uq_overtime_open_employee','overtime_sessions',['employee_id'],unique=True,postgresql_where=sa.text('check_out_at IS NULL'))
def downgrade():
 op.drop_index('uq_overtime_open_employee',table_name='overtime_sessions');op.drop_index('ix_overtime_employee_date',table_name='overtime_sessions');op.drop_table('overtime_sessions')
