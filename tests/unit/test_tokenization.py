"""Unit tests for token budget management."""

import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.agent.tokenization import (
    TokenBudgetManager,
    TokenBudgetExceeded,
    estimate_tool_output_tokens
)


class TestTokenBudgetManager:
    """Test TokenBudgetManager class."""
    
    def test_initialization(self):
        """Test manager initialization with default values."""
        manager = TokenBudgetManager()
        assert manager.max_tokens == 100_000
        assert manager.tokens_used == 0
    
    def test_initialization_custom_limit(self):
        """Test manager initialization with custom token limit."""
        manager = TokenBudgetManager(max_tokens=50_000)
        assert manager.max_tokens == 50_000
        assert manager.tokens_used == 0
    
    def test_count_tokens_simple(self):
        """Test token counting for simple text."""
        manager = TokenBudgetManager()
        text = "Hello, world!"
        tokens = manager.count_tokens(text)
        
        # "Hello, world!" should be ~4 tokens
        assert tokens > 0
        assert tokens < 10
    
    def test_count_tokens_empty(self):
        """Test token counting for empty string."""
        manager = TokenBudgetManager()
        tokens = manager.count_tokens("")
        assert tokens == 0
    
    def test_count_messages_single(self):
        """Test token counting for single message."""
        manager = TokenBudgetManager()
        messages = [HumanMessage(content="Hello, how are you?")]
        tokens = manager.count_messages(messages)
        
        # Should include content tokens + 4 for message overhead
        assert tokens > 4
        assert tokens < 20
    
    def test_count_messages_multiple(self):
        """Test token counting for multiple messages."""
        manager = TokenBudgetManager()
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(content="How are you?")
        ]
        tokens = manager.count_messages(messages)
        
        # Should include all content + 4 tokens per message (3 messages = 12 overhead)
        assert tokens > 12
    
    def test_check_budget_within_limit(self):
        """Test budget check when within limit."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 500
        
        assert manager.check_budget(400) is True
    
    def test_check_budget_at_limit(self):
        """Test budget check when exactly at limit."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 500
        
        assert manager.check_budget(500) is True
    
    def test_check_budget_exceeds_limit(self):
        """Test budget check when exceeding limit."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 500
        
        assert manager.check_budget(501) is False
    
    def test_reserve_tokens_success(self):
        """Test successful token reservation."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.reserve_tokens(500)
        
        assert manager.tokens_used == 500
    
    def test_reserve_tokens_exceeds_budget(self):
        """Test token reservation that exceeds budget."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 900
        
        with pytest.raises(TokenBudgetExceeded) as exc_info:
            manager.reserve_tokens(200)
        
        assert "exceed budget" in str(exc_info.value).lower()
        assert manager.tokens_used == 900  # Should not change on failure
    
    def test_get_budget_status_empty(self):
        """Test budget status when no tokens used."""
        manager = TokenBudgetManager(max_tokens=1000)
        status = manager.get_budget_status()
        
        assert status["tokens_used"] == 0
        assert status["tokens_remaining"] == 1000
        assert status["max_tokens"] == 1000
        assert status["percent_used"] == 0.0
    
    def test_get_budget_status_partial(self):
        """Test budget status with partial usage."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 250
        status = manager.get_budget_status()
        
        assert status["tokens_used"] == 250
        assert status["tokens_remaining"] == 750
        assert status["max_tokens"] == 1000
        assert status["percent_used"] == 25.0
    
    def test_get_budget_status_full(self):
        """Test budget status when fully used."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 1000
        status = manager.get_budget_status()
        
        assert status["tokens_used"] == 1000
        assert status["tokens_remaining"] == 0
        assert status["max_tokens"] == 1000
        assert status["percent_used"] == 100.0
    
    def test_reset(self):
        """Test resetting token counter."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 500
        manager.reset()
        
        assert manager.tokens_used == 0
    
    def test_should_summarize_below_threshold(self):
        """Test summarization check below threshold."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 700
        
        assert manager.should_summarize(threshold=0.8) is False
    
    def test_should_summarize_at_threshold(self):
        """Test summarization check at threshold."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 800
        
        assert manager.should_summarize(threshold=0.8) is True
    
    def test_should_summarize_above_threshold(self):
        """Test summarization check above threshold."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 900
        
        assert manager.should_summarize(threshold=0.8) is True
    
    def test_should_summarize_custom_threshold(self):
        """Test summarization check with custom threshold."""
        manager = TokenBudgetManager(max_tokens=1000)
        manager.tokens_used = 600
        
        assert manager.should_summarize(threshold=0.5) is True
        assert manager.should_summarize(threshold=0.7) is False


class TestEstimateToolOutputTokens:
    """Test tool output token estimation."""
    
    def test_estimate_known_tool(self):
        """Test estimation for known tool."""
        tokens = estimate_tool_output_tokens("bq_query_tool", {})
        assert tokens == 5000
    
    def test_estimate_unknown_tool(self):
        """Test estimation for unknown tool (default)."""
        tokens = estimate_tool_output_tokens("unknown_tool", {})
        assert tokens == 1000
    
    def test_estimate_with_limit_parameter(self):
        """Test estimation adjusted by limit parameter."""
        # Base estimate for search_logs_tool is 3000
        # With limit=40 (2x baseline of 20), should be ~6000
        tokens = estimate_tool_output_tokens("search_logs_tool", {"limit": 40})
        assert tokens == 6000
    
    def test_estimate_with_small_limit(self):
        """Test estimation with small limit."""
        # With limit=10 (0.5x baseline), should be ~1500
        tokens = estimate_tool_output_tokens("search_logs_tool", {"limit": 10})
        assert tokens == 1500
    
    def test_estimate_without_limit(self):
        """Test estimation without limit parameter."""
        tokens = estimate_tool_output_tokens("search_logs_tool", {})
        assert tokens == 3000


class TestIntegration:
    """Integration tests for token budget management."""
    
    def test_full_conversation_flow(self):
        """Test complete conversation with budget tracking."""
        manager = TokenBudgetManager(max_tokens=10_000)
        
        # User message
        user_msg = HumanMessage(content="Show me errors from the last hour")
        user_tokens = manager.count_messages([user_msg])
        manager.reserve_tokens(user_tokens)
        
        # Estimate tool output
        tool_estimate = estimate_tool_output_tokens("search_logs_tool", {"limit": 10})
        manager.reserve_tokens(tool_estimate)
        
        # Assistant response
        assistant_msg = AIMessage(content="Here are the errors I found: ...")
        assistant_tokens = manager.count_messages([assistant_msg])
        manager.reserve_tokens(assistant_tokens)
        
        # Check status
        status = manager.get_budget_status()
        assert status["tokens_used"] > 0
        assert status["tokens_used"] < 10_000
        assert status["percent_used"] < 100
    
    def test_budget_exceeded_scenario(self):
        """Test scenario where budget is exceeded."""
        manager = TokenBudgetManager(max_tokens=100)
        
        # Use most of budget
        manager.reserve_tokens(90)
        
        # Try to reserve more than remaining
        with pytest.raises(TokenBudgetExceeded):
            manager.reserve_tokens(20)
        
        # Should trigger summarization
        assert manager.should_summarize(threshold=0.8) is True
