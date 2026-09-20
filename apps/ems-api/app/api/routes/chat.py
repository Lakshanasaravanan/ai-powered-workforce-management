from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db.session import get_db, SessionLocal
from app.models.audit import AuditEvent, AuditOutcome, AuditSource
from app.models.chat import ChatConversation, ChatMessage, ChatParticipant, ConversationType
from app.models.employee import Employee
from app.models.notification import NotificationCategory
from app.schemas.chat import DirectConversationRequest, GroupConversationRequest, MessageRequest
from app.services.notifications import create_notification
from app.services.chat_ws import manager

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
def participant(db, cid, uid): return db.get(ChatParticipant, {"conversation_id": cid, "employee_id": uid})
def require_member(db, cid, user):
    c=db.get(ChatConversation,cid)
    if not c or not participant(db,cid,user.id): raise HTTPException(404,"Conversation not found")
    return c
def safe_message(m): return {"id":str(m.id),"conversation_id":str(m.conversation_id),"sender_employee_id":str(m.sender_employee_id),"content":m.content,"created_at":m.created_at}
def summary(db,c,user):
    p=participant(db,c.id,user.id); unread=db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id==c.id,ChatMessage.sender_employee_id!=user.id, ChatMessage.created_at>(p.last_read_at or datetime.min)))
    last=db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==c.id).order_by(ChatMessage.created_at.desc()).limit(1))
    return {"id":str(c.id),"type":c.type.value,"name":c.name,"created_by":str(c.created_by),"updated_at":c.updated_at,"unread_count":unread,"last_message":safe_message(last) if last else None}
def audit(db,user,op,c): db.add(AuditEvent(actor_employee_id=user.id,operation=op,target_type="CHAT_CONVERSATION",target_id=c.id,source=AuditSource.UI,outcome=AuditOutcome.SUCCEEDED,after_state={}))
@router.get("/conversations")
def conversations(db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
    cs=db.scalars(select(ChatConversation).join(ChatParticipant).where(ChatParticipant.employee_id==user.id).order_by(ChatConversation.updated_at.desc())).all(); return [summary(db,c,user) for c in cs]
@router.post("/conversations/direct")
def direct(body:DirectConversationRequest,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
    if body.target_employee_id==user.id: raise HTTPException(422,"Direct self-chat is not supported")
    target=db.get(Employee,body.target_employee_id)
    if not target or not target.is_active: raise HTTPException(422,"Invalid active participant")
    key=":".join(sorted((str(user.id),str(target.id)))); c=db.scalar(select(ChatConversation).where(ChatConversation.direct_key==key))
    if not c:
        c=ChatConversation(type=ConversationType.DIRECT,created_by=user.id,direct_key=key); db.add(c); db.flush(); db.add_all([ChatParticipant(conversation_id=c.id,employee_id=user.id),ChatParticipant(conversation_id=c.id,employee_id=target.id)]); audit(db,user,"create_direct_chat",c); db.commit()
    return summary(db,c,user)
@router.post("/conversations/group")
def group(body:GroupConversationRequest,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
    ids=set(body.participant_employee_ids); ids.add(user.id)
    if len(ids)<2: raise HTTPException(422,"A group requires another participant")
    people=db.scalars(select(Employee).where(Employee.id.in_(ids),Employee.is_active==True)).all()
    if len(people)!=len(ids): raise HTTPException(422,"Invalid active participant")
    c=ChatConversation(type=ConversationType.GROUP,name=body.name.strip(),created_by=user.id); db.add(c); db.flush(); db.add_all([ChatParticipant(conversation_id=c.id,employee_id=x) for x in ids]); audit(db,user,"create_group_chat",c); db.commit(); return summary(db,c,user)
@router.get("/conversations/{conversation_id}")
def one(conversation_id:UUID,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)): return summary(db,require_member(db,conversation_id,user),user)
@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id:UUID,limit:int=50,before:datetime|None=None,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
    require_member(db,conversation_id,user); limit=max(1,min(limit,100)); q=select(ChatMessage).where(ChatMessage.conversation_id==conversation_id)
    if before:q=q.where(ChatMessage.created_at<before)
    return [safe_message(x) for x in reversed(db.scalars(q.order_by(ChatMessage.created_at.desc()).limit(limit)).all())]
@router.post("/conversations/{conversation_id}/messages")
async def send(conversation_id:UUID,body:MessageRequest,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
    c=require_member(db,conversation_id,user); content=body.content.strip()
    if not content: raise HTTPException(422,"Message content is required")
    m=ChatMessage(conversation_id=c.id,sender_employee_id=user.id,content=content); db.add(m); c.updated_at=datetime.utcnow(); db.flush()
    recipients=list(db.scalars(select(ChatParticipant).where(ChatParticipant.conversation_id==c.id,ChatParticipant.employee_id!=user.id)))
    for p in recipients:
        create_notification(db,recipient_id=p.employee_id,category=NotificationCategory.CHAT,title="New chat message",message="You have a new chat message.",related_entity_type="CHAT_MESSAGE",related_entity_id=m.id)
    db.commit(); payload=safe_message(m)
    await manager.broadcast([str(p.employee_id) for p in recipients]+[str(user.id)], jsonable_encoder({"type":"message.created","conversation_id":str(c.id),"message":payload}))
    return payload
@router.post("/conversations/{conversation_id}/read")
def read(conversation_id:UUID,db:Session=Depends(get_db),user:Employee=Depends(get_current_user)):
    require_member(db,conversation_id,user); p=participant(db,conversation_id,user.id); p.last_read_at=datetime.utcnow(); db.commit(); return {"ok":True}

@router.websocket("/ws")
async def websocket_chat(websocket:WebSocket):
    token=websocket.query_params.get("token")
    try:
        import jwt
        from app.core.config import Settings
        settings=Settings(); payload=jwt.decode(token or "",settings.jwt_secret,algorithms=[settings.jwt_algorithm]); employee_id=UUID(str(payload.get("sub")))
        db=SessionLocal(); user=db.get(Employee,employee_id)
        if not user or not user.is_active: raise ValueError()
    except Exception:
        await websocket.close(code=1008); return
    await manager.connect(str(employee_id),websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: pass
    finally:
        manager.disconnect(str(employee_id),websocket)
        try: db.close()
        except Exception: pass
