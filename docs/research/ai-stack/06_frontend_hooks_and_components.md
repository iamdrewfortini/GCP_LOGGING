# Frontend Hooks & Components

**Date:** 2025-12-15  
**Status:** Proposed  
**Version:** 1.0

---

## Enhanced Chat Hook

### useChatStream (with Token Tracking)

```typescript
// frontend/src/hooks/use-chat-stream.ts
import { useState, useCallback, useRef } from "react"
import { streamChat } from "@/lib/api"
import type { ChatStreamEvent } from "@/types/api"

export interface TokenBudget {
  used: number
  remaining: number
  percentUsed: number
  maxTokens: number
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string
  timestamp: Date
  metadata?: {
    tokens?: { input: number; output: number }
    toolCalls?: ToolCall[]
    citations?: Citation[]
    confidence?: number
  }
}

export function useChatStream(sessionId?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [tokenBudget, setTokenBudget] = useState<TokenBudget | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (content: string) => {
    setError(null)
    setIsStreaming(true)

    // Add user message
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMessage])

    // Create assistant message placeholder
    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
      metadata: { toolCalls: [], citations: [] },
    }
    setMessages((prev) => [...prev, assistantMessage])

    try {
      for await (const event of streamChat({ message: content, session_id: sessionId })) {
        handleStreamEvent(event, assistantMessage.id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stream error")
      setMessages((prev) => prev.filter((m) => m.id !== assistantMessage.id))
    } finally {
      setIsStreaming(false)
    }
  }, [sessionId])

  const handleStreamEvent = useCallback((event: ChatStreamEvent, messageId: string) => {
    switch (event.type) {
      case "on_chat_model_stream":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId ? { ...m, content: m.content + event.data.content } : m
          )
        )
        break

      case "token_count":
        setTokenBudget({
          used: event.data.total_tokens,
          remaining: event.data.budget_remaining,
          percentUsed: (event.data.total_tokens / (event.data.total_tokens + event.data.budget_remaining)) * 100,
          maxTokens: event.data.total_tokens + event.data.budget_remaining,
        })
        break

      case "on_tool_start":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? {
                  ...m,
                  metadata: {
                    ...m.metadata,
                    toolCalls: [
                      ...(m.metadata?.toolCalls || []),
                      {
                        id: crypto.randomUUID(),
                        tool: event.data.tool,
                        input: event.data.input,
                        status: "running",
                      },
                    ],
                  },
                }
              : m
          )
        )
        break

      case "on_tool_end":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? {
                  ...m,
                  metadata: {
                    ...m.metadata,
                    toolCalls: m.metadata?.toolCalls?.map((tc) =>
                      tc.tool === event.data.tool
                        ? { ...tc, output: event.data.output, status: "completed" }
                        : tc
                    ),
                  },
                }
              : m
          )
        )
        break

      case "citation":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? {
                  ...m,
                  metadata: {
                    ...m.metadata,
                    citations: [...(m.metadata?.citations || []), event.data],
                  },
                }
              : m
          )
        )
        break

      case "error":
        setError(event.data.message)
        break
    }
  }, [])

  const stopGeneration = useCallback(() => {
    abortControllerRef.current?.abort()
    setIsStreaming(false)
  }, [])

  return {
    messages,
    isStreaming,
    tokenBudget,
    error,
    sendMessage,
    stopGeneration,
  }
}
```

---

## Artifact Viewer Hook

### useArtifacts

```typescript
// frontend/src/hooks/use-artifacts.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchArtifacts, downloadArtifact, deleteArtifact } from "@/lib/api"

export function useArtifacts(sessionId?: string) {
  const queryClient = useQueryClient()

  const { data: artifacts, isLoading } = useQuery({
    queryKey: ["artifacts", sessionId],
    queryFn: () => fetchArtifacts({ sessionId }),
    enabled: !!sessionId,
  })

  const downloadMutation = useMutation({
    mutationFn: (artifactId: string) => downloadArtifact(artifactId),
    onSuccess: (blob, artifactId) => {
      // Trigger browser download
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `artifact-${artifactId}.json`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (artifactId: string) => deleteArtifact(artifactId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["artifacts", sessionId] })
    },
  })

  return {
    artifacts: artifacts?.data || [],
    isLoading,
    download: downloadMutation.mutate,
    delete: deleteMutation.mutate,
  }
}
```

---

## Token Budget Display Component

```typescript
// frontend/src/components/chat/TokenBudgetIndicator.tsx
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import type { TokenBudget } from "@/hooks/use-chat-stream"

interface TokenBudgetIndicatorProps {
  budget: TokenBudget | null
}

export function TokenBudgetIndicator({ budget }: TokenBudgetIndicatorProps) {
  if (!budget) return null

  const getStatusColor = (percent: number) => {
    if (percent < 50) return "bg-green-500"
    if (percent < 80) return "bg-yellow-500"
    return "bg-red-500"
  }

  return (
    <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
      <div className="flex-1">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-muted-foreground">Token Usage</span>
          <span className="font-medium">
            {budget.used.toLocaleString()} / {budget.maxTokens.toLocaleString()}
          </span>
        </div>
        <Progress value={budget.percentUsed} className="h-2" />
      </div>
      <Badge variant={budget.percentUsed > 80 ? "destructive" : "secondary"}>
        {budget.percentUsed.toFixed(1)}%
      </Badge>
    </div>
  )
}
```

---

## Tool Call Timeline Component

```typescript
// frontend/src/components/chat/ToolCallTimeline.tsx
import { CheckCircle, Clock, XCircle } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

interface ToolCall {
  id: string
  tool: string
  input?: any
  output?: any
  status: "running" | "completed" | "error"
  durationMs?: number
}

interface ToolCallTimelineProps {
  toolCalls: ToolCall[]
}

export function ToolCallTimeline({ toolCalls }: ToolCallTimelineProps) {
  if (toolCalls.length === 0) return null

  return (
    <div className="space-y-2 my-4">
      {toolCalls.map((call) => (
        <Collapsible key={call.id}>
          <Card className="p-3">
            <CollapsibleTrigger className="flex items-center gap-2 w-full text-left">
              {call.status === "running" && <Clock className="h-4 w-4 animate-spin text-blue-500" />}
              {call.status === "completed" && <CheckCircle className="h-4 w-4 text-green-500" />}
              {call.status === "error" && <XCircle className="h-4 w-4 text-red-500" />}
              <span className="font-medium">{call.tool}</span>
              {call.durationMs && (
                <span className="text-sm text-muted-foreground ml-auto">
                  {call.durationMs}ms
                </span>
              )}
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 space-y-2">
              {call.input && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Input:</div>
                  <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
                    {JSON.stringify(call.input, null, 2)}
                  </pre>
                </div>
              )}
              {call.output && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Output:</div>
                  <pre className="text-xs bg-muted p-2 rounded overflow-x-auto max-h-40">
                    {JSON.stringify(call.output, null, 2)}
                  </pre>
                </div>
              )}
            </CollapsibleContent>
          </Card>
        </Collapsible>
      ))}
    </div>
  )
}
```

---

## Citations Panel Component

```typescript
// frontend/src/components/chat/CitationsPanel.tsx
import { ExternalLink } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface Citation {
  source: string
  excerpt: string
  relevanceScore: number
}

interface CitationsPanelProps {
  citations: Citation[]
}

export function CitationsPanel({ citations }: CitationsPanelProps) {
  if (citations.length === 0) return null

  return (
    <div className="mt-4 space-y-2">
      <div className="text-sm font-medium text-muted-foreground">Sources:</div>
      {citations.map((citation, idx) => (
        <Card key={idx} className="p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <ExternalLink className="h-3 w-3" />
                <span className="text-sm font-medium">{citation.source}</span>
              </div>
              <p className="text-xs text-muted-foreground line-clamp-2">
                {citation.excerpt}
              </p>
            </div>
            <Badge variant="outline" className="text-xs">
              {(citation.relevanceScore * 100).toFixed(0)}%
            </Badge>
          </div>
        </Card>
      ))}
    </div>
  )
}
```

---

## Artifact List Component

```typescript
// frontend/src/components/artifacts/ArtifactList.tsx
import { Download, Trash2, FileText, Code, BarChart } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { useArtifacts } from "@/hooks/use-artifacts"

const ARTIFACT_ICONS = {
  trace: FileText,
  snapshot: Code,
  report: BarChart,
  dashboard_spec: BarChart,
}

interface ArtifactListProps {
  sessionId: string
}

export function ArtifactList({ sessionId }: ArtifactListProps) {
  const { artifacts, isLoading, download, delete: deleteArtifact } = useArtifacts(sessionId)

  if (isLoading) return <div>Loading artifacts...</div>
  if (artifacts.length === 0) return <div>No artifacts yet</div>

  return (
    <div className="space-y-2">
      {artifacts.map((artifact) => {
        const Icon = ARTIFACT_ICONS[artifact.artifactType] || FileText
        return (
          <Card key={artifact.artifactId} className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Icon className="h-5 w-5 text-muted-foreground" />
                <div>
                  <div className="font-medium">{artifact.title}</div>
                  <div className="text-sm text-muted-foreground">
                    {new Date(artifact.createdAt).toLocaleString()}
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => download(artifact.artifactId)}
                >
                  <Download className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => deleteArtifact(artifact.artifactId)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </Card>
        )
      })}
    </div>
  )
}
```

---

## Testing Strategy

### Unit Tests

```typescript
// frontend/tests/unit/use-chat-stream.test.ts
import { renderHook, act } from "@testing-library/react"
import { useChatStream } from "@/hooks/use-chat-stream"

describe("useChatStream", () => {
  it("should add user message and create assistant placeholder", async () => {
    const { result } = renderHook(() => useChatStream())

    await act(async () => {
      await result.current.sendMessage("Hello")
    })

    expect(result.current.messages).toHaveLength(2)
    expect(result.current.messages[0].role).toBe("user")
    expect(result.current.messages[1].role).toBe("assistant")
  })

  it("should update token budget on token_count event", async () => {
    const { result } = renderHook(() => useChatStream())

    act(() => {
      result.current.handleStreamEvent({
        type: "token_count",
        data: { total_tokens: 100, budget_remaining: 900 },
      }, "msg-id")
    })

    expect(result.current.tokenBudget?.used).toBe(100)
    expect(result.current.tokenBudget?.remaining).toBe(900)
  })
})
```

### E2E Tests

```typescript
// frontend/tests/e2e/chat-streaming.spec.ts
import { test, expect } from "@playwright/test"

test("should stream chat response with token tracking", async ({ page }) => {
  await page.goto("/chat")

  // Send message
  await page.fill('[data-testid="chat-input"]', "Show me errors")
  await page.click('[data-testid="send-button"]')

  // Wait for streaming to start
  await expect(page.locator('[data-testid="assistant-message"]')).toBeVisible()

  // Check token budget appears
  await expect(page.locator('[data-testid="token-budget"]')).toBeVisible()

  // Wait for streaming to complete
  await expect(page.locator('[data-testid="streaming-indicator"]')).not.toBeVisible()

  // Verify message content
  const message = await page.locator('[data-testid="assistant-message"]').textContent()
  expect(message).toBeTruthy()
})
```

---

**Next:** See `07_mcp_tool_generator_template.md` for MCP tool generation framework.

**End of Frontend Hooks & Components**
