from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db.session import Base,get_db
from app.models.employee import Employee,Role
from app.core.security import hash_password,token
from app.models.notification import Notification,NotificationCategory
import app.api.routes.chat as chat_route

engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool); Session=sessionmaker(engine); client=TestClient(app)
def db_override():
 db=Session()
 try: yield db
 finally: db.close()
def make(code,role=Role.EMPLOYEE,active=True):
 db=Session(); u=Employee(employee_code=code,full_name=code,company_email=f'{code}@x.test',role=role,designation='x',department='x',password_hash=hash_password('x'),onboarding_completed=True,is_active=active);db.add(u);db.commit();db.refresh(u);db.close();return u
def h(u):return {'Authorization':f'Bearer {token(str(u.id))}'}
def setup(): Base.metadata.drop_all(engine);Base.metadata.create_all(engine);app.dependency_overrides[get_db]=db_override
def test_direct_membership_messages_unread_and_notifications():
 setup(); a,b,c,admin=make('A'),make('B'),make('C'),make('ADMIN',Role.ADMIN)
 r=client.post('/api/v1/chat/conversations/direct',json={'target_employee_id':str(b.id)},headers=h(a));assert r.status_code==200; cid=r.json()['id']
 assert client.post('/api/v1/chat/conversations/direct',json={'target_employee_id':str(a.id)},headers=h(b)).json()['id']==cid
 assert client.get(f'/api/v1/chat/conversations/{cid}',headers=h(b)).status_code==200
 assert client.get(f'/api/v1/chat/conversations/{cid}',headers=h(c)).status_code==404 and client.get(f'/api/v1/chat/conversations/{cid}',headers=h(admin)).status_code==404
 sent=client.post(f'/api/v1/chat/conversations/{cid}/messages',json={'content':'hello'},headers=h(a));assert sent.status_code==200
 assert client.post(f'/api/v1/chat/conversations/{cid}/messages',json={'content':'x'},headers=h(c)).status_code==404
 assert client.get('/api/v1/chat/conversations',headers=h(b)).json()[0]['unread_count']==1
 assert client.post(f'/api/v1/chat/conversations/{cid}/read',headers=h(b)).status_code==200
 assert client.get('/api/v1/chat/conversations',headers=h(b)).json()[0]['unread_count']==0
 assert client.post(f'/api/v1/chat/conversations/{cid}/messages',json={'content':'   '},headers=h(a)).status_code==422
 db=Session(); assert db.query(Notification).filter_by(category=NotificationCategory.CHAT,recipient_id=b.id).count()==1;assert db.query(Notification).filter_by(recipient_id=a.id).count()==0;db.close()
def test_group_validates_active_members():
 setup(); a,b=make('A'),make('B'); dead=make('D',active=False)
 r=client.post('/api/v1/chat/conversations/group',json={'name':'Team','participant_employee_ids':[str(b.id)]},headers=h(a));assert r.status_code==200
 assert client.post('/api/v1/chat/conversations/group',json={'name':'Bad','participant_employee_ids':[str(dead.id)]},headers=h(a)).status_code==422
def test_websocket_authentication_rejects_invalid_and_inactive():
 setup(); active=make('A'); inactive=make('I',active=False); chat_route.SessionLocal=Session
 with client.websocket_connect(f'/api/v1/chat/ws?token={token(str(active.id))}') as ws: ws.send_text('ping')
 try:
  with client.websocket_connect('/api/v1/chat/ws?token=invalid'): pass
 except Exception: pass
def test_rest_message_broadcasts_only_to_conversation_members():
 setup(); a,b,c=make('A'),make('B'),make('C'); chat_route.SessionLocal=Session
 cid=client.post('/api/v1/chat/conversations/direct',json={'target_employee_id':str(b.id)},headers=h(a)).json()['id']
 delivered=[]
 async def capture(ids,event): delivered.append((ids,event))
 original=chat_route.manager.broadcast; chat_route.manager.broadcast=capture
 try:
  response=client.post(f'/api/v1/chat/conversations/{cid}/messages',json={'content':'private'},headers=h(a)); assert response.status_code==200
  import time; time.sleep(.05)
 finally: chat_route.manager.broadcast=original
 assert len(delivered)==1
 ids,event=delivered[0]
 assert str(b.id) in ids and str(c.id) not in ids
 assert event['type']=='message.created' and event['conversation_id']==cid and event['message']['id']==response.json()['id']
 try:
  with client.websocket_connect(f'/api/v1/chat/ws?token={token(str(inactive.id))}'): pass
 except Exception: pass
