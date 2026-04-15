# ReflexionOS

AI-powered autonomous coding agent that runs locally on your machine.

## Quick Start

### 1. Install Dependencies

**Backend:**
```bash
cd backend
pip install -r requirements.txt
```

**Frontend:**
```bash
cd frontend
npm install
```

### 2. Start Services

**Terminal 1 - Backend:**
```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### 3. Access the Application

- Frontend: http://localhost:5173
- Backend API: http://127.0.0.1:8000
- API Docs: http://127.0.0.1:8000/docs

## Usage

1. **Configure LLM**: Go to Settings page, enter your OpenAI API key
2. **Create Project**: Go to Projects page, create a new project with a local path
3. **Execute Tasks**: Go to Agent page, select a project, describe your task, and click Execute

## Features

- **File Operations**: Read, write, list, and delete files
- **Shell Commands**: Execute safe shell commands
- **Patch Tool**: Apply unified diff patches for precise code modifications
- **Autonomous Execution**: AI agent that can plan and execute multi-step tasks

## Project Structure

```
ReflexionOS/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/            # API routes
│   │   ├── execution/      # Agent execution engine
│   │   ├── llm/            # LLM adapters
│   │   ├── models/         # Data models
│   │   ├── orchestration/  # Skills & MCP
│   │   ├── security/       # Security controls
│   │   ├── services/       # Business services
│   │   ├── storage/        # Persistence layer
│   │   └── tools/          # Tool implementations
│   └── tests/              # Backend tests
├── frontend/                # React frontend
│   └── src/
│       ├── components/     # UI components
│       ├── pages/          # Page components
│       ├── services/       # API clients
│       ├── stores/         # State management
│       └── types/          # TypeScript types
└── docs/                    # Documentation
```

## Test

```bash
cd backend
pytest tests/ -v
```

Current test status: **77 tests passing**

## License

MIT
