from .agents import WorkflowAgents
from .tasks import WorkflowTasks
from crewai import Crew
import json


def generate_workflow_from_prompt(prompt: str, db=None):
    """
    Generates a workflow DAG from the user prompt.
    If `db` is supplied and the prompt looks like a 'repeat/similar' request,
    the memory module will attempt to find and adapt a past workflow first,
    skipping the expensive CrewAI round-trip entirely.
    """
    # ── Memory short-circuit ────────────────────────────────────────────────
    if db is not None:
        try:
            from .memory import apply_memory
            memory_dag = apply_memory(prompt, db)
            if memory_dag is not None:
                print("[Memory] Returning adapted workflow from memory — skipping CrewAI.")
                return memory_dag
        except Exception as mem_err:
            print(f"[Memory] Memory lookup failed (falling back to CrewAI): {mem_err}")

    # ── Normal CrewAI generation ────────────────────────────────────────────
    agents = WorkflowAgents()
    tasks = WorkflowTasks()

    planner = agents.planner_agent()
    reviewer = agents.reviewer_agent()
    executor = agents.executor_agent()

    plan_task = tasks.plan_workflow_task(planner, prompt)
    review_task = tasks.review_workflow_task(reviewer)
    exec_task = tasks.execute_prep_task(executor)

    crew = Crew(
        agents=[planner, reviewer, executor],
        tasks=[plan_task, review_task, exec_task],
        verbose=True
    )

    result = crew.kickoff()

    # Try parsing
    try:
        raw_output = result.raw
        # Clean markdown if present
        if "```json" in raw_output:
            raw_output = raw_output.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_output:
            raw_output = raw_output.split("```")[1].strip()

        parsed_json = json.loads(raw_output)
        return parsed_json
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return {"error": "Failed to parse workflow", "raw_output": str(result.raw)}
