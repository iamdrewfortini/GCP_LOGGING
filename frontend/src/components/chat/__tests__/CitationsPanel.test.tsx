/**
 * Unit tests for CitationsPanel component
 * Phase 3, Task 3.8: CitationsPanel tests
 */

import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { CitationsPanel } from "../CitationsPanel"
import type { Citation } from "@/hooks/use-chat-stream"

describe("CitationsPanel", () => {
  const mockCitations: Citation[] = [
    {
      source: "log-12345",
      content: "ERROR: Connection timeout to database",
      relevanceScore: 0.95,
      metadata: {
        severity: "ERROR",
        service: "api-gateway",
        timestamp: "2024-01-15T10:00:00Z",
      },
    },
    {
      source: "log-67890",
      content: "WARNING: High memory usage detected",
      relevanceScore: 0.65,
      metadata: {
        severity: "WARNING",
        service: "worker",
      },
    },
    {
      source: "log-11111",
      content: "INFO: Request processed successfully",
      relevanceScore: 0.35,
    },
  ]

  it("renders nothing when citations is empty", () => {
    const { container } = render(<CitationsPanel citations={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders citations header with count", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    expect(screen.getByText(/Sources & Citations \(3\)/)).toBeInTheDocument()
  })

  it("displays all citations", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    expect(screen.getByText("log-12345")).toBeInTheDocument()
    expect(screen.getByText("log-67890")).toBeInTheDocument()
    expect(screen.getByText("log-11111")).toBeInTheDocument()
  })

  it("sorts citations by relevance score", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    const citations = screen.getAllByText(/\[\d+\]/)
    // First citation should be the highest relevance (0.95)
    expect(citations[0]).toHaveTextContent("[1]")
  })

  it("displays relevance badges with correct labels", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    expect(screen.getByText(/High \(95%\)/)).toBeInTheDocument()
    expect(screen.getByText(/Medium \(65%\)/)).toBeInTheDocument()
    expect(screen.getByText(/Low \(35%\)/)).toBeInTheDocument()
  })

  it("expands citation details on click", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    // Initially collapsed
    expect(screen.queryByText("Excerpt:")).not.toBeInTheDocument()
    
    // Click to expand
    const citation = screen.getByText("log-12345")
    fireEvent.click(citation)
    
    // Now visible
    expect(screen.getByText("Excerpt:")).toBeInTheDocument()
  })

  it("displays citation content when expanded", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    const citation = screen.getByText("log-12345")
    fireEvent.click(citation)
    
    expect(screen.getByText(/ERROR: Connection timeout to database/)).toBeInTheDocument()
  })

  it("displays metadata when available", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    const citation = screen.getByText("log-12345")
    fireEvent.click(citation)
    
    expect(screen.getByText("Metadata:")).toBeInTheDocument()
    expect(screen.getByText(/severity:/)).toBeInTheDocument()
    expect(screen.getByText(/ERROR/)).toBeInTheDocument()
    expect(screen.getByText(/service:/)).toBeInTheDocument()
    expect(screen.getByText(/api-gateway/)).toBeInTheDocument()
  })

  it("handles citations without metadata", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    const citation = screen.getByText("log-11111")
    fireEvent.click(citation)
    
    // Should show excerpt but not metadata section
    expect(screen.getByText("Excerpt:")).toBeInTheDocument()
    expect(screen.queryByText("Metadata:")).not.toBeInTheDocument()
  })

  it("shows view source button", () => {
    render(<CitationsPanel citations={mockCitations} />)
    
    const citation = screen.getByText("log-12345")
    fireEvent.click(citation)
    
    expect(screen.getByText("View Source")).toBeInTheDocument()
  })

  it("applies correct color coding for relevance", () => {
    const { container } = render(<CitationsPanel citations={mockCitations} />)
    
    // High relevance should have green styling
    const highBadge = screen.getByText(/High \(95%\)/)
    expect(highBadge.className).toContain("green")
    
    // Medium relevance should have blue styling
    const mediumBadge = screen.getByText(/Medium \(65%\)/)
    expect(mediumBadge.className).toContain("blue")
    
    // Low relevance should have yellow styling
    const lowBadge = screen.getByText(/Low \(35%\)/)
    expect(lowBadge.className).toContain("yellow")
  })
})
