# AI Workflow Builder

A powerful workflow automation tool that leverages AI agents and crew orchestration to automate complex tasks with integrated services like email, WhatsApp, GitHub, and more.

## Features

- **AI Agent Orchestration**: Uses CrewAI framework for multi-agent coordination
- **Workflow Automation**: Build and execute complex workflows with custom nodes
- **Multiple Integrations**:
  - Email service
  - WhatsApp integration
  - GitHub integration
  - API nodes
  - Desktop automation
  - GUI node
- **Database Support**: SQLite database for workflow state management
- **Memory Management**: Built-in memory system for agent context
- **Self-Healing**: Automatic error recovery and healing mechanisms
- **Trigger Service**: Event-driven workflow execution

## Project Structure

```
├── backend/              # Core backend application
│   ├── agents.py        # AI agent definitions
│   ├── config.py        # Configuration management
│   ├── crew_runner.py   # CrewAI execution engine
│   ├── database.py      # Database models and operations
│   ├── email_service.py # Email integration
│   ├── main.py          # Main application entry
│   ├── memory.py        # Memory management
│   ├── models.py        # Data models
│   ├── tasks.py         # Task definitions
│   ├── trigger_service.py # Workflow triggers
│   ├── workflow.py      # Workflow orchestration
│   ├── self_healing.py  # Error recovery logic
│   └── nodes/           # Workflow nodes
│       ├── api_node.py
│       ├── base.py
│       ├── desktop_nodes.py
│       ├── email_node.py
│       ├── github_node.py
│       ├── gui_node.py
│       ├── misc_nodes.py
│       └── whatsapp_node.py
├── frontend/            # Frontend application
│   └── index.html
├── requirements.txt     # Python dependencies
├── debug_execution.py   # Debug execution script
└── README.md           # This file
```

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Git
- (Optional) Virtual environment tools (venv, virtualenv, etc.)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/sahilc497/ai-workflow-builder.git
cd ai-workflow-builder
```

### 2. Create a Virtual Environment (Recommended)

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Running the Application

### Start the Application

```bash
python backend/main.py
```

### Debug Execution

For debugging and testing:

```bash
python debug_execution.py
```

## Configuration

Edit configuration in `backend/config.py` to setup:
- Database connections
- Email service credentials
- WhatsApp integration
- GitHub tokens
- API endpoints

## Usage Examples

### Creating a Workflow

```python
from backend.workflow import Workflow
from backend.nodes.email_node import EmailNode

workflow = Workflow()
workflow.add_node(EmailNode())
workflow.execute()
```

### Using Triggers

```python
from backend.trigger_service import TriggerService

trigger = TriggerService()
trigger.on_event("email_received", workflow)
```

## Development

### Project Structure Guidelines

- **Agents**: Define AI agents in `backend/agents.py`
- **Tasks**: Define tasks in `backend/tasks.py`
- **Nodes**: Add custom workflow nodes in `backend/nodes/`
- **Services**: Add integrations in `backend/` (e.g., `email_service.py`)

### Adding New Nodes

1. Create a new file in `backend/nodes/`
2. Extend the `BaseNode` class
3. Implement required methods
4. Register in workflow

## Database

The application uses SQLite by default. Database models are defined in `backend/models.py` and managed through `backend/database.py`.

## Troubleshooting

- **Import Errors**: Ensure all dependencies are installed with `pip install -r requirements.txt`
- **Database Issues**: Check database path in `config.py`
- **Service Integration**: Verify credentials in `config.py` for email, WhatsApp, and GitHub services

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or suggestions, please create an issue on the GitHub repository.

---

**Author**: Sahil  
**Repository**: https://github.com/sahilc497/ai-workflow-builder
