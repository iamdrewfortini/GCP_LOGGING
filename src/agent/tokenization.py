"""Token budget management for LangGraph agent.

This module provides token counting and budget enforcement to prevent
context window overflow in long conversations.
"""

from typing import List, Dict, Any
from langchain_core.messages import BaseMessage
import tiktoken


class TokenBudgetExceeded(Exception):
    """Raised when token budget is exceeded."""
    pass


class TokenBudgetManager:
    """Manages token budget for a conversation.
    
    Uses tiktoken to count tokens accurately for Gemini models
    (which use similar tokenization to GPT-4).
    
    Example:
        >>> manager = TokenBudgetManager(max_tokens=100_000)
        >>> tokens = manager.count_tokens("Hello, world!")
        >>> manager.reserve_tokens(tokens)
        >>> status = manager.get_budget_status()
        >>> print(f"Used: {status['tokens_used']}/{status['max_tokens']}")
    """
    
    def __init__(self, model: str = "gpt-4", max_tokens: int = 100_000):
        """Initialize token budget manager.
        
        Args:
            model: Model name for tokenizer (default: gpt-4)
            max_tokens: Maximum tokens allowed (default: 100,000)
                       Note: Gemini 2.5 Flash supports 1M tokens, but we use
                       a conservative limit to allow for tool outputs and safety margin.
        """
        self.encoding = tiktoken.encoding_for_model(model)
        self.max_tokens = max_tokens
        self.tokens_used = 0
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))
    
    def count_messages(self, messages: List[BaseMessage]) -> int:
        """Count tokens in a list of messages.
        
        Includes overhead for message formatting (4 tokens per message).
        
        Args:
            messages: List of LangChain messages
            
        Returns:
            Total number of tokens
        """
        total = 0
        for msg in messages:
            # Count content tokens
            content = str(msg.content)
            total += self.count_tokens(content)
            
            # Add message overhead (role, formatting, etc.)
            total += 4
        
        return total
    
    def check_budget(self, additional_tokens: int) -> bool:
        """Check if adding tokens would exceed budget.
        
        Args:
            additional_tokens: Number of tokens to add
            
        Returns:
            True if within budget, False otherwise
        """
        return (self.tokens_used + additional_tokens) <= self.max_tokens
    
    def reserve_tokens(self, count: int) -> None:
        """Reserve tokens from budget.
        
        Args:
            count: Number of tokens to reserve
            
        Raises:
            TokenBudgetExceeded: If reservation would exceed budget
        """
        if not self.check_budget(count):
            raise TokenBudgetExceeded(
                f"Would exceed budget: {self.tokens_used + count} > {self.max_tokens}. "
                f"Consider summarizing the conversation or starting a new session."
            )
        self.tokens_used += count
    
    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status.
        
        Returns:
            Dictionary with budget information:
            - tokens_used: Tokens consumed so far
            - tokens_remaining: Tokens still available
            - max_tokens: Maximum tokens allowed
            - percent_used: Percentage of budget used
        """
        remaining = self.max_tokens - self.tokens_used
        percent = (self.tokens_used / self.max_tokens) * 100 if self.max_tokens > 0 else 0
        
        return {
            "tokens_used": self.tokens_used,
            "tokens_remaining": remaining,
            "max_tokens": self.max_tokens,
            "percent_used": round(percent, 2)
        }
    
    def reset(self) -> None:
        """Reset token counter to zero."""
        self.tokens_used = 0
    
    def should_summarize(self, threshold: float = 0.8) -> bool:
        """Check if conversation should be summarized.
        
        Args:
            threshold: Percentage threshold (0.0-1.0) for triggering summarization
            
        Returns:
            True if tokens_used >= threshold * max_tokens
        """
        return self.tokens_used >= (threshold * self.max_tokens)


def estimate_tool_output_tokens(tool_name: str, input_data: Dict[str, Any]) -> int:
    """Estimate token count for tool output.
    
    Provides conservative estimates based on tool type and input.
    
    Args:
        tool_name: Name of the tool
        input_data: Tool input parameters
        
    Returns:
        Estimated token count for output
    """
    # Conservative estimates by tool type
    estimates = {
        "bq_query_tool": 5000,  # BigQuery results can be large
        "search_logs_tool": 3000,  # Log search results
        "analyze_logs": 4000,  # Comprehensive analysis
        "get_log_summary": 1000,  # Quick summary
        "find_related_logs": 2000,  # Related log context
        "trace_lookup_tool": 1500,  # Trace spans
        "service_health_tool": 500,  # Service metadata
        "semantic_search_logs": 2000,  # Semantic search results
    }
    
    # Get base estimate
    base_estimate = estimates.get(tool_name, 1000)
    
    # Adjust based on input parameters
    if "limit" in input_data:
        # Scale by result limit
        limit = input_data["limit"]
        base_estimate = int(base_estimate * (limit / 20))  # Assume 20 is baseline
    
    return base_estimate
