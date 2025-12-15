/**
 * Unit tests for TokenBudgetIndicator component
 * Phase 3, Task 3.6: TokenBudgetIndicator tests
 */

import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { TokenBudgetIndicator } from "../TokenBudgetIndicator"
import type { TokenBudget } from "@/hooks/use-chat-stream"

describe("TokenBudgetIndicator", () => {
  const mockTokenBudget: TokenBudget = {
    promptTokens: 1000,
    completionTokens: 500,
    totalTokens: 1500,
    budgetMax: 10000,
    budgetRemaining: 8500,
    lastUpdateTs: "2024-01-15T10:00:00Z",
    model: "gpt-4",
    shouldSummarize: false,
  }

  it("renders nothing when tokenBudget is null", () => {
    const { container } = render(<TokenBudgetIndicator tokenBudget={null} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders token usage information", () => {
    render(<TokenBudgetIndicator tokenBudget={mockTokenBudget} />)
    
    expect(screen.getByText("Token Usage")).toBeInTheDocument()
    expect(screen.getByText(/1,500 \/ 10,000 tokens/)).toBeInTheDocument()
  })

  it("displays healthy status for low usage", () => {
    render(<TokenBudgetIndicator tokenBudget={mockTokenBudget} />)
    
    expect(screen.getByText("Token budget healthy")).toBeInTheDocument()
  })

  it("displays warning status for high usage", () => {
    const highUsageBudget: TokenBudget = {
      ...mockTokenBudget,
      totalTokens: 7500,
      budgetRemaining: 2500,
    }
    
    render(<TokenBudgetIndicator tokenBudget={highUsageBudget} />)
    
    expect(screen.getByText("Token budget high")).toBeInTheDocument()
  })

  it("displays critical status for very high usage", () => {
    const criticalBudget: TokenBudget = {
      ...mockTokenBudget,
      totalTokens: 9500,
      budgetRemaining: 500,
    }
    
    render(<TokenBudgetIndicator tokenBudget={criticalBudget} />)
    
    expect(screen.getByText("Token budget critical")).toBeInTheDocument()
  })

  it("shows token breakdown", () => {
    render(<TokenBudgetIndicator tokenBudget={mockTokenBudget} />)
    
    expect(screen.getByText("Input")).toBeInTheDocument()
    expect(screen.getByText("1,000")).toBeInTheDocument()
    expect(screen.getByText("Output")).toBeInTheDocument()
    expect(screen.getByText("500")).toBeInTheDocument()
    expect(screen.getByText("Remaining")).toBeInTheDocument()
    expect(screen.getByText("8,500")).toBeInTheDocument()
  })

  it("displays model information", () => {
    render(<TokenBudgetIndicator tokenBudget={mockTokenBudget} />)
    
    expect(screen.getByText(/Model: gpt-4/)).toBeInTheDocument()
  })

  it("shows summarization warning when needed", () => {
    const summarizeBudget: TokenBudget = {
      ...mockTokenBudget,
      shouldSummarize: true,
    }
    
    render(<TokenBudgetIndicator tokenBudget={summarizeBudget} />)
    
    expect(screen.getByText(/Summarization recommended/)).toBeInTheDocument()
  })

  it("calculates percentage correctly", () => {
    render(<TokenBudgetIndicator tokenBudget={mockTokenBudget} />)
    
    // 1500 / 10000 = 15%
    expect(screen.getByText(/15\.0% used/)).toBeInTheDocument()
  })
})
