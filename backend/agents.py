import os
from crewai import Agent, LLM
from textwrap import dedent
from dotenv import load_dotenv
load_dotenv()

def get_llm():
    api_key = os.getenv("MISTRAL_API_KEY")
    model_name = os.getenv("MODEL_NAME", "mistral-small")
    
    if not api_key:
        api_key = "dummy_for_build"
    
    # Standard format for CrewAI/LiteLLM with Mistral
    full_model = model_name if "/" in model_name else f"mistral/{model_name}"
    
    return LLM(model=full_model, api_key=api_key)

class WorkflowAgents:
    def __init__(self):
        self.llm = get_llm()

    def planner_agent(self):
        return Agent(
            role="Workflow Architecture Planner",
            goal="Analyze natural language requirements and plan a structured, node-based workflow (DAG).",
            backstory=dedent("""You are an expert system architect capable of breaking down complex prompts into step-by-step parallel and sequential processes. You only output valid JSON representations of workflows."""),
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
        )
        
    def reviewer_agent(self):
        return Agent(
            role="Systems Workflow Reviewer",
            goal="Ensure the workflow JSON proposed by the planner is valid, optimal, and inherently safe.",
            backstory=dedent("""You rigorously review and refine system workflows to prevent logical bugs, infinite loops, or vulnerabilities. You ensure accurate JSON syntax corresponding to a workflow DAG."""),
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
        )

    def executor_agent(self):
        return Agent(
            role="Execution Preparer",
            goal="Finalize the verified JSON workflow DAG making sure parameters are all correctly set up for LangGraph.",
            backstory=dedent("""You take a correct logical workflow and format it exactly for the execution engine, ensuring structure compliance."""),
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
        )
