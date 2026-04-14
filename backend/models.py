from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime
import uuid

class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    prompt = Column(Text, nullable=True)   # Original user prompt for memory/similarity search
    dag_json = Column(JSON) # Store parsed DAG
    explanation = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    executions = relationship("Execution", back_populates="workflow")
    triggers = relationship("Trigger", back_populates="workflow")

class Execution(Base):
    __tablename__ = "executions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    workflow_id = Column(String, ForeignKey("workflows.id"))
    status = Column(String, default="PENDING") # PENDING, RUNNING, COMPLETED, FAILED
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    workflow = relationship("Workflow", back_populates="executions")
    logs = relationship("Log", back_populates="execution")

class Log(Base):
    __tablename__ = "logs"
    
    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(String, ForeignKey("executions.id"))
    level = Column(String, default="INFO")
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    execution = relationship("Execution", back_populates="logs")


# ── Event-Driven Trigger Models ─────────────────────────────────────────────

class Trigger(Base):
    """Persists a trigger configuration that links an event source to a workflow."""
    __tablename__ = "triggers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    trigger_type = Column(String, nullable=False)   # "webhook" | "filesystem" | "email"
    config = Column(JSON, default=dict)              # type-specific settings
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="triggers")
    events = relationship("TriggerEvent", back_populates="trigger", order_by="TriggerEvent.timestamp.desc()")


class TriggerEvent(Base):
    """Audit log entry for every trigger firing."""
    __tablename__ = "trigger_events"

    id = Column(Integer, primary_key=True, index=True)
    trigger_id = Column(String, ForeignKey("triggers.id"), nullable=False)
    payload = Column(JSON, nullable=True)            # snapshot of the event payload
    execution_id = Column(String, nullable=True)      # resulting execution ID (if created)
    status = Column(String, default="FIRED")          # FIRED | SUCCESS | ERROR
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    trigger = relationship("Trigger", back_populates="events")
