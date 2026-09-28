from fastapi import Depends,HTTPException
from app.api.routes.auth import current
from app.models.employee import Employee,Role
def get_current_user(user:Employee=Depends(current)):return user
def require_roles(*roles:Role):
 def check(user:Employee=Depends(current)):
  if user.role not in roles: raise HTTPException(403,'Insufficient permissions')
  return user
 return check
require_admin=require_roles(Role.ADMIN)
require_manager=require_roles(Role.ADMIN,Role.MANAGER)
