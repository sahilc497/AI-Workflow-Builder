import os
from backend.database import SessionLocal
from backend.models import Log, Execution

def dump_logs():
    db = SessionLocal()
    try:
        # Get the latest execution
        latest_exec = db.query(Execution).order_by(Execution.created_at.desc()).first()
        if not latest_exec:
            print("No executions found.")
            return
            
        print(f"Dumping logs for Execution ID: {latest_exec.id}")
        logs = db.query(Log).filter(Log.execution_id == latest_exec.id).order_by(Log.timestamp).all()
        
        print(f"Execution ID: {latest_exec.id}")
        print(f"Status: {latest_exec.status}")
        print("-" * 50)
        for log in logs:
            print(f"[{log.timestamp}] {log.level}: {log.message}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    dump_logs()
