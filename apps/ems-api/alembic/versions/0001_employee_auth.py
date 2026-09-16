"""employee auth foundation"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0001_employee_auth';down_revision=None;branch_labels=None;depends_on=None
def upgrade():
 role=postgresql.ENUM('ADMIN','MANAGER','EMPLOYEE',name='role',create_type=False);role.create(op.get_bind(),checkfirst=True)
 op.create_table('employees',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('employee_code',sa.String(32),unique=True,nullable=False),sa.Column('full_name',sa.String(120),nullable=False),sa.Column('company_email',sa.String(255),unique=True,nullable=False),sa.Column('password_hash',sa.String(255),nullable=False),sa.Column('temporary_password_hash',sa.String(255)),sa.Column('role',role,nullable=False),sa.Column('designation',sa.String(100),nullable=False),sa.Column('department',sa.String(100),nullable=False),sa.Column('manager_id',sa.Uuid(),sa.ForeignKey('employees.id')),sa.Column('is_active',sa.Boolean(),nullable=False),sa.Column('onboarding_completed',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False))
def downgrade():op.drop_table('employees');op.execute('DROP TYPE IF EXISTS role')
