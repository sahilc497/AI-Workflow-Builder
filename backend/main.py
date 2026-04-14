from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request, responses
import os
import logging
from dotenv import load_dotenv, set_key
load_dotenv()

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import engine, Base, get_db
from .models import Workflow, Execution, Log, Trigger, TriggerEvent
from .schemas import (WorkflowCreateRequest, WorkflowResponse, ExecutionResponse,
                      AddAppRequest, TriggerCreateRequest, TriggerResponse, TriggerEventResponse)
from .crew_runner import generate_workflow_from_prompt
from .workflow import run_workflow_engine
from .memory import find_similar_workflow
from .trigger_service import trigger_service, _fire_trigger

logger = logging.getLogger("trigger_api")

Base.metadata.create_all(bind=engine)


def _run_migrations():
    """
    Safely add any new columns that don't yet exist in the live database.
    Uses IF NOT EXISTS syntax so it is re-runnable and never destructive.
    """
    migrations = [
        "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS prompt TEXT;",
        "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS explanation JSON;",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__('sqlalchemy').text(sql))
                conn.commit()
            except Exception as e:
                # Column may already exist (non-PostgreSQL DBs raise different errors)
                print(f"[Migration] Skipped (probably already applied): {e}")

try:
    _run_migrations()
except Exception as mig_err:
    print(f"[Migration] Failed: {mig_err}")

app = FastAPI(title="AI Workflow Builder")


# ── Lifespan: start/stop trigger listeners ──────────────────────────────────

@app.on_event("startup")
def _startup_triggers():
    try:
        trigger_service.start_all()
        logger.info("Trigger listener service started")
    except Exception as exc:
        logger.error("Failed to start trigger listeners: %s", exc)


@app.on_event("shutdown")
def _shutdown_triggers():
    trigger_service.stop_all()
    logger.info("Trigger listener service stopped")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/create-workflow", response_model=WorkflowResponse)
def create_workflow(req: WorkflowCreateRequest, db: Session = Depends(get_db)):
    # Pass db so crew_runner can query memory for similar past workflows
    response_json = generate_workflow_from_prompt(req.prompt, db=db)
    if "error" in response_json:
        raise HTTPException(status_code=400, detail="Failed to parse workflow prompt into DAG format.")
        
    dag_json = response_json.get("workflow", response_json)
    explanation = response_json.get("explanation", [])
        
    wf = Workflow(name="Generated Workflow", prompt=req.prompt, dag_json=dag_json, explanation=explanation)
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf

@app.post("/execute/{workflow_id}", response_model=ExecutionResponse)
def execute_workflow(workflow_id: str, background_tasks: BackgroundTasks, approved: bool = False, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    # --- Permission & Safety Check ---
    dag_json = wf.dag_json
    highest_risk = "LOW"
    from .nodes import get_node
    
    for n in dag_json.get("nodes", []):
        action = n.get("action", "")
        actual_action = action.split("/")[-1] if "/" in action else action
        node_instance = get_node(actual_action)
        if node_instance:
            risk = getattr(node_instance, "risk_level", "LOW")
            if risk == "HIGH":
                highest_risk = "HIGH"
            elif risk == "MEDIUM" and highest_risk == "LOW":
                highest_risk = "MEDIUM"
                
    allow_auto_execute = os.getenv("ALLOW_AUTO_EXECUTE", "true").lower() == "true"
    
    if highest_risk == "HIGH" and not approved:
        raise HTTPException(status_code=403, detail="HIGH risk workflow requires explicit approval.")
        
    if not allow_auto_execute and not approved:
        raise HTTPException(status_code=403, detail="Auto-execution is disabled. Explicit approval required.")
    # ---------------------------------
        
    exec_record = Execution(workflow_id=wf.id, status="PENDING")
    db.add(exec_record)
    db.commit()
    db.refresh(exec_record)
    
    background_tasks.add_task(run_workflow_engine, exec_record.id, wf.id, wf.dag_json)
    
    return exec_record

@app.get("/workflow/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf

@app.get("/workflow/{workflow_id}/validate")
def validate_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    dag_json = wf.dag_json
    nodes = dag_json.get("nodes", [])
    
    highest_risk = "LOW"
    risky_nodes = []
    
    from .nodes import get_node
    
    for n in nodes:
        action = n.get("action", "")
        actual_action = action.split("/")[-1] if "/" in action else action
        node_instance = get_node(actual_action)
        
        risk = "LOW"
        if node_instance:
            risk = getattr(node_instance, "risk_level", "LOW")
            
        if risk != "LOW":
            risky_nodes.append({
                "id": n.get("id"),
                "action": action,
                "risk": risk
            })
            if risk == "HIGH":
                highest_risk = "HIGH"
            elif risk == "MEDIUM" and highest_risk == "LOW":
                highest_risk = "MEDIUM"
                
    allow_auto_execute = os.getenv("ALLOW_AUTO_EXECUTE", "true").lower() == "true"
    
    needs_approval = False
    if highest_risk == "HIGH":
        needs_approval = True
    elif not allow_auto_execute:
        needs_approval = True
        
    return {
        "highest_risk": highest_risk,
        "risky_nodes": risky_nodes,
        "needs_approval": needs_approval,
        "allow_auto_execute": allow_auto_execute
    }

@app.get("/workflows", response_model=list[WorkflowResponse])
def get_workflows(db: Session = Depends(get_db)):
    return db.query(Workflow).order_by(Workflow.created_at.desc()).all()

@app.get("/executions/{execution_id}")
def get_execution(execution_id: str, db: Session = Depends(get_db)):
    exec_record = db.query(Execution).filter(Execution.id == execution_id).first()
    if not exec_record:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    logs = db.query(Log).filter(Log.execution_id == execution_id).order_by(Log.timestamp).all()
    
    return {
        "execution": exec_record,
        "logs": logs
    }

@app.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    executions = db.query(Execution).all()
    total = len(executions)
    
    if total == 0:
        return {
            "total": 0, "success_rate": 0, "failure_rate": 0, 
            "avg_time_sec": 0, "success_count": 0, "fail_count": 0, "pending_count": 0
        }
        
    success = sum(1 for e in executions if e.status == "COMPLETED")
    failed = sum(1 for e in executions if e.status == "FAILED")
    pending = total - success - failed
    
    total_time = 0
    calculated_count = 0
    
    for e in executions:
        if e.status in ["COMPLETED", "FAILED"]:
            last_log = db.query(Log).filter(Log.execution_id == e.id).order_by(Log.timestamp.desc()).first()
            if last_log:
                duration = (last_log.timestamp - e.created_at).total_seconds()
                total_time += max(0, duration)
                calculated_count += 1
                
    avg_time = (total_time / calculated_count) if calculated_count > 0 else 0
    
    return {
        "total": total,
        "success_rate": round((success / total) * 100, 1),
        "failure_rate": round((failed / total) * 100, 1),
        "avg_time_sec": round(avg_time, 2),
        "success_count": success,
        "fail_count": failed,
        "pending_count": pending
    }

@app.get("/memory/search")
def memory_search(q: str, db: Session = Depends(get_db)):
    """
    Returns the most similar past workflow for a given query string.
    Useful for the frontend to preview what memory retrieval would return.
    """
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required.")
    
    result = find_similar_workflow(q, db)
    if result is None:
        return {"found": False, "message": "No similar workflow found.", "similarity": 0}
    
    matched_wf, score = result
    return {
        "found": True,
        "similarity": round(score, 3),
        "workflow_id": matched_wf.id,
        "original_prompt": matched_wf.prompt,
        "dag_json": matched_wf.dag_json,
        "created_at": matched_wf.created_at.isoformat()
    }

@app.get("/settings/allowed-apps")
def get_allowed_apps():
    import backend.config as config
    return {"allowed_apps": config.ALLOWED_APPS}

@app.post("/settings/allowed-apps")
def add_allowed_app(req: AddAppRequest):
    import backend.config as config
    app_name = req.app_name.strip().lower()
    if not app_name.endswith(".exe"):
        app_name += ".exe"
        
    if app_name not in config.ALLOWED_APPS:
        config.ALLOWED_APPS.append(app_name)
        
        # Persist to .env
        env_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if not os.path.exists(env_file_path):
            with open(env_file_path, "w") as f:
                pass
        
        current_apps = ",".join(config.ALLOWED_APPS)
        set_key(env_file_path, "ALLOWED_APPS", current_apps)
        
    return {"message": f"Added {app_name}", "allowed_apps": config.ALLOWED_APPS}


# ═══════════════════════════════════════════════════════════════════════════
#  EVENT-DRIVEN TRIGGER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/trigger", response_model=TriggerResponse)
def create_trigger(req: TriggerCreateRequest, db: Session = Depends(get_db)):
    """Create a new event-driven trigger (webhook / filesystem / email)."""
    # Validate trigger type
    if req.trigger_type not in ("webhook", "filesystem", "email"):
        raise HTTPException(status_code=400, detail="trigger_type must be 'webhook', 'filesystem', or 'email'")

    # Validate workflow exists
    wf = db.query(Workflow).filter(Workflow.id == req.workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    trigger = Trigger(
        workflow_id=req.workflow_id,
        trigger_type=req.trigger_type,
        config=req.config,
        enabled=True,
    )
    db.add(trigger)
    db.commit()
    db.refresh(trigger)

    # Start the listener immediately
    trigger_service.start_trigger(
        trigger.id, trigger.trigger_type, trigger.config,
        wf.id, wf.dag_json,
    )

    # Build response with webhook URL if applicable
    resp = TriggerResponse.model_validate(trigger)
    if trigger.trigger_type == "webhook":
        resp.webhook_url = f"/webhook/{trigger.id}"

    logger.info("Created %s trigger %s → workflow %s", trigger.trigger_type, trigger.id, wf.id)
    return resp


@app.get("/triggers", response_model=list[TriggerResponse])
def list_triggers(db: Session = Depends(get_db)):
    """List all triggers."""
    triggers = db.query(Trigger).order_by(Trigger.created_at.desc()).all()
    result = []
    for t in triggers:
        resp = TriggerResponse.model_validate(t)
        if t.trigger_type == "webhook":
            resp.webhook_url = f"/webhook/{t.id}"
        result.append(resp)
    return result


@app.delete("/trigger/{trigger_id}")
def delete_trigger(trigger_id: str, db: Session = Depends(get_db)):
    """Delete a trigger and stop its listener."""
    trigger = db.query(Trigger).filter(Trigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    # Stop listener
    trigger_service.stop_trigger(trigger_id)

    # Delete events first (foreign key), then trigger
    db.query(TriggerEvent).filter(TriggerEvent.trigger_id == trigger_id).delete()
    db.delete(trigger)
    db.commit()

    logger.info("Deleted trigger %s", trigger_id)
    return {"message": f"Trigger {trigger_id} deleted"}


@app.get("/trigger/{trigger_id}/events", response_model=list[TriggerEventResponse])
def get_trigger_events(trigger_id: str, db: Session = Depends(get_db)):
    """View the audit log for a specific trigger."""
    trigger = db.query(Trigger).filter(Trigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    events = (
        db.query(TriggerEvent)
        .filter(TriggerEvent.trigger_id == trigger_id)
        .order_by(TriggerEvent.timestamp.desc())
        .limit(50)
        .all()
    )
    return events


@app.post("/webhook/{trigger_id}")
async def receive_webhook(trigger_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Incoming webhook receiver.
    Any POST to this URL fires the linked workflow with the request body as payload.
    """
    trigger = db.query(Trigger).filter(Trigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    if not trigger.enabled:
        raise HTTPException(status_code=403, detail="Trigger is disabled")
    if trigger.trigger_type != "webhook":
        raise HTTPException(status_code=400, detail="This trigger is not a webhook type")

    # Parse incoming payload
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw_body": (await request.body()).decode("utf-8", errors="replace")}

    wf = db.query(Workflow).filter(Workflow.id == trigger.workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Linked workflow not found")

    exec_id = _fire_trigger(
        trigger_id=trigger.id,
        workflow_id=wf.id,
        dag_json=wf.dag_json,
        payload=payload,
        source_label=f"webhook:{trigger_id[:8]}",
    )

    if exec_id:
        return {"status": "fired", "execution_id": exec_id, "trigger_id": trigger_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to fire trigger")
