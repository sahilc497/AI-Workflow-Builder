from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class WorkflowCreateRequest(BaseModel):
    prompt: str

class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    dag_json: Dict[str, Any]
    explanation: Optional[List[str]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class ExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    result: Optional[Dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True

class AddAppRequest(BaseModel):
    app_name: str


# ── Event-Driven Trigger Schemas ────────────────────────────────────────────

class TriggerCreateRequest(BaseModel):
    workflow_id: str
    trigger_type: str                          # "webhook" | "filesystem" | "email"
    config: Dict[str, Any] = {}

class TriggerResponse(BaseModel):
    id: str
    workflow_id: str
    trigger_type: str
    config: Dict[str, Any]
    enabled: bool
    created_at: datetime
    webhook_url: Optional[str] = None          # populated for webhook triggers

    class Config:
        from_attributes = True

class TriggerEventResponse(BaseModel):
    id: int
    trigger_id: str
    payload: Optional[Dict[str, Any]]
    execution_id: Optional[str]
    status: str
    message: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True
