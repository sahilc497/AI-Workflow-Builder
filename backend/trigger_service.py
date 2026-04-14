"""
Event-Driven Trigger Listener Service
======================================
Manages background listeners for three trigger types:
  • Webhook   – handled via dynamic FastAPI route (no background task needed)
  • Filesystem – watchdog Observer watching a directory for file changes
  • Email      – IMAP polling loop checking for new UNSEEN messages

All trigger firings are logged to the TriggerEvent audit table.
"""

import asyncio
import imaplib
import email as email_lib
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from .database import SessionLocal
from .models import Trigger, TriggerEvent, Execution, Workflow, Log
from .workflow import run_workflow_engine

logger = logging.getLogger("trigger_service")
logger.setLevel(logging.INFO)

# Add console handler if none present
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s  %(name)s  %(message)s"))
    logger.addHandler(_ch)


# ── Helper: fire a trigger ──────────────────────────────────────────────────

def _fire_trigger(trigger_id: str, workflow_id: str, dag_json: dict,
                  payload: dict, source_label: str) -> Optional[str]:
    """
    Create an Execution record, log a TriggerEvent, and kick off the
    workflow engine in a new thread.

    Returns the execution_id on success, None on error.
    """
    db = SessionLocal()
    try:
        # Create execution record
        exec_id = str(uuid.uuid4())
        exec_record = Execution(id=exec_id, workflow_id=workflow_id, status="PENDING")
        db.add(exec_record)

        # Log the trigger event
        event = TriggerEvent(
            trigger_id=trigger_id,
            payload=payload,
            execution_id=exec_id,
            status="FIRED",
            message=f"Trigger fired from {source_label}",
        )
        db.add(event)

        # Add a log entry on the execution
        db.add(Log(
            execution_id=exec_id,
            message=f"⚡ Triggered by {source_label} (trigger={trigger_id})",
            level="INFO",
        ))
        db.commit()

        logger.info("Trigger %s fired → execution %s (source: %s)", trigger_id, exec_id, source_label)

        # Run the workflow in a background thread (non-blocking)
        t = threading.Thread(
            target=run_workflow_engine,
            args=(exec_id, workflow_id, dag_json),
            daemon=True,
        )
        t.start()

        # Update event status after successful dispatch
        event.status = "SUCCESS"
        db.commit()
        return exec_id

    except Exception as exc:
        logger.error("Failed to fire trigger %s: %s", trigger_id, exc)
        try:
            err_event = TriggerEvent(
                trigger_id=trigger_id,
                payload=payload,
                status="ERROR",
                message=str(exc),
            )
            db.add(err_event)
            db.commit()
        except Exception:
            pass
        return None
    finally:
        db.close()


# ── Filesystem Watcher ──────────────────────────────────────────────────────

class _TriggerFSHandler(FileSystemEventHandler):
    """Watchdog handler that fires the linked workflow on file creation/modification."""

    def __init__(self, trigger_id: str, workflow_id: str, dag_json: dict, patterns: list[str]):
        super().__init__()
        self.trigger_id = trigger_id
        self.workflow_id = workflow_id
        self.dag_json = dag_json
        self.patterns = [p.lower() for p in patterns] if patterns else []
        self._debounce: Dict[str, float] = {}

    def _matches(self, path: str) -> bool:
        if not self.patterns:
            return True
        import fnmatch
        basename = os.path.basename(path).lower()
        return any(fnmatch.fnmatch(basename, pat) for pat in self.patterns)

    def _handle(self, event):
        if event.is_directory:
            return
        if not self._matches(event.src_path):
            return

        # Debounce: ignore duplicate events within 2 seconds for the same file
        now = time.time()
        last = self._debounce.get(event.src_path, 0)
        if now - last < 2.0:
            return
        self._debounce[event.src_path] = now

        logger.info("FS trigger %s: %s on %s", self.trigger_id, event.event_type, event.src_path)
        _fire_trigger(
            trigger_id=self.trigger_id,
            workflow_id=self.workflow_id,
            dag_json=self.dag_json,
            payload={"event_type": event.event_type, "file_path": event.src_path},
            source_label=f"filesystem:{event.src_path}",
        )

    def on_created(self, event):
        self._handle(event)

    def on_modified(self, event):
        self._handle(event)


# ── Email (IMAP) Poller ─────────────────────────────────────────────────────

class _EmailPoller:
    """Polls an IMAP inbox for new unseen messages and fires the trigger."""

    def __init__(self, trigger_id: str, workflow_id: str, dag_json: dict, config: dict):
        self.trigger_id = trigger_id
        self.workflow_id = workflow_id
        self.dag_json = dag_json
        self.imap_server = config.get("imap_server", "imap.gmail.com")
        self.email_addr = config.get("email", "")
        self.password = config.get("password", "")
        self.folder = config.get("folder", "INBOX")
        self.interval = max(int(config.get("poll_interval_sec", 30)), 10)
        self._stop = threading.Event()

    def run(self):
        logger.info("Email poller started for trigger %s (%s)", self.trigger_id, self.email_addr)
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception as exc:
                logger.error("Email poll error (trigger %s): %s", self.trigger_id, exc)
            self._stop.wait(self.interval)
        logger.info("Email poller stopped for trigger %s", self.trigger_id)

    def stop(self):
        self._stop.set()

    def _poll_once(self):
        if not self.email_addr or not self.password:
            return

        mail = imaplib.IMAP4_SSL(self.imap_server)
        try:
            mail.login(self.email_addr, self.password)
            mail.select(self.folder)

            status, data = mail.search(None, "UNSEEN")
            if status != "OK":
                return

            msg_ids = data[0].split()
            if not msg_ids:
                return

            for msg_id in msg_ids[:5]:  # process at most 5 per cycle
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                subject = msg.get("Subject", "(no subject)")
                sender = msg.get("From", "(unknown)")

                logger.info("Email trigger %s: new mail from %s — %s", self.trigger_id, sender, subject)
                _fire_trigger(
                    trigger_id=self.trigger_id,
                    workflow_id=self.workflow_id,
                    dag_json=self.dag_json,
                    payload={"from": sender, "subject": subject},
                    source_label=f"email:{sender}",
                )

                # Mark as seen so we don't re-process
                mail.store(msg_id, "+FLAGS", "\\Seen")
        finally:
            try:
                mail.logout()
            except Exception:
                pass


# ── Trigger Listener Service (main orchestrator) ────────────────────────────

class TriggerListenerService:
    """
    Central manager for all active trigger listeners.
    Integrates with FastAPI lifespan to start/stop cleanly.
    """

    def __init__(self):
        # trigger_id → (observer_or_thread, optional_stop_callable)
        self._active: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    # ── public API ───────────────────────────────────────────────────────

    def start_all(self):
        """Load and start all enabled triggers from the DB."""
        db = SessionLocal()
        try:
            triggers = db.query(Trigger).filter(Trigger.enabled == True).all()
            for t in triggers:
                wf = db.query(Workflow).filter(Workflow.id == t.workflow_id).first()
                if wf:
                    self.start_trigger(t.id, t.trigger_type, t.config, t.workflow_id, wf.dag_json)
        finally:
            db.close()
        logger.info("TriggerListenerService: started %d listener(s)", len(self._active))

    def stop_all(self):
        """Gracefully stop every active listener."""
        with self._lock:
            for tid, (resource, stop_fn) in list(self._active.items()):
                self._do_stop(tid, resource, stop_fn)
            self._active.clear()
        logger.info("TriggerListenerService: all listeners stopped")

    def start_trigger(self, trigger_id: str, trigger_type: str, config: dict,
                      workflow_id: str, dag_json: dict):
        """Start a single trigger listener."""
        with self._lock:
            if trigger_id in self._active:
                return  # already running

        if trigger_type == "filesystem":
            self._start_fs(trigger_id, workflow_id, dag_json, config)
        elif trigger_type == "email":
            self._start_email(trigger_id, workflow_id, dag_json, config)
        elif trigger_type == "webhook":
            # Webhooks are handled via the FastAPI route — nothing to start here
            logger.info("Webhook trigger %s registered (handled via /webhook/<id> route)", trigger_id)
        else:
            logger.warning("Unknown trigger type '%s' for trigger %s", trigger_type, trigger_id)

    def stop_trigger(self, trigger_id: str):
        """Stop a single trigger listener."""
        with self._lock:
            entry = self._active.pop(trigger_id, None)
        if entry:
            resource, stop_fn = entry
            self._do_stop(trigger_id, resource, stop_fn)

    # ── private helpers ──────────────────────────────────────────────────

    def _start_fs(self, trigger_id, workflow_id, dag_json, config):
        watch_path = config.get("watch_path", ".")
        patterns = config.get("patterns", [])

        if not os.path.isdir(watch_path):
            try:
                os.makedirs(watch_path, exist_ok=True)
            except OSError as e:
                logger.error("Cannot create watch_path %s: %s", watch_path, e)
                return

        handler = _TriggerFSHandler(trigger_id, workflow_id, dag_json, patterns)
        observer = Observer()
        observer.schedule(handler, watch_path, recursive=False)
        observer.daemon = True
        observer.start()

        with self._lock:
            self._active[trigger_id] = (observer, observer.stop)
        logger.info("FS trigger %s watching %s (patterns=%s)", trigger_id, watch_path, patterns)

    def _start_email(self, trigger_id, workflow_id, dag_json, config):
        poller = _EmailPoller(trigger_id, workflow_id, dag_json, config)
        t = threading.Thread(target=poller.run, daemon=True, name=f"email-{trigger_id[:8]}")
        t.start()

        with self._lock:
            self._active[trigger_id] = (t, poller.stop)
        logger.info("Email trigger %s polling %s every %ds",
                     trigger_id, config.get("email", "?"), poller.interval)

    @staticmethod
    def _do_stop(trigger_id, resource, stop_fn):
        try:
            if stop_fn:
                stop_fn()
            if isinstance(resource, Observer):
                resource.join(timeout=3)
        except Exception as exc:
            logger.error("Error stopping trigger %s: %s", trigger_id, exc)


# Singleton instance — imported by main.py
trigger_service = TriggerListenerService()
