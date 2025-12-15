/**
 * Unit tests for ToolCallTimeline component
 * Phase 3, Task 3.7: ToolCallTimeline tests
 */

import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ToolCallTimeline } from "../ToolCallTimeline"
import type { ToolCall } from "@/hooks/use-chat-stream"

describe("ToolCallTimeline", () => {
  const mockToolCalls: ToolCall[] = [
    {
      id: "tool-1",
      tool: "search_logs_tool",
      input: { query: "ERROR", hours: 24 },
      output: { count: 150, logs: ["log1", "log2"] },
      status: "completed",
      startedAt: "2024-01-15T10:00:00Z",
      completedAt: "2024-01-15T10:00:02Z",
      durationMs: 2000,
      tokenCount: 500,
      costUsd: 0.005,
    },
    {
      id: "tool-2",
      tool: "analyze_logs",
      input: { intent: "errors" },
      status: "running",
      startedAt: "2024-01-15T10:00:03Z",
    },
  ]

  it("renders nothing when toolCalls is empty", () => {
    const { container } = render(<ToolCallTimeline toolCalls={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders tool execution header", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    expect(screen.getByText("Tool Executions")).toBeInTheDocument()
  })

  it("displays all tool calls", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    expect(screen.getByText("search_logs_tool")).toBeInTheDocument()
    expect(screen.getByText("analyze_logs")).toBeInTheDocument()
  })

  it("shows correct status badges", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    expect(screen.getByText("completed")).toBeInTheDocument()
    expect(screen.getByText("running")).toBeInTheDocument()
  })

  it("displays duration for completed tools", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    expect(screen.getByText("2.00s")).toBeInTheDocument()
  })

  it("expands tool details on click", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    // Initially collapsed
    expect(screen.queryByText("Input:")).not.toBeInTheDocument()
    
    // Click to expand
    const toolItem = screen.getByText("search_logs_tool")
    fireEvent.click(toolItem)
    
    // Now visible
    expect(screen.getByText("Input:")).toBeInTheDocument()
    expect(screen.getByText("Output:")).toBeInTheDocument()
  })

  it("displays tool input when expanded", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    const toolItem = screen.getByText("search_logs_tool")
    fireEvent.click(toolItem)
    
    expect(screen.getByText(/query/)).toBeInTheDocument()
    expect(screen.getByText(/ERROR/)).toBeInTheDocument()
  })

  it("displays tool output when expanded", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    const toolItem = screen.getByText("search_logs_tool")
    fireEvent.click(toolItem)
    
    expect(screen.getByText(/count/)).toBeInTheDocument()
  })

  it("shows token count and cost", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    const toolItem = screen.getByText("search_logs_tool")
    fireEvent.click(toolItem)
    
    expect(screen.getByText(/Tokens: 500/)).toBeInTheDocument()
    expect(screen.getByText(/Cost: \$0\.0050/)).toBeInTheDocument()
  })

  it("handles tools without output", () => {
    render(<ToolCallTimeline toolCalls={mockToolCalls} />)
    
    const runningTool = screen.getByText("analyze_logs")
    fireEvent.click(runningTool)
    
    // Should show input but not output
    expect(screen.getByText("Input:")).toBeInTheDocument()
    expect(screen.queryByText("Output:")).not.toBeInTheDocument()
  })
})
