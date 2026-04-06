from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

class AlertPayload(BaseModel):
    time: str
    level: str
    type: str
    ip: str
    analysis: str
    # ---> BỔ SUNG CÁC TRƯỜNG CHO SERVER NẠN NHÂN TẠI ĐÂY <---
    target_ip: Optional[str] = "Unknown"
    target_server: Optional[str] = "Unknown"
    server: Optional[str] = "Unknown"

@app.post("/api/alerts")
async def receive_alert(alert: AlertPayload):
    print(f"🔔 [WEB BACKEND] Báo động đỏ: {alert.type} từ IP {alert.ip} tấn công {alert.target_server}")
    await manager.broadcast(alert.dict())
    return {"status": "Broadcasted"}

@app.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)