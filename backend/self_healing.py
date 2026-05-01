"""
Self-Healing Engine
===================
When a workflow node fails, the self-healer:
  1. Captures the error + full execution context
  2. Sends it to the LLM with the node's action type and params
  3. Receives a corrected parameter set
  4. Retries execution with the patched params

Safety:
  • Hard retry limit (MAX_HEAL_ATTEMPTS = 3) prevents infinite loops
  • Fallback strategy: skip node with error result after all attempts exhausted
  • Every heal attempt is logged for full auditability
"""

import json
import logging
import os
from typing import Any, Optional, Tuple

logger = logging.getLogger("self_healing")
logger.setLevel(logging.INFO)

if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s  %(name)s  %(message)s"))
    logger.addHandler(_ch)

# ── Constants ───────────────────────────────────────────────────────────────

MAX_HEAL_ATTEMPTS = 3          # absolute cap on LLM-driven retries per node
FALLBACK_STRATEGY = "skip"     # "skip" = mark node as failed-but-continue | "abort" = raise


# ── LLM call to diagnose + fix ──────────────────────────────────────────────

def _call_heal_llm(action: str, params: dict, error: str,
                   context_keys: list, attempt: int) -> Optional[dict]:
    """
    Ask the LLM to diagnose the failure and return corrected params.

    Returns a dict of fixed params, or None if the LLM can't help.
    """
    api_key = os.getenv("MISTRAL_API_KEY", "")
    model_name = os.getenv("MODEL_NAME", "mistral-small")

    # Check for Gemini override
    if "gemini" in model_name.lower():
        api_key = os.getenv("GEMINI_API_KEY", "")
        full_model = model_name
    else:
        if not api_key or api_key == "dummy_for_build":
            logger.warning("No LLM API key configured — self-healing unavailable")
            return None
        full_model = model_name if "/" in model_name else f"mistral/{model_name}"


    prompt = f"""You are a workflow self-healing assistant. A node in an automated workflow has failed.

**Node Action:** {action}
**Current Parameters:** {json.dumps(params, indent=2)}
**Error Message:** {error}
**Available Context Keys:** {context_keys}
**Attempt:** {attempt} of {MAX_HEAL_ATTEMPTS}

Analyze the error and return ONLY a corrected JSON object with the fixed parameters.
Do NOT include any explanation — output ONLY valid JSON.

Rules:
- Fix obvious issues: missing fields, wrong types, placeholder values like "[something]"
- If a parameter references a context key, ensure it matches an available key
- If the error is about a missing environment variable or external service being down, return {{"__unfixable__": true}}
- Never invent data — only fix structural/config issues

Output ONLY the corrected params JSON:"""

    try:
        # Use LiteLLM (same as the rest of the project)
        from litellm import completion

        response = completion(
            model=full_model,
            api_key=api_key,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )


        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        fixed = json.loads(raw)

        if isinstance(fixed, dict) and fixed.get("__unfixable__"):
            logger.info("LLM reports error is unfixable for %s", action)
            return None

        return fixed

    except Exception as llm_err:
        logger.error("Self-heal LLM call failed: %s", llm_err)
        return None


# ── Public API ──────────────────────────────────────────────────────────────

def attempt_self_heal(action: str, original_params: dict, error: Exception,
                      context: dict, node_id: str,
                      log_callback=None) -> Tuple[bool, Any, dict]:
    """
    Attempt to heal a failed node execution via LLM-driven param correction.

    Args:
        action:          The node action string (e.g. "EMAIL_MESSAGE")
        original_params: The params that caused the failure
        error:           The exception that was raised
        context:         Current execution context (results of prior nodes)
        node_id:         The node identifier in the DAG
        log_callback:    Optional callable(message, level) for logging

    Returns:
        (healed: bool, result: Any, final_params: dict)
        • healed=True  → result contains the successful execution output
        • healed=False → all attempts failed, result contains fallback value
    """
    from .nodes import get_node

    def _log(msg, level="INFO"):
        logger.info(msg)
        if log_callback:
            log_callback(msg, level)

    current_params = dict(original_params)
    error_msg = str(error)

    for attempt in range(1, MAX_HEAL_ATTEMPTS + 1):
        _log(f"🔧 SELF-HEAL attempt {attempt}/{MAX_HEAL_ATTEMPTS} for node '{node_id}' "
             f"(action={action}): {error_msg}", "WARNING")

        # Ask the LLM for a fix
        fixed_params = _call_heal_llm(
            action=action,
            params=current_params,
            error=error_msg,
            context_keys=list(context.keys()),
            attempt=attempt,
        )

        if fixed_params is None:
            _log(f"🔧 SELF-HEAL: LLM couldn't produce a fix (attempt {attempt})", "WARNING")
            continue

        _log(f"🔧 SELF-HEAL: LLM suggested params → {json.dumps(fixed_params)}", "INFO")

        # Re-execute with patched params
        node = get_node(action)
        if node is None:
            _log(f"🔧 SELF-HEAL: No node registered for action '{action}'", "ERROR")
            break

        try:
            node.validate(fixed_params)
            result = node.execute(fixed_params, context)
            _log(f"✅ SELF-HEAL SUCCESS on attempt {attempt}: {result}", "INFO")
            return True, result, fixed_params
        except Exception as retry_exc:
            error_msg = str(retry_exc)
            current_params = fixed_params  # feed the updated params back for next attempt
            _log(f"🔧 SELF-HEAL: Retry {attempt} still failed: {error_msg}", "WARNING")

    # All attempts exhausted — apply fallback strategy
    fallback_result = {
        "self_heal_status": "exhausted",
        "original_error": str(error),
        "attempts": MAX_HEAL_ATTEMPTS,
        "fallback": FALLBACK_STRATEGY,
    }

    if FALLBACK_STRATEGY == "skip":
        _log(f"⚠️ SELF-HEAL EXHAUSTED: Skipping node '{node_id}' after {MAX_HEAL_ATTEMPTS} attempts", "WARNING")
        return False, fallback_result, current_params
    else:
        _log(f"❌ SELF-HEAL EXHAUSTED: Aborting workflow at node '{node_id}'", "ERROR")
        return False, fallback_result, current_params
