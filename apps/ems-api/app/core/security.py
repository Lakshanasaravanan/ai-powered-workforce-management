from datetime import datetime,timedelta,timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from app.core.config import Settings
pwd=PasswordHasher()
def hash_password(value:str)->str:return pwd.hash(value)
def verify_password(value:str,hashed:str)->bool:
 try:return pwd.verify(hashed,value)
 except (VerifyMismatchError,InvalidHashError):return False
verify=verify_password
def token(employee_id:str)->str:
 s=Settings();return jwt.encode({'sub':employee_id,'exp':datetime.now(timezone.utc)+timedelta(minutes=s.access_token_expire_minutes)},s.jwt_secret,algorithm=s.jwt_algorithm)
