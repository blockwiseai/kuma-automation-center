from pydantic import BaseModel
from typing import Optional, Dict, Any

class MonitorNotification(BaseModel):
    url: Dict[str, Any]
    name: Dict[str, Any]
    msg: str

    class Config:
        extra = "allow"  # Allow additional fields that may be sent by Uptime Kuma