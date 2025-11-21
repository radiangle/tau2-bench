# Agent Developer Guide

> 📚 **For comprehensive documentation**, see [AGENT_DOCUMENTATION.md](./AGENT_DOCUMENTATION.md)

## Quick Start

### Understanding the Environment

To develop an agent for a specific domain, you first need to understand the domain's policy and available tools. Start by running the environment server for your target domain:

```bash
tau2 domain <domain>
```

This will start a server and automatically open your browser to the API documentation page (ReDoc). Here you can:
- Review the available tools (API endpoints) for the domain
- Understand the policy requirements and constraints
- Test API calls directly through the documentation interface

### Developing an Agent

1. **Implement the `LocalAgent` class**:
   - Inherit from `LocalAgent` in `src/tau2/agent/base.py`
   - Implement required methods: `generate_next_message()`, `get_init_state()`
   - See `LLMAgent` in `llm_agent.py` for a reference implementation

2. **Register your agent**:
   ```python
   from tau2.registry import registry
   registry.register_agent(MyAgent, "my_agent")
   ```

3. **Test your agent**:
   ```bash
   tau2 run \
     --domain <domain> \
     --agent my_agent \
     --agent-llm <llm_name> \
     --user-llm <llm_name> \
     ...
   ```

## Available Agent Types

- **LLMAgent**: Standard conversational agent with LLM backend
- **LLMGTAgent**: Ground truth agent with oracle action guidance
- **LLMSoloAgent**: Solo agent that works without user interaction

See [AGENT_DOCUMENTATION.md](./AGENT_DOCUMENTATION.md) for detailed explanations of each agent type.

## Documentation

- **[AGENT_DOCUMENTATION.md](./AGENT_DOCUMENTATION.md)**: Comprehensive documentation covering:
  - Architecture and class hierarchy
  - Detailed API reference
  - Message types and validation
  - State management
  - Error handling
  - Extension guide
  - Troubleshooting