"""Unit tests for agent nodes with token tracking."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.agent.state import AgentState, TokenBudgetState, create_initial_state
from src.agent.nodes import (
    get_token_manager,
    reset_token_manager,
    update_token_budget,
    track_message_tokens,
    track_tool_tokens,
)
from src.agent.tokenization import TokenBudgetManager


class TestTokenBudgetState:
    """Test TokenBudgetState TypedDict."""

    def test_create_token_budget_state(self):
        """Test creating a TokenBudgetState."""
        state = TokenBudgetState(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            budget_max=100_000,
            budget_remaining=99_850,
            last_update_ts="2025-12-15T10:00:00",
            model="gpt-4",
            should_summarize=False,
        )

        assert state["prompt_tokens"] == 100
        assert state["completion_tokens"] == 50
        assert state["total_tokens"] == 150
        assert state["budget_max"] == 100_000
        assert state["budget_remaining"] == 99_850
        assert state["model"] == "gpt-4"
        assert state["should_summarize"] is False


class TestAgentState:
    """Test AgentState TypedDict with token budget."""

    def test_agent_state_with_token_budget(self):
        """Test AgentState includes token_budget field."""
        state = AgentState(
            run_id="test-run",
            user_query="test query",
            messages=[],
            scope={},
            phase="diagnose",
            token_budget=TokenBudgetState(
                prompt_tokens=0,
                total_tokens=0,
                budget_max=100_000,
                budget_remaining=100_000,
            ),
        )

        assert "token_budget" in state
        assert state["token_budget"]["budget_max"] == 100_000


class TestCreateInitialState:
    """Test create_initial_state function."""

    def test_create_initial_state_defaults(self):
        """Test create_initial_state with defaults."""
        messages = [HumanMessage(content="Hello")]
        state = create_initial_state(
            run_id="run-123",
            user_query="Hello",
            messages=messages,
        )

        assert state["run_id"] == "run-123"
        assert state["user_query"] == "Hello"
        assert state["phase"] == "diagnose"
        assert state["status"] == "running"

        # Check token budget
        assert "token_budget" in state
        token_budget = state["token_budget"]
        assert token_budget["budget_max"] == 100_000
        assert token_budget["budget_remaining"] == 100_000
        assert token_budget["prompt_tokens"] == 0
        assert token_budget["total_tokens"] == 0
        assert token_budget["should_summarize"] is False

    def test_create_initial_state_custom_budget(self):
        """Test create_initial_state with custom budget."""
        messages = [HumanMessage(content="Test")]
        state = create_initial_state(
            run_id="run-456",
            user_query="Test",
            messages=messages,
            budget_max=50_000,
        )

        assert state["token_budget"]["budget_max"] == 50_000
        assert state["token_budget"]["budget_remaining"] == 50_000


class TestTokenManagerFunctions:
    """Test token manager helper functions."""

    def setup_method(self):
        """Reset token manager before each test."""
        reset_token_manager()

    def teardown_method(self):
        """Reset token manager after each test."""
        reset_token_manager()

    def test_get_token_manager_creates_new(self):
        """Test get_token_manager creates new manager."""
        manager = get_token_manager()
        assert manager is not None
        assert isinstance(manager, TokenBudgetManager)
        assert manager.max_tokens == 100_000

    def test_get_token_manager_returns_same(self):
        """Test get_token_manager returns same instance."""
        manager1 = get_token_manager()
        manager2 = get_token_manager()
        assert manager1 is manager2

    def test_get_token_manager_custom_params(self):
        """Test get_token_manager with custom parameters."""
        manager = get_token_manager(max_tokens=50_000)
        assert manager.max_tokens == 50_000

    def test_reset_token_manager(self):
        """Test reset_token_manager clears the manager."""
        manager1 = get_token_manager()
        manager1.reserve_tokens(100)
        assert manager1.tokens_used == 100

        reset_token_manager()

        manager2 = get_token_manager()
        assert manager2.tokens_used == 0
        assert manager2 is not manager1


class TestUpdateTokenBudget:
    """Test update_token_budget function."""

    def setup_method(self):
        """Reset token manager before each test."""
        reset_token_manager()

    def teardown_method(self):
        """Reset token manager after each test."""
        reset_token_manager()

    def test_update_token_budget_initial(self):
        """Test update_token_budget with fresh manager."""
        manager = get_token_manager()
        state = AgentState()

        budget = update_token_budget(state, manager, "diagnose")

        assert budget["prompt_tokens"] == 0
        assert budget["total_tokens"] == 0
        assert budget["budget_max"] == 100_000
        assert budget["budget_remaining"] == 100_000
        assert budget["should_summarize"] is False
        assert "last_update_ts" in budget

    def test_update_token_budget_after_usage(self):
        """Test update_token_budget after some token usage."""
        manager = get_token_manager(max_tokens=1000)
        manager.reserve_tokens(500)
        state = AgentState()

        budget = update_token_budget(state, manager, "verify")

        assert budget["prompt_tokens"] == 500
        assert budget["total_tokens"] == 500
        assert budget["budget_max"] == 1000
        assert budget["budget_remaining"] == 500
        assert budget["should_summarize"] is False

    def test_update_token_budget_near_limit(self):
        """Test update_token_budget when near budget limit."""
        manager = get_token_manager(max_tokens=1000)
        manager.reserve_tokens(850)  # 85% usage
        state = AgentState()

        budget = update_token_budget(state, manager, "optimize")

        assert budget["should_summarize"] is True


class TestTrackMessageTokens:
    """Test track_message_tokens function."""

    def setup_method(self):
        """Reset token manager before each test."""
        reset_token_manager()

    def teardown_method(self):
        """Reset token manager after each test."""
        reset_token_manager()

    def test_track_message_tokens_single(self):
        """Test tracking tokens for single message."""
        manager = get_token_manager()
        messages = [HumanMessage(content="Hello world")]

        tokens = track_message_tokens(manager, messages, "diagnose")

        assert tokens > 0
        assert manager.tokens_used == tokens

    def test_track_message_tokens_multiple(self):
        """Test tracking tokens for multiple messages."""
        manager = get_token_manager()
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="What is the weather?"),
            AIMessage(content="I can help with that."),
        ]

        tokens = track_message_tokens(manager, messages, "verify")

        assert tokens > 0
        assert manager.tokens_used == tokens


class TestTrackToolTokens:
    """Test track_tool_tokens function."""

    def setup_method(self):
        """Reset token manager before each test."""
        reset_token_manager()

    def teardown_method(self):
        """Reset token manager after each test."""
        reset_token_manager()

    def test_track_tool_tokens_known_tool(self):
        """Test tracking tokens for known tool."""
        manager = get_token_manager()

        tokens = track_tool_tokens(manager, "bq_query_tool", {})

        assert tokens == 5000  # Base estimate for bq_query_tool
        assert manager.tokens_used == 5000

    def test_track_tool_tokens_with_limit(self):
        """Test tracking tokens for tool with limit parameter."""
        manager = get_token_manager()

        tokens = track_tool_tokens(manager, "search_logs_tool", {"limit": 40})

        assert tokens == 6000  # 3000 base * (40/20)
        assert manager.tokens_used == 6000

    def test_track_tool_tokens_unknown_tool(self):
        """Test tracking tokens for unknown tool."""
        manager = get_token_manager()

        tokens = track_tool_tokens(manager, "unknown_tool", {})

        assert tokens == 1000  # Default estimate
        assert manager.tokens_used == 1000


class TestTokenTracking:
    """Integration tests for token tracking across nodes."""

    def setup_method(self):
        """Reset token manager before each test."""
        reset_token_manager()

    def teardown_method(self):
        """Reset token manager after each test."""
        reset_token_manager()

    def test_token_tracking_flow(self):
        """Test token tracking across a simulated flow."""
        manager = get_token_manager(max_tokens=10_000)

        # Simulate diagnose phase
        messages = [HumanMessage(content="Show me recent errors")]
        tokens1 = track_message_tokens(manager, messages, "diagnose")

        # Simulate tool call
        tokens2 = track_tool_tokens(manager, "search_logs_tool", {"limit": 10})

        # Simulate response
        response = [AIMessage(content="Here are the errors I found...")]
        tokens3 = track_message_tokens(manager, response, "diagnose")

        total = tokens1 + tokens2 + tokens3
        assert manager.tokens_used == total

        # Get final budget
        state = AgentState()
        budget = update_token_budget(state, manager, "finalize")

        assert budget["total_tokens"] == total
        assert budget["budget_remaining"] == 10_000 - total
