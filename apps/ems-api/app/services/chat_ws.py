import asyncio
from collections import defaultdict
from fastapi import WebSocket


class ChatConnectionManager:
    def __init__(self): self._connections: dict[str,set[WebSocket]]=defaultdict(set)
    async def connect(self, employee_id:str, websocket:WebSocket, subprotocol: str | None = None):
        await websocket.accept(subprotocol=subprotocol); self._connections[employee_id].add(websocket)
    def disconnect(self, employee_id:str, websocket:WebSocket):
        self._connections[employee_id].discard(websocket)
        if not self._connections[employee_id]: self._connections.pop(employee_id,None)
    async def broadcast(self, employee_ids:list[str], event:dict):
        stale=[]
        for employee_id in employee_ids:
            for socket in tuple(self._connections.get(employee_id,())):
                try:
                    await socket.send_json(event)
                except Exception:
                    stale.append((employee_id,socket))
        for employee_id,socket in stale: self.disconnect(employee_id,socket)

manager=ChatConnectionManager()
