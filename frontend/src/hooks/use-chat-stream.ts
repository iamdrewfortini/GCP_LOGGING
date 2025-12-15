/**
 * Enhanced chat hook with token tracking, checkpoints, and citations
 * Phase 3, Task 3.5: Update frontend useChatStream hook
 */

import { useState, useCallback, useRef } from "react"
import { streamChat } from "@/lib/api"
import type { ChatRequest, ChatStreamEvent, Message } from "@/types/api"

// ============================================
// TYPES
// ============================================

export interface TokenBudget {
  promptTokens: number
  completionTokens: number
  totalTokens: number
  budgetMax: number
  budgetRemaining: number
  lastUpdateTs: string
  model: string
  shouldSummarize: boolean
}

export interface ToolCall {
  id: string
  tool: string
  input?: Record<string, unknown>
  output?: string | Record<string, unknown>
  status: "running" | "completed" | "error"
  startedAt?: string
  completedAt?: string
  durationMs?: number
  tokenCount?: number
  costUsd?: number
}

export interface Citation {
  source: string
  content: string
  relevanceScore: number
  metadata?: Record<string, unknown>
}

export interface Checkpoint {
  checkpointId: string
  runId: string
  phase: string
  timestamp: string
  tokenUsage: {
    totalTokens: number
    budgetRemaining: number
  }
  messageCount: number
  toolCallCount: number
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string
  timestamp: Date
  toolCalls?: ToolCall[]
  citations?: Citation[]
  checkpoint?: Checkpoint
}

// ============================================
// HOOK
// ============================================

export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tokenBudget, setTokenBudget] = useState<TokenBudget | null>(null)
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([])
  
  const abortControllerRef = useRef<AbortController | null>(null)
  const toolCallsRef = useRef<Map<string, ToolCall>>(new Map())
  const citationsRef = useRef<Citation[]>([])

  const handleStreamEvent = useCallback(
    (event: ChatStreamEvent, assistantMessageId: string) => {
      switch (event.type) {
        case "session": {
          if (event.data.session_id) {
            setSessionId(event.data.session_id as string)
          }
          break
        }

        case "on_chat_model_stream": {
          if (event.data.content) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? { ...m, content: m.content + event.data.content }
                  : m
              )
            )
          }
          break
        }

        case "on_tool_start": {
          const toolId = crypto.randomUUID()
          const toolCall: ToolCall = {
            id: toolId,
            tool: event.data.tool as string,
            input: event.data.input as Record<string, unknown>,
            status: "running",
            startedAt: new Date().toISOString(),
          }
          toolCallsRef.current.set(event.data.tool as string, toolCall)

          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? {
                    ...m,
                    toolCalls: [...(m.toolCalls || []), toolCall],
                  }
                : m
            )
          )
          break
        }

        case "on_tool_end": {
          const output = event.data.output as { content?: string; name?: string }
          const toolName = output?.name

          if (toolName && toolCallsRef.current.has(toolName)) {
            const existingTool = toolCallsRef.current.get(toolName)!
            existingTool.output = output?.content
            existingTool.status = "completed"
            existingTool.completedAt = new Date().toISOString()
            
            // Calculate duration if we have both timestamps
            if (existingTool.startedAt && existingTool.completedAt) {
              const start = new Date(existingTool.startedAt).getTime()
              const end = new Date(existingTool.completedAt).getTime()
              existingTool.durationMs = end - start
            }

            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      toolCalls: m.toolCalls?.map((tc) =>
                        tc.tool === toolName
                          ? { ...tc, ...existingTool }
                          : tc
                      ),
                    }
                  : m
              )
            )
          }
          break
        }

        // NEW: Token count event
        case "token_count": {
          const tokenData = event.data as {
            input_tokens?: number
            output_tokens?: number
            total_tokens?: number
            budget_remaining?: number
            budget_max?: number
            model?: string
            should_summarize?: boolean
          }

          setTokenBudget({
            promptTokens: tokenData.input_tokens || 0,
            completionTokens: tokenData.output_tokens || 0,
            totalTokens: tokenData.total_tokens || 0,
            budgetMax: tokenData.budget_max || 100000,
            budgetRemaining: tokenData.budget_remaining || 0,
            lastUpdateTs: new Date().toISOString(),
            model: tokenData.model || "unknown",
            shouldSummarize: tokenData.should_summarize || false,
          })
          break
        }

        // NEW: Checkpoint event
        case "checkpoint": {
          const checkpointData = event.data as {
            checkpoint_id?: string
            run_id?: string
            phase?: string
            timestamp?: string
            token_usage?: {
              total_tokens?: number
              budget_remaining?: number
            }
            message_count?: number
            tool_call_count?: number
          }

          const checkpoint: Checkpoint = {
            checkpointId: checkpointData.checkpoint_id || "",
            runId: checkpointData.run_id || "",
            phase: checkpointData.phase || "",
            timestamp: checkpointData.timestamp || new Date().toISOString(),
            tokenUsage: {
              totalTokens: checkpointData.token_usage?.total_tokens || 0,
              budgetRemaining: checkpointData.token_usage?.budget_remaining || 0,
            },
            messageCount: checkpointData.message_count || 0,
            toolCallCount: checkpointData.tool_call_count || 0,
          }

          setCheckpoints((prev) => [...prev, checkpoint])

          // Add checkpoint to current message
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? { ...m, checkpoint }
                : m
            )
          )
          break
        }

        // NEW: Citation event
        case "citation": {
          const citationData = event.data as {
            source?: string
            content?: string
            relevance_score?: number
            metadata?: Record<string, unknown>
          }

          const citation: Citation = {
            source: citationData.source || "",
            content: citationData.content || "",
            relevanceScore: citationData.relevance_score || 0,
            metadata: citationData.metadata,
          }

          citationsRef.current.push(citation)

          // Add citation to current message
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? {
                    ...m,
                    citations: [...(m.citations || []), citation],
                  }
                : m
            )
          )
          break
        }

        case "error": {
          setError(event.data.message as string)
          break
        }

        default:
          // Log unknown event types for debugging
          console.debug("Unknown event type:", event.type, event.data)
          break
      }
    },
    []
  )

  const sendMessage = useCallback(
    async (content: string, context: Record<string, unknown> = {}) => {
      setError(null)

      // Add user message
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, userMessage])

      // Create placeholder for assistant message
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        timestamp: new Date(),
        toolCalls: [],
        citations: [],
      }
      setMessages((prev) => [...prev, assistantMessage])

      setIsStreaming(true)
      toolCallsRef.current = new Map()
      citationsRef.current = []

      try {
        const request: ChatRequest = {
          message: content,
          session_id: sessionId || undefined,
          context,
        }

        for await (const event of streamChat(request)) {
          handleStreamEvent(event, assistantMessage.id)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to send message")
        // Remove empty assistant message on error
        setMessages((prev) => prev.filter((m) => m.id !== assistantMessage.id))
      } finally {
        setIsStreaming(false)
      }
    },
    [sessionId, handleStreamEvent]
  )

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setIsStreaming(false)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setSessionId(null)
    setError(null)
    setTokenBudget(null)
    setCheckpoints([])
    toolCallsRef.current = new Map()
    citationsRef.current = []
  }, [])

  const loadSession = useCallback((messages: Message[], newSessionId: string) => {
    setSessionId(newSessionId)
    setMessages(
      messages.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant" | "system",
        content: m.content,
        timestamp: new Date(m.timestamp),
        toolCalls: m.metadata?.toolCalls as ToolCall[] | undefined,
        citations: m.metadata?.citations as Citation[] | undefined,
        checkpoint: m.metadata?.checkpoint as Checkpoint | undefined,
      }))
    )
  }, [])

  return {
    messages,
    isStreaming,
    sessionId,
    error,
    tokenBudget,
    checkpoints,
    sendMessage,
    stopGeneration,
    clearMessages,
    loadSession,
  }
}
