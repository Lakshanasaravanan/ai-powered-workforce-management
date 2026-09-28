from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from app.cleanup_development_data import KNOWN_PHASE6_CHAT_MESSAGES, cleanup_known_development_data
from app.core.security import hash_password
from app.db.session import Base
from app.models.chat import ChatConversation, ChatMessage, ChatParticipant, ConversationType
from app.models.employee import Employee, Role


def test_development_cleanup_removes_only_allowlisted_messages_and_is_idempotent():
 engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Session=sessionmaker(engine);Base.metadata.create_all(engine);db=Session();a=Employee(employee_code='CLEAN_A',full_name='Cleanup A',company_email='CLEAN_A@infotech.local',role=Role.EMPLOYEE,designation='Engineer',department='Engineering',password_hash=hash_password('test-password'),onboarding_completed=True,is_active=True);b=Employee(employee_code='CLEAN_B',full_name='Cleanup B',company_email='CLEAN_B@infotech.local',role=Role.EMPLOYEE,designation='Engineer',department='Engineering',password_hash=hash_password('test-password'),onboarding_completed=True,is_active=True);db.add_all([a,b]);db.flush();conversation=ChatConversation(type=ConversationType.DIRECT,created_by=a.id,direct_key='cleanup');db.add(conversation);db.flush();db.add_all([ChatParticipant(conversation_id=conversation.id,employee_id=a.id),ChatParticipant(conversation_id=conversation.id,employee_id=b.id),ChatMessage(conversation_id=conversation.id,sender_employee_id=a.id,content=next(iter(KNOWN_PHASE6_CHAT_MESSAGES))),ChatMessage(conversation_id=conversation.id,sender_employee_id=b.id,content='Ordinary retained conversation')]);db.commit();db.close();first=cleanup_known_development_data(Session,environment='development');second=cleanup_known_development_data(Session,environment='development');db=Session();assert first.chat_messages==1 and second.chat_messages==0;assert db.query(ChatMessage).count()==1 and db.query(ChatConversation).count()==1 and db.query(ChatParticipant).count()==2;db.close()


def test_development_cleanup_refuses_non_development_environment():
 with pytest.raises(RuntimeError): cleanup_known_development_data(environment='production')
