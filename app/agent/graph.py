"""LangGraph ReAct agent — core agent graph.

Implements the agent state, tool binding, and message handling.
Uses LangGraph's interrupt() API for action confirmations (M7).
Checkpoint persistence via SQLite at /data/assistant.db.
"""

from __future__ import annotations

import logging
from typing import Any, Annotated

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from typing_extensions import TypedDict

from agent.context_assembler import ContextAssembler
from agent.prompts import build_system_prompt
from agent.router import LLMRouter

_LOGGER = logging.getLogger(__name__)


class AgentState(TypedDict):
    """State for the LangGraph ReAct agent."""

    messages: Annotated[list, add_messages]
    user_profile: dict
    ha_context: str
    chat_id: int
    conversation_id: str


class PersonalAssistantAgent:
    """LangGraph-based personal assistant agent.

    Handles Telegram events, runs the agent graph, and sends responses
    back via the HA REST API.
    """

    def __init__(
        self,
        config: dict[str, Any],
        ha_client: Any,
        llm_router: LLMRouter,
        profile_manager: Any,
        conversation_memory: Any,
        rag_engine: Any,
    ) -> None:
        self._config = config
        self._ha = ha_client
        self._llm_router = llm_router
        self._profile_manager = profile_manager
        self._conversation_memory = conversation_memory
        self._rag_engine = rag_engine
        self._learning_worker: Any | None = None
        self._context_assembler = ContextAssembler()
        self._graph = self._build_graph()
        self._checkpointer: AsyncSqliteSaver | None = None

    def set_learning_worker(self, worker: Any) -> None:
        """Set the learning worker for post-response processing."""
        self._learning_worker = worker

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph agent graph."""
        from tools.ha_tools import create_ha_tools
        from tools.web_search import create_search_tool
        from tools.profile_tools import create_profile_tools
        from tools.rag_tools import create_rag_tool

        # Create all tools
        tools = []
        tools.extend(create_ha_tools(self._ha, self._config))
        tools.append(create_search_tool(self._config))
        tools.extend(create_profile_tools(self._profile_manager))
        tools.append(create_rag_tool(self._rag_engine))

        # Bind tools to the LLM
        llm = self._llm_router.get_chat_model()
        llm_with_tools = llm.bind_tools(tools)

        # Define the agent node
        async def agent_node(state: AgentState) -> dict:
            """Run the LLM with tools."""
            response = await llm_with_tools.ainvoke(state["messages"])
            return {"messages": [response]}

        # Define should_continue logic
        def should_continue(state: AgentState) -> str:
            """Route to tools or end based on last message."""
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return END

        # Build graph
        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", ToolNode(tools))

        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", should_continue, {
            "tools": "tools",
            END: END,
        })
        graph.add_edge("tools", "agent")

        return graph

    async def _get_checkpointer(self) -> AsyncSqliteSaver:
        """Get or create the SQLite checkpointer for graph persistence."""
        if self._checkpointer is None:
            from const import DB_PATH
            self._checkpointer = AsyncSqliteSaver.from_conn_string(
                f"{DB_PATH}_checkpoints"
            )
        return self._checkpointer

    async def handle_telegram_text(self, event_data: dict[str, Any]) -> None:
        """Handle incoming Telegram text messages.

        Called by HAClient when a telegram_text event is received
        via WebSocket.
        """
        chat_id = event_data.get("chat_id")
        text = event_data.get("text", "")
        user_name = event_data.get("from_first", "User")

        if not chat_id or not text:
            return

        _LOGGER.info(
            "Telegram message from %s (chat %s): %s",
            user_name,
            chat_id,
            text[:50],
        )

        try:
            response = await self._process_message(chat_id, text, user_name)
            await self._send_telegram_response(chat_id, response)
        except Exception:
            _LOGGER.exception("Error processing message from chat %s", chat_id)
            await self._send_telegram_response(
                chat_id, "Sorry, I encountered an error processing your message."
            )

    async def handle_telegram_callback(
        self, event_data: dict[str, Any]
    ) -> None:
        """Handle Telegram inline keyboard callbacks.

        Used for action confirmations (M7 — Action Permission Layer).
        """
        chat_id = event_data.get("chat_id")
        callback_data = event_data.get("data", "")

        if not chat_id or not callback_data:
            return

        _LOGGER.info(
            "Telegram callback from chat %s: %s", chat_id, callback_data
        )

        # Parse callback: format is "confirm:{action_id}:yes" or "confirm:{action_id}:no"
        parts = callback_data.split(":")
        if len(parts) != 3 or parts[0] != "confirm":
            return

        action_id = parts[1]
        approved = parts[2] == "yes"

        # Resume the interrupted graph with the confirmation result
        try:
            checkpointer = await self._get_checkpointer()
            config = {"configurable": {"thread_id": f"confirm_{action_id}"}}

            # Resume the graph with the approval/rejection
            compiled = self._graph.compile(checkpointer=checkpointer)
            result = await compiled.ainvoke(
                {"messages": [HumanMessage(
                    content=f"Action {'approved' if approved else 'rejected'} by user."
                )]},
                config=config,
            )

            # Send the result
            last_msg = result["messages"][-1]
            if hasattr(last_msg, "content"):
                await self._send_telegram_response(chat_id, last_msg.content)
        except Exception:
            _LOGGER.exception("Error handling callback for action %s", action_id)

    async def _process_message(
        self, chat_id: int, text: str, user_name: str
    ) -> str:
        """Process a user message through the full agent pipeline."""
        # 1. Get or create conversation session
        session = await self._conversation_memory.get_or_create_session(
            chat_id
        )

        # 2. Build token-budgeted context
        context = await self._context_assembler.build_context(
            query=text,
            ha_client=self._ha,
            profile_manager=self._profile_manager,
            conversation_history=await self._conversation_memory.get_history(
                session["id"]
            ),
            rag_results=await self._rag_engine.retrieve(text),
        )

        # 3. Build system prompt
        is_cloud = self._llm_router.is_cloud
        system_prompt = build_system_prompt(
            persona=self._config.get(
                "persona", "You are a helpful personal home assistant."
            ),
            profile_context=context.get("profile_context", ""),
            ha_context=context.get("ha_context", ""),
            is_cloud_llm=is_cloud,
            send_profile_to_cloud=self._config.get(
                "cloud_llm_send_profile", False
            ),
            send_ha_state_to_cloud=self._config.get(
                "cloud_llm_send_ha_state", False
            ),
        )

        # 4. Assemble messages
        messages = [SystemMessage(content=system_prompt)]

        # Add conversation history context
        history_context = context.get("history_context", "")
        if history_context:
            messages.append(SystemMessage(
                content=f"Recent conversation:\n{history_context}"
            ))

        # Add RAG context
        rag_context = context.get("rag_context", "")
        if rag_context:
            messages.append(SystemMessage(
                content=f"Relevant knowledge:\n{rag_context}"
            ))

        # Add current user message
        messages.append(HumanMessage(content=text))

        # 5. Run the agent graph
        checkpointer = await self._get_checkpointer()
        compiled = self._graph.compile(checkpointer=checkpointer)

        config = {
            "configurable": {
                "thread_id": session["id"],
            }
        }

        result = await compiled.ainvoke(
            {
                "messages": messages,
                "user_profile": {},
                "ha_context": context.get("ha_context", ""),
                "chat_id": chat_id,
                "conversation_id": session["id"],
            },
            config=config,
        )

        # 6. Extract response
        last_message = result["messages"][-1]
        response_text = (
            last_message.content
            if hasattr(last_message, "content")
            else str(last_message)
        )

        # 7. Save to conversation history
        await self._conversation_memory.add_message(
            session["id"], chat_id, "user", text
        )
        await self._conversation_memory.add_message(
            session["id"], chat_id, "assistant", response_text
        )

        # 8. Queue interaction for learning (decoupled — never in response path)
        if self._learning_worker:
            await self._learning_worker.queue_interaction(
                session_id=session["id"],
                chat_id=chat_id,
                user_message=text,
                assistant_response=response_text,
                tools_used=[],  # TODO: extract from result
                entities_mentioned=[],
            )

        return response_text

    async def _send_telegram_response(
        self, chat_id: int, message: str
    ) -> None:
        """Send a response back via HA Telegram service (REST API)."""
        try:
            await self._ha.call_service("telegram_bot", "send_message", {
                "message": message,
                "target": chat_id,
                "parse_mode": "markdown",
            })
        except Exception:
            _LOGGER.exception("Failed to send Telegram message to %s", chat_id)
