"""
Workflow Memory Module
Provides:
  - Semantic similarity search across stored workflow prompts (TF-IDF cosine)
  - Dynamic entity substitution to adapt a matched workflow to new context
"""
import re
import json
import copy
from typing import Optional, Tuple

# ── keywords that indicate the user wants to reuse a past workflow ──────────
MEMORY_TRIGGER_KEYWORDS = [
    "repeat", "same as", "last workflow", "like before", "similar to",
    "do it again", "redo", "again but", "previous workflow", "like last time",
    "same workflow", "as before", "reuse", "copy of"
]


def _is_memory_request(prompt: str) -> bool:
    """Returns True if the prompt looks like a 'repeat / similar' request."""
    lower = prompt.lower()
    return any(kw in lower for kw in MEMORY_TRIGGER_KEYWORDS)


def _extract_entities(text: str) -> list[str]:
    """
    Light-weight named entity extraction using regex.
    Captures capitalised proper nouns (company names, repo names, etc.)
    and emails / URLs.
    """
    entities = []
    # Capitalised words (potential proper nouns / company names)
    entities += re.findall(r'\b[A-Z][a-zA-Z0-9_\-]+\b', text)
    # Email addresses
    entities += re.findall(r'[\w.\-]+@[\w.\-]+\.\w+', text)
    # GitHub-style repo paths  owner/repo
    entities += re.findall(r'\b[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+\b', text)
    # Deduplicate preserving order
    seen, result = set(), []
    for e in entities:
        if e.lower() not in seen:
            seen.add(e.lower())
            result.append(e)
    return result


def substitute_entities(dag_json: dict, original_prompt: str, new_prompt: str) -> dict:
    """
    Swaps entities from `original_prompt` that appear anywhere in the DAG
    with their counterpart entities from `new_prompt`.

    Strategy: pair entities in order of appearance. If the new prompt has
    fewer entities than the original, only substitute as many as we can.
    """
    dag_str = json.dumps(dag_json)

    old_entities = _extract_entities(original_prompt)
    new_entities = _extract_entities(new_prompt)

    # Build a replacement map: old → new (pair by position)
    replacements = {}
    for i, old in enumerate(old_entities):
        if i < len(new_entities):
            replacements[old] = new_entities[i]

    # Apply replacements (longest first to avoid partial matches)
    for old, new in sorted(replacements.items(), key=lambda x: -len(x[0])):
        dag_str = re.sub(re.escape(old), new, dag_str)

    try:
        return json.loads(dag_str)
    except Exception:
        return dag_json  # fall back to original if substitution broke JSON


def find_similar_workflow(prompt: str, db, top_k: int = 1) -> Optional[Tuple[object, float]]:
    """
    Fetches all stored workflows with a prompt, vectorises them with TF-IDF,
    and returns the (workflow, similarity_score) tuple for the closest match.
    Returns None if no stored prompts or similarity < 0.3.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        print("scikit-learn not installed – memory search unavailable.")
        return None

    from .models import Workflow

    # Pull all workflows that have a stored prompt
    stored = db.query(Workflow).filter(Workflow.prompt.isnot(None)).all()
    if not stored:
        return None

    stored_prompts = [w.prompt for w in stored]
    all_texts = stored_prompts + [prompt]   # query goes at the end

    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform(all_texts)
    except Exception as e:
        print(f"TF-IDF vectorisation failed: {e}")
        return None

    # Compare query vector (last row) against all stored vectors
    query_vec = tfidf_matrix[-1]
    stored_vecs = tfidf_matrix[:-1]
    scores = cosine_similarity(query_vec, stored_vecs).flatten()

    best_idx = int(scores.argmax())
    best_score = float(scores[best_idx])

    if best_score < 0.25:       # below threshold → treat as new request
        return None

    return stored[best_idx], best_score


def apply_memory(prompt: str, db) -> Optional[dict]:
    """
    High-level entry point called by crew_runner.
    Returns a modified DAG dict if a similar workflow was found,
    or None to signal that a fresh CrewAI run is needed.
    """
    if not _is_memory_request(prompt):
        return None

    result = find_similar_workflow(prompt, db)
    if result is None:
        return None

    matched_workflow, score = result
    print(f"[Memory] Matched workflow {matched_workflow.id[:8]}… (score={score:.2f})")

    modified_dag = substitute_entities(
        dag_json=copy.deepcopy(matched_workflow.dag_json),
        original_prompt=matched_workflow.prompt or "",
        new_prompt=prompt
    )
    return modified_dag
