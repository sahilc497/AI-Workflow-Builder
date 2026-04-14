from crewai import Task
from textwrap import dedent

class WorkflowTasks:
    def plan_workflow_task(self, agent, prompt):
        return Task(
            description=dedent(f"""
                Analyze the following requirement: "{prompt}"
                Create a structured DAG representation and provide a step-by-step explanation.
                
                You must return a JSON object with EXACTLY this structure:
                {{
                  "workflow": {{
                    "nodes": [...],
                    "edges": [...]
                  }},
                  "explanation": [
                    "Step 1: API call to fetch data because...",
                    "Step 2: Condition node to check..."
                  ]
                }}
                
                Each node must have:
                  - "id": unique string
                  - "action": MUST be EXACTLY one of the supported types listed below
                  - "params": a dict of configuration values
                
                Edges must have "from" and "to" fields referencing node IDs.

                === SUPPORTED ACTION TYPES ===

                INTERNET / API:
                  API_CALL         → params: url
                  WEB_SEARCH       → params: query  (use for any "search", "find news", "look up")
                  GITHUB_PR        → params: repo_owner, repo_name
                  GITHUB_API_CALL  → params: endpoint, method
                  GITHUB_ACTION    → params: github_action_type (create_issue|list_issues|get_repo_status|create_repo), repo_owner, repo_name
                  LLM_PROMPT       → params: prompt (text with optional {{{{node_id}}}} placeholders)
                  EXTRACT_DATA     → params: data_ref (node_id of source), key_to_extract

                MESSAGING:
                  EMAIL / EMAIL_MESSAGE → params: to, subject, body
                  WHATSAPP_MESSAGE      → params: contact (name as in WhatsApp, e.g. "Dad"), message

                DESKTOP / OFFICE:
                  DESKTOP_APP           → params: app ("word"|"excel"|"powerpoint"|"chrome"|"notepad"|"calculator"|any exe name), file (optional path to open)
                  CREATE_DOCUMENT       → params: filename (.docx), title, content or content_ref (node_id)
                  CREATE_SPREADSHEET    → params: filename (.xlsx), data (list of row arrays)
                  CREATE_PRESENTATION   → params: filename (.pptx), title, slides (list of {{heading, body}})
                  BROWSER_ACTION        → params: url, action ("open"|"get_text"|"screenshot")

                PC AUTOMATION:
                  GUI_AUTOMATION  → params: actions (list of steps: {{type: "type"|"press"|"hotkey"|"click"|"wait", text/key/keys/seconds}})
                  APP_CONTROL     → params: app_title (window title), actions (list of steps)

                UTILITIES:
                  TIME / GET_TIME → no params needed

                === RULES ===
                - WHATSAPP_MESSAGE: use the contact's name EXACTLY as it appears in the user's WhatsApp contacts.
                - CREATE_DOCUMENT/SPREADSHEET/PRESENTATION: set content_ref to the node_id of the step that generates your content (e.g. a WEB_SEARCH node).
                - DESKTOP_APP: to open a file created by a previous node, set file_ref to that node_id.
                - NEVER use placeholders like "[Insert Here]". Use real values from the prompt.
                - Provide ONLY valid JSON, no markdown.
            """),
            expected_output="A valid JSON string containing 'workflow' (with 'nodes' and 'edges') and 'explanation' keys.",
            agent=agent
        )

    def review_workflow_task(self, agent):
        return Task(
            description=dedent("""
                Review the previously generated workflow JSON.
                Ensure it follows a valid DAG structure inside the 'workflow' key, and contains an 'explanation' array. 
                Avoid loops.
                CHECK: Ensure NO placeholders (like square brackets with text) exist in the parameters.
                If placeholders exist, REPLACE them with the actual data from the user requirement.
                Output ONLY the final verified JSON. Do not include markdown formatting or extra text.
            """),
            expected_output="A valid JSON string of the reviewed workflow and explanation without markdown formatting.",
            agent=agent
        )
        
    def execute_prep_task(self, agent):
        return Task(
            description=dedent("""
                Prepare the JSON for execution. Just return the valid JSON string exactly as constructed, ensuring formatting is pristine.
                Do not include markdown blocks like ```json ... ```. Just the raw JSON.
            """),
            expected_output="Raw JSON string.",
            agent=agent
        )
