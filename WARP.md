# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

τ²-bench (tau2-bench) is a benchmark framework for evaluating conversational agents in dual-control environments. It simulates customer service scenarios where both the agent and user can interact with the environment using tools.

### Core Concepts

**Three-Role Architecture**: The framework orchestrates interactions between three entities:

- **Agent**: Responds to user requests and makes tool calls to solve tasks
- **User**: Either a simulator (LLM-based) or dummy user, provides requests and feedback
- **Environment**: Executes tool calls, maintains state, and validates actions

**Domains**: Self-contained evaluation scenarios with policies, tools, tasks, and databases:

- `mock`: Simple testing domain
- `airline`: Flight booking and management
- `retail`: E-commerce operations
- `telecom`: Telecommunications customer service

**Modes**:

- **Normal Mode**: Agent converses with a user simulator
- **Solo Mode**: Agent works independently on tickets without user interaction (agent can only make tool calls)

### Three-Role Architecture Diagram

```mermaid
graph TB
    subgraph "τ²-bench Framework"
        A[Agent<br/>Responds to requests<br/>Makes tool calls]
        U[User<br/>Simulator or Dummy<br/>Provides requests/feedback]
        E[Environment<br/>Executes tool calls<br/>Maintains state<br/>Validates actions]
        O[Orchestrator<br/>Manages message flow<br/>Enforces protocol]
    end

    A <-->|Messages| U
    A -->|Tool Calls| E
    U -->|Tool Calls| E
    E -->|Tool Results| A
    E -->|Tool Results| U
    O -.->|Coordinates| A
    O -.->|Coordinates| U
    O -.->|Coordinates| E

    style A fill:#e1f5ff
    style U fill:#fff4e1
    style E fill:#e8f5e9
    style O fill:#f3e5f5
```

## Development Commands

### Installation & Setup

```bash
# Install in editable mode (recommended for development)
pip install -e .

# Verify data directory setup
tau2 check-data

# Setup API keys: copy .env.example to .env and configure
```

### Testing

```bash
# Run all tests
make test

# Run domain-specific tests
pytest tests/test_domains/<domain_name>

# Run specific test files
pytest tests/test_agent.py
pytest tests/test_environment.py
pytest tests/test_orchestrator.py
```

### Code Quality

```bash
# Check linting
make lint

# Format code (uses ruff)
make format

# Auto-fix linting issues
make lint-fix

# Run both linting and formatting
make check-all
```

### Running Evaluations

```bash
# Quick test evaluation (5 tasks, 1 trial each)
tau2 run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-trials 1 --num-tasks 5

# Full evaluation on base task split (for benchmarking)
tau2 run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-trials 4 --task-split base

# Solo mode (agent only, no user interaction)
tau2 run --domain telecom --agent llm_agent_solo --agent-llm gpt-4.1 --user dummy_user

# Oracle plan mode (agent given ground-truth plan)
tau2 run --domain telecom --agent llm_agent_gt --agent-llm gpt-4.1 --user-llm gpt-4.1
```

### Interactive Tools

```bash
# Play mode - manually control agent or user
tau2 play

# View simulation results
tau2 view

# View domain documentation (starts server on port 8004)
tau2 domain <domain_name>
# Then visit http://127.0.0.1:8004/redoc

# Environment CLI (interactive testing)
make env-cli
```

### Leaderboard Submission

```bash
# Prepare submission package
tau2 submit prepare data/tau2/simulations/my_model_*.json --output ./my_submission

# Validate submission
tau2 submit validate ./my_submission

# Verify individual trajectories
tau2 submit verify-trajs data/tau2/simulations/my_model_*.json
```

### Cleanup

```bash
make clean  # Remove generated files and virtual environment
```

## Architecture

### Message Flow Protocol

**Message Types**:

- `AssistantMessage`: Agent responses (text or tool calls)
- `UserMessage`: User messages (text or tool calls in domains with user tools)
- `ToolMessage`: Environment responses to tool calls
- `MultiToolMessage`: Wraps multiple tool responses

**Communication Rules**:

1. Messages contain EITHER text OR tool calls, never both
2. Messages cannot be empty
3. Tool calls must be followed by corresponding tool responses from environment

**Turn Sequence**:

```
Agent → User (text response)
Agent → Environment (tool call)
User → Agent (text message)
User → Environment (tool call, if user tools exist)
Environment → Agent (tool result)
Environment → User (tool result)
```

### Message Flow Diagram

```mermaid
sequenceDiagram
    participant A as Agent
    participant O as Orchestrator
    participant U as User
    participant E as Environment

    Note over A,E: Turn Sequence

    A->>O: AssistantMessage (text)
    O->>U: Forward message

    A->>O: AssistantMessage (tool calls)
    O->>E: Execute tool calls

    U->>O: UserMessage (text)
    O->>A: Forward message

    alt User has tools
        U->>O: UserMessage (tool calls)
        O->>E: Execute tool calls
    end

    E->>O: ToolMessage (results)
    O->>A: Forward tool results
    O->>U: Forward tool results

    Note over A,E: Cycle repeats until termination
```

### Core Components

```mermaid
graph LR
    subgraph "Agent Module"
        BA[BaseAgent]
        LA[LocalAgent]
        LLA[LLMAgent]
        LLSA[LLMSoloAgent]
        BA --> LA
        LA --> LLA
        LA --> LLSA
    end

    subgraph "User Module"
        BU[BaseUser]
        US[UserSimulator]
        DU[DummyUser]
        BU --> US
        BU --> DU
    end

    subgraph "Environment Module"
        E[Environment]
        TKB[ToolKitBase]
        AT[Agent Tools]
        UT[User Tools]
        TKB --> AT
        TKB --> UT
        E --> AT
        E --> UT
    end

    subgraph "Orchestrator"
        O[Orchestrator]
    end

    subgraph "Evaluator Module"
        EE[EnvironmentEvaluator]
        NE[NLEvaluator]
    end

    O --> BA
    O --> BU
    O --> E
    O --> EE
    EE --> NE

    style O fill:#f3e5f5
    style E fill:#e8f5e9
    style BA fill:#e1f5ff
    style BU fill:#fff4e1
    style EE fill:#ffe0b2
```

**Orchestrator** (`src/tau2/orchestrator/orchestrator.py`):

- Manages message flow between Agent, User, and Environment
- Enforces communication protocol
- Handles initialization, termination, error tracking
- Validates message history and state transitions

**Agent** (`src/tau2/agent/`):

- `BaseAgent`: Abstract interface all agents must implement
- `LocalAgent`: Base class for custom agent implementations
- `LLMAgent`: Default LLM-based agent
- `LLMSoloAgent`: Agent for solo mode (tool calls only)
- Key methods: `generate_next_message()`, `get_init_state()`, `stop()`

**User** (`src/tau2/user/`):

- `BaseUser`: Abstract user interface
- `UserSimulator`: LLM-based user simulator
- `DummyUser`: No-op user for solo mode
- `UserState`: Tracks conversation state with flipped roles (user as assistant)

**Environment** (`src/tau2/environment/environment.py`):

- Manages domain policy, tools, and state
- `ToolKitBase`: Base class for tool collections
- Separate tool sets for agent and user
- Syncs state between agent/user tools
- Validates actions against task evaluation criteria

**Evaluator** (`src/tau2/evaluator/`):

- `EnvironmentEvaluator`: Compares final environment state against gold standard
- `NLEvaluator`: Uses LLM to evaluate conversation quality
- Reward calculation based on DB state matching and environment assertions

### Data Flow

```mermaid
flowchart TD
    Start([Start Evaluation]) --> Load[Load Task]
    Load --> Task[Task Object]

    Task --> |initial_state| Init[Initialize Environment]
    Task --> |evaluation_criteria| Eval[Evaluation Criteria]

    Init --> Run[Run Simulation]
    Run --> Messages[Message History]
    Run --> State[Environment State]

    Messages --> Sim[Simulation Run Object]
    State --> Sim

    Sim --> |trajectory| Eval
    Eval --> |compare| Compare[Compare States]
    Compare --> Reward[Calculate Reward]

    Reward --> Results[Evaluation Results]
    Results --> Metrics[Final Metrics]
    Metrics --> End([End])

    style Task fill:#e1f5ff
    style Sim fill:#fff4e1
    style Eval fill:#e8f5e9
    style Results fill:#f3e5f5
```

**Task Structure** (`src/tau2/data_model/tasks.py`):

```python
Task:
  - initial_state: InitializationData, actions, message_history
  - evaluation_criteria: Expected actions, environment assertions, reward basis
  - task_id, domain, split
```

**Simulation Run** (`src/tau2/data_model/simulation.py`):

- Complete trajectory with messages, rewards, termination reason
- Agent/user metadata, LLM configurations
- Evaluation results and metrics

### Domain Structure

```mermaid
graph TB
    subgraph "Source Code<br/>src/tau2/domains/domain_name/"
        ENV[environment.py<br/>get_environment<br/>get_tasks]
        DM[data_model.py<br/>Domain DB Class]
        TOOLS[tools.py<br/>Agent Tools<br/>ToolKitBase]
        UTOOLS[user_tools.py<br/>User Tools<br/>Optional]
        UDM[user_data_model.py<br/>User DB<br/>Optional]
    end

    subgraph "Data Files<br/>data/tau2/domains/domain_name/"
        TASKS[tasks.json<br/>Task Definitions]
        SPLIT[split_tasks.json<br/>Task Splits<br/>must include 'base']
        POLICY[policy.md<br/>Domain Policy]
        DB[db.json / db.toml<br/>Environment Database]
        UDB[user_db.json<br/>User Database<br/>Optional]
    end

    subgraph "Registry"
        REG[registry.py<br/>register_domain]
    end

    ENV --> DM
    ENV --> TOOLS
    ENV --> UTOOLS
    TOOLS --> DM
    UTOOLS --> UDM

    ENV --> TASKS
    ENV --> SPLIT
    ENV --> POLICY
    DM --> DB
    UDM --> UDB

    REG --> ENV

    style ENV fill:#e1f5ff
    style DM fill:#e8f5e9
    style TOOLS fill:#fff4e1
    style REG fill:#f3e5f5
```

Each domain in `src/tau2/domains/<domain_name>/`:

- `environment.py`: `get_environment()`, `get_tasks()` functions
- `data_model.py`: Domain-specific DB class
- `tools.py`: Agent tools (ToolKitBase implementation)
- `user_tools.py`: User tools (optional)
- `user_data_model.py`: User DB (optional)

Domain data in `data/tau2/domains/<domain_name>/`:

- `tasks.json`: Task definitions
- `split_tasks.json`: Task splits (must include 'base' split)
- `policy.md`: Domain policy
- `db.json` or `db.toml`: Environment database
- `user_db.json`: User database (optional)

### Registry System

```mermaid
graph TB
    subgraph "Registry<br/>src/tau2/registry.py"
        REG[Central Registry]
    end

    subgraph "Domains"
        D1[mock]
        D2[airline]
        D3[retail]
        D4[telecom]
    end

    subgraph "Agents"
        A1[LLMAgent]
        A2[LLMSoloAgent]
        A3[Custom Agents...]
    end

    subgraph "Users"
        U1[UserSimulator]
        U2[DummyUser]
        U3[Custom Users...]
    end

    REG -->|registers| D1
    REG -->|registers| D2
    REG -->|registers| D3
    REG -->|registers| D4

    REG -->|registers| A1
    REG -->|registers| A2
    REG -->|registers| A3

    REG -->|registers| U1
    REG -->|registers| U2
    REG -->|registers| U3

    style REG fill:#f3e5f5
    style D1 fill:#e1f5ff
    style D2 fill:#e1f5ff
    style D3 fill:#e1f5ff
    style D4 fill:#e1f5ff
```

`src/tau2/registry.py`:

- Central registration for domains, agents, users
- `registry.register_domain(get_environment_func, "domain_name")`
- `registry.register_agent(AgentClass, "agent_name")`
- Auto-discovery of registered components

## Key Implementation Details

### LLM Integration

- Uses LiteLLM for multi-provider support
- API keys configured via `.env` file
- Optional Redis caching (disabled by default, configure in `config.py`)
- Optional Langfuse tracing (disabled by default)

### Task Splits

- All domains have train/test splits
- **IMPORTANT**: Use `--task-split base` for benchmark evaluations to ensure consistency with original τ²-bench
- Default is `base` if not specified

### Configuration

`src/tau2/config.py` contains defaults for:

- Max steps (200), max errors (10)
- LLM models and temperatures
- Redis cache settings
- API port (8000)

### Testing Infrastructure

- `tests/test_domains/`: Domain-specific tool tests
- `tests/test_agent.py`, `test_environment.py`, `test_orchestrator.py`: Core component tests
- `tests/conftest.py`: Shared fixtures

### Gymnasium Interface

`src/tau2/gym/`:

- `AgentGymEnv`: Control agent against user simulator
- `UserGymEnv`: Control user against agent
- Standard gym interface: `reset()`, `step()`, `render()`
- Configure via `solo_mode`, `user_llm`, `agent_llm` parameters

## Development Guidelines

### Adding a New Domain

1. Create domain folder in `src/tau2/domains/<domain_name>/`
2. Implement required files: `environment.py`, `data_model.py`, `tools.py`
3. Create data files in `data/tau2/domains/<domain_name>/`
4. Register domain in `src/tau2/registry.py`
5. Add tests in `tests/test_domains/<domain_name>/`

### Creating a Custom Agent

1. Subclass `LocalAgent` in `src/tau2/agent/base.py`
2. Implement `generate_next_message()` and `get_init_state()`
3. Register in `src/tau2/registry.py`
4. Test with: `tau2 run --agent my_agent --domain <domain> ...`

### Message Validation

- Agent messages must use `validate_message_format()`
- Solo mode has stricter validation (tool calls only, except stop signal)
- Use `is_valid_agent_history_message()` and `is_valid_user_history_message()` for filtering

### Environment State Management

- Call `sync_tools()` after state changes
- Use `set_state()` to initialize or replay from message history
- Implement `get_db_hash()` for environment comparison

### Error Handling

- `AgentError`: Raised for agent-related errors
- `UserError`: Raised for user-related errors
- Orchestrator tracks error count and terminates at max_errors threshold

## Repository Structure Notes

- **Experimental Code**: `src/experiments/` contains research features (self-contained, not core framework)
- **Scripts**: `src/tau2/scripts/` contains CLI command implementations
- **Data Directory**: Set `TAU2_DATA_DIR` environment variable if not using editable install
- **Versioning**: Uses PDM for package management, version in `pyproject.toml`
