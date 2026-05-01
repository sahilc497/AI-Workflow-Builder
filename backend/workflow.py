"""
Workflow Execution Engine
Dispatches DAG node execution through the plugin-based NODE_REGISTRY.
Includes LLM-powered self-healing for automatic failure recovery.
"""
import time
import os
import json
from typing import Dict, Any, TypedDict

from .database import SessionLocal
from .models import Execution, Log
from .nodes import get_node, NODE_REGISTRY
from .self_healing import attempt_self_heal, FALLBACK_STRATEGY


# ── State schema for LangGraph compatibility ────────────────────────────────

class WorkflowState(TypedDict):
    workflow_id: str
    execution_id: str
    dag: Dict[str, Any]
    current_node: str
    results: Dict[str, Any]
    errors: list


def _resolve_template_recursive(obj: Any, context: Dict[str, Any]) -> Any:
    """Recursively replace {{node_id}} placeholders in strings, lists, and dicts."""
    if isinstance(obj, str):
        result = obj
        # Double braces {{key}}
        for key, val in context.items():
            val_str = str(val)
            result = result.replace(f"{{{{{key}.output}}}}", val_str)
            result = result.replace(f"{{{{{key}}}}}", val_str)
            
        # Single braces {key} (agent sometimes uses these)
        for key, val in context.items():
            val_str = str(val)
            result = result.replace(f"{{{key}.output}}", val_str)
            result = result.replace(f"{{{key}}}", val_str)
            
        return result
        
    if isinstance(obj, list):
        return [_resolve_template_recursive(item, context) for item in obj]
        
    if isinstance(obj, dict):
        return {k: _resolve_template_recursive(v, context) for k, v in obj.items()}
        
    return obj


# ── Core dispatch function ──────────────────────────────────────────────────

def execute_node_action(action: str, params: dict, context: dict, max_retries: int = 3):
    """
    Dispatch `action` to the registered node plugin via polymorphism.
    """
    node = get_node(action)

    if node is None:
        return f"Executed action {action} with status: SUCCESS"

    # ── Resolve {{placeholders}} in params before execution ──────────
    resolved_params = _resolve_template_recursive(params, context)

    last_error = None
    for attempt in range(max_retries):
        try:
            node.validate(resolved_params)
            return node.execute(resolved_params, context)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(1)

    raise last_error


# ── DAG execution engine ────────────────────────────────────────────────────

def run_workflow_engine(execution_id: str, workflow_id: str, dag_json: dict):
    """
    Executes a workflow DAG in topological (BFS) order.
    Each node is dispatched through the NODE_REGISTRY plugin system.
    On failure, the self-healing engine attempts LLM-driven parameter correction.
    """
    db = SessionLocal()
    exec_record = db.query(Execution).filter(Execution.id == execution_id).first()

    if not exec_record:
        db.close()
        return

    exec_record.status = "RUNNING"
    db.add(Log(execution_id=execution_id, message="Starting DAG execution", level="INFO"))
    
    if exec_record.workflow and exec_record.workflow.explanation:
        expl_text = "Workflow Explanation:\n" + "\n".join(exec_record.workflow.explanation)
        db.add(Log(execution_id=execution_id, message=expl_text, level="INFO"))
        
    db.commit()

    # Helper to write heal logs into the execution log table
    def _heal_log(msg: str, level: str = "INFO"):
        db.add(Log(execution_id=execution_id, message=msg, level=level))
        db.commit()

    try:
        nodes = dag_json.get("nodes", [])
        edges = dag_json.get("edges", [])

        # ── Build adjacency list + in-degree for topological BFS ──────────
        in_degree = {n["id"]: 0 for n in nodes}
        adj = {n["id"]: [] for n in nodes}

        for e in edges:
            adj[e["from"]].append(e["to"])
            in_degree[e["to"]] += 1

        queue = [n for n in in_degree if in_degree[n] == 0]
        results: Dict[str, Any] = {}
        healed_nodes: list = []          # track which nodes were self-healed

        while queue:
            curr = queue.pop(0)
            node_data = next((n for n in nodes if n["id"] == curr), None)

            if not node_data:
                raise RuntimeError(f"Node definition for '{curr}' not found in DAG.")

            action = node_data.get("action", "UNKNOWN")
            params = node_data.get("params", {})

            # Pre-execution log
            db.add(Log(
                execution_id=execution_id,
                message=(f"PRE-EXEC: Node={curr}, Action={action}, "
                         f"Params={params}, ContextKeys={list(results.keys())}"),
                level="INFO"
            ))
            db.commit()

            try:
                res = execute_node_action(action, params, results)
                results[curr] = res
                db.add(Log(execution_id=execution_id,
                           message=f"Executed {curr}: {res}", level="INFO"))
                db.commit()

            except Exception as exc:
                db.add(Log(execution_id=execution_id,
                           message=f"Failed {curr}: {str(exc)} — invoking self-healing…",
                           level="WARNING"))
                db.commit()

                # ── Self-Healing ─────────────────────────────────────────
                healed, heal_result, final_params = attempt_self_heal(
                    action=action,
                    original_params=params,
                    error=exc,
                    context=results,
                    node_id=curr,
                    log_callback=_heal_log,
                )

                if healed:
                    results[curr] = heal_result
                    healed_nodes.append({
                        "node_id": curr,
                        "action": action,
                        "original_params": params,
                        "healed_params": final_params,
                    })
                    db.add(Log(
                        execution_id=execution_id,
                        message=f"✅ Self-healed {curr}: {heal_result}",
                        level="INFO",
                    ))
                    db.commit()

                elif FALLBACK_STRATEGY == "skip":
                    # Skip this node — mark as failed but continue the DAG
                    results[curr] = heal_result
                    db.add(Log(
                        execution_id=execution_id,
                        message=f"⚠️ Skipped {curr} after self-heal exhausted (fallback=skip)",
                        level="WARNING",
                    ))
                    db.commit()

                else:
                    # Abort — rethrow the original error
                    raise RuntimeError(f"Failed at node {curr}: {exc}") from exc

            # Enqueue nodes whose dependencies are now satisfied
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # ── Success path ───────────────────────────────────────────────────
        exec_record.status = "COMPLETED"
        exec_record.result = results

        summary = "Execution Finished"
        if healed_nodes:
            summary += f" (self-healed {len(healed_nodes)} node(s): " + \
                       ", ".join(h["node_id"] for h in healed_nodes) + ")"

        db.add(Log(execution_id=execution_id, message=summary, level="INFO"))

        # Store heal metadata in the result
        if healed_nodes:
            exec_record.result = {**results, "__self_healed__": healed_nodes}

        db.commit()

        _notify_admin(admin_subject="✅ AI Workflow Completed",
                      admin_body=f"Workflow finished.\n\nResults:\n{json.dumps(results, indent=2, default=str)}",
                      execution_id=execution_id, db=db)

    except Exception as exc:
        exec_record.status = "FAILED"
        exec_record.result = {"error": str(exc)}
        db.add(Log(execution_id=execution_id,
                   message=f"Execution Failed: {str(exc)}", level="ERROR"))
        db.commit()

        _notify_admin(admin_subject="❌ AI Workflow Failed",
                      admin_body=f"Workflow encountered an error.\n\nDetails:\n{str(exc)}",
                      execution_id=execution_id, db=db)

    finally:
        db.close()


# ── Helper: admin email notification ────────────────────────────────────────

def _notify_admin(admin_subject: str, admin_body: str, execution_id: str, db):
    admin_email = os.getenv("SMTP_EMAIL")
    if not admin_email:
        return
    try:
        from backend.email_service import send_email
        send_email(admin_email, admin_subject, admin_body)
        db.add(Log(execution_id=execution_id,
                   message="Sent admin notification email", level="INFO"))
        db.commit()
    except Exception as mail_err:
        db.add(Log(execution_id=execution_id,
                   message=f"Admin email failed: {str(mail_err)}", level="ERROR"))
        db.commit()

