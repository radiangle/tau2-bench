"""
LangChain Agent implementation for tau2-bench.

This agent uses LangGraph's create_react_agent to provide a conversational
agent that can interact with domain tools.
"""

import os
from copy import deepcopy
from typing import List, Optional

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage as LangChainSystemMessage,
)
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from loguru import logger
from pydantic import BaseModel

from tau2.agent.base import (
    LocalAgent,
    ValidAgentInputMessage,
    is_valid_agent_history_message,
)
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.environment.tool import Tool

AGENT_INSTRUCTION = """
You are a customer service agent that helps the user according to the <policy> provided below.
In each turn you can either:
- Send a message to the user.
- Make a tool call.
You cannot do both at the same time.

Try to be helpful and always follow the policy. Always make sure you generate valid JSON only.
""".strip()

SYSTEM_PROMPT = """
<instructions>
{agent_instruction}
</instructions>
<policy>
{domain_policy}
</policy>
""".strip()


class LangChainAgentState(BaseModel):
    """The state of the LangChain agent."""

    system_messages: list[SystemMessage]
    messages: list[APICompatibleMessage]
    langchain_messages: list  # Store LangChain messages for the agent


class LangChainAgent(LocalAgent[LangChainAgentState]):
    """
    A LangChain agent that uses LangGraph's create_react_agent.
    """

    def __init__(
        self,
        tools: List[Tool],
        domain_policy: str,
        llm: Optional[str] = None,
        llm_args: Optional[dict] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the LangChainAgent.

        Args:
            tools: List of tau2 Tool objects
            domain_policy: Domain policy document
            llm: LLM model name (e.g., "openai/gpt-oss-120b")
            llm_args: Additional LLM parameters
            base_url: Optional base URL for the LLM API
            api_key: Optional API key (if not provided, will use environment variable)
        """
        super().__init__(tools=tools, domain_policy=domain_policy)
        self.llm = llm
        self.llm_args = deepcopy(llm_args) if llm_args is not None else {}
        self.base_url = base_url
        self.api_key = api_key

        # Convert tau2 tools to LangChain tools
        self.langchain_tools = self._convert_tools_to_langchain(tools)

        # Initialize LangChain LLM
        self.langchain_llm = self._create_langchain_llm()

        # Create LangGraph agent
        self.system_prompt_text = SYSTEM_PROMPT.format(
            domain_policy=self.domain_policy, agent_instruction=AGENT_INSTRUCTION
        )
        self.agent = create_react_agent(
            self.langchain_llm, self.langchain_tools, prompt=self.system_prompt_text
        )

    def _create_langchain_llm(self) -> ChatOpenAI:
        """Create a LangChain ChatOpenAI instance."""
        llm_kwargs = deepcopy(self.llm_args) if self.llm_args else {}

        # Handle base_url and api_key
        if self.base_url:
            llm_kwargs["base_url"] = self.base_url
        if self.api_key:
            llm_kwargs["api_key"] = self.api_key
        elif "api_key" not in llm_kwargs:
            # Try to get from environment if using Nebius API
            # Check if base_url points to Nebius or model name contains "nebius"
            is_nebius = (self.base_url and "nebius" in self.base_url.lower()) or (
                self.llm and "nebius" in self.llm.lower()
            )
            if is_nebius:
                api_key = os.getenv("NEBIUS_API_KEY")
                if api_key:
                    llm_kwargs["api_key"] = api_key
                    logger.debug("Loaded NEBIUS_API_KEY from environment")

        return ChatOpenAI(model=self.llm, **llm_kwargs)

    def _convert_tools_to_langchain(self, tools: List[Tool]) -> List[StructuredTool]:
        """Convert tau2 Tool objects to LangChain StructuredTool objects."""
        langchain_tools = []

        for tool in tools:
            # Create a wrapper function that calls the tau2 tool
            # Use a closure to capture the tool properly
            def make_tool_func(tau2_tool: Tool):
                def tool_func(**kwargs):
                    try:
                        result = tau2_tool(**kwargs)
                        # Convert result to string if needed
                        if isinstance(result, (dict, list)):
                            import json

                            return json.dumps(result, indent=2)
                        return str(result) if result is not None else ""
                    except Exception as e:
                        logger.error(f"Error calling tool {tau2_tool.name}: {e}")
                        import traceback

                        logger.debug(traceback.format_exc())
                        return f"Error: {str(e)}"

                # Set function name and docstring for better debugging
                tool_func.__name__ = tau2_tool.name
                tool_func.__doc__ = tau2_tool._get_description()
                return tool_func

            # Get the function signature from the tool
            tool_func = make_tool_func(tool)

            # Create LangChain StructuredTool
            langchain_tool = StructuredTool.from_function(
                func=tool_func,
                name=tool.name,
                description=tool._get_description(),
                args_schema=tool.params,
            )
            langchain_tools.append(langchain_tool)

        return langchain_tools

    @property
    def system_prompt(self) -> str:
        return self.system_prompt_text

    def _tau2_to_langchain_message(self, message: Message) -> Optional[object]:
        """Convert a tau2 message to a LangChain message."""
        if isinstance(message, UserMessage):
            return HumanMessage(content=message.content or "")
        elif isinstance(message, AssistantMessage):
            # LangGraph agent handles assistant messages internally
            # We'll convert tool calls separately if needed
            return AIMessage(content=message.content or "")
        elif isinstance(message, ToolMessage):
            # Tool messages are handled by LangGraph internally
            from langchain_core.messages import ToolMessage as LangChainToolMessage

            return LangChainToolMessage(
                content=message.content or "", tool_call_id=message.id
            )
        elif isinstance(message, SystemMessage):
            return LangChainSystemMessage(content=message.content or "")
        return None

    def _langchain_to_tau2_assistant_message(
        self, langchain_messages: list
    ) -> AssistantMessage:
        """Convert LangGraph agent output to tau2 AssistantMessage."""
        # Get the last message (should be AIMessage from agent)
        last_msg = langchain_messages[-1] if langchain_messages else None

        content = None
        tool_calls = None

        if last_msg:
            # Check if it's an AIMessage with content
            if hasattr(last_msg, "content") and last_msg.content:
                content = last_msg.content

            # Check for tool calls in the last message
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                tool_calls = []
                for tc in last_msg.tool_calls:
                    # Handle different tool call formats
                    if isinstance(tc, dict):
                        # Extract arguments - could be in 'args' or 'arguments'
                        args = tc.get("args", tc.get("arguments", {}))
                        # If args is a string, try to parse as JSON
                        if isinstance(args, str):
                            import json

                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, ValueError):
                                args = {}
                        tool_calls.append(
                            ToolCall(
                                id=tc.get("id", ""),
                                name=tc.get("name", ""),
                                arguments=args,
                            )
                        )
                    else:
                        # LangChain tool call object
                        args = getattr(tc, "args", getattr(tc, "arguments", {}))
                        if isinstance(args, str):
                            import json

                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, ValueError):
                                args = {}
                        tool_calls.append(
                            ToolCall(
                                id=getattr(tc, "id", ""),
                                name=getattr(tc, "name", ""),
                                arguments=args,
                            )
                        )

        # If no content and no tool calls, provide a default message
        if not content and not tool_calls:
            content = "I'm ready to help you."

        return AssistantMessage(
            role="assistant", content=content, tool_calls=tool_calls or None
        )

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> LangChainAgentState:
        """Get the initial state of the agent.

        Args:
            message_history: The message history of the conversation.

        Returns:
            The initial state of the agent.
        """
        if message_history is None:
            message_history = []
        assert all(is_valid_agent_history_message(m) for m in message_history), (
            "Message history must contain only AssistantMessage, UserMessage, or ToolMessage to Agent."
        )

        # Convert message history to LangChain format
        langchain_messages = []
        for msg in message_history:
            lc_msg = self._tau2_to_langchain_message(msg)
            if lc_msg:
                langchain_messages.append(lc_msg)

        return LangChainAgentState(
            system_messages=[SystemMessage(role="system", content=self.system_prompt)],
            messages=message_history,
            langchain_messages=langchain_messages,
        )

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: LangChainAgentState
    ) -> tuple[AssistantMessage, LangChainAgentState]:
        """
        Respond to a user or tool message using LangGraph agent.
        """
        # Add the new message to state
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
            # Convert tool messages to LangChain format
            for tm in message.tool_messages:
                lc_msg = self._tau2_to_langchain_message(tm)
                if lc_msg:
                    state.langchain_messages.append(lc_msg)
        else:
            state.messages.append(message)
            lc_msg = self._tau2_to_langchain_message(message)
            if lc_msg:
                state.langchain_messages.append(lc_msg)

        # Invoke LangGraph agent with current message history
        try:
            result = self.agent.invoke({"messages": state.langchain_messages})

            # Extract the updated messages from LangGraph result
            # LangGraph returns a dict with "messages" key containing the full conversation
            updated_langchain_messages = result.get(
                "messages", state.langchain_messages
            )

            # Convert the last assistant message to tau2 format
            assistant_message = self._langchain_to_tau2_assistant_message(
                updated_langchain_messages
            )

            # Validate the message format
            from tau2.agent.base import validate_message_format

            is_valid, error_msg = validate_message_format(assistant_message)
            if not is_valid:
                logger.warning(f"Invalid message format: {error_msg}")
                # Try to fix: if both content and tool_calls exist, prefer tool_calls
                if (
                    assistant_message.has_text_content()
                    and assistant_message.is_tool_call()
                ):
                    assistant_message.content = None

            # Update state with new messages
            state.messages.append(assistant_message)
            state.langchain_messages = updated_langchain_messages

        except Exception as e:
            logger.error(f"Error in LangGraph agent invocation: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            # Fallback: create a simple text response
            assistant_message = AssistantMessage(
                role="assistant",
                content=f"I apologize, but I encountered an error: {str(e)}",
            )
            state.messages.append(assistant_message)

        return assistant_message, state

    def set_seed(self, seed: int):
        """Set the seed for the LLM."""
        if self.llm is None:
            raise ValueError("LLM is not set")
        cur_seed = self.llm_args.get("seed", None)
        if cur_seed is not None:
            logger.warning(f"Seed is already set to {cur_seed}, resetting it to {seed}")
        self.llm_args["seed"] = seed
        # Recreate LLM with new seed
        self.langchain_llm = self._create_langchain_llm()
        self.agent = create_react_agent(
            self.langchain_llm, self.langchain_tools, prompt=self.system_prompt_text
        )
