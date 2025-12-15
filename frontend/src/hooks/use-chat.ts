import { useState, useCallback, useRef } from "react"
import { streamChat } from "@/lib/api"
import type { ChatRequest, ChatStreamEvent, Message } from "@/types/api"

export interface ToolCall {
  id: string
  tool: string
  input?: Record<string, unknown>
  output?: unknown
  status: "running" | "completed" | "error"
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string
  timestamp: Date
  toolCalls?: ToolCall[]
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const toolCallsRef = useRef<Map<string, ToolCall>>(new Map())

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

            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      toolCalls: m.toolCalls?.map((tc) =>
                        tc.tool === toolName
                          ? { ...tc, output: output?.content, status: "completed" }
                          : tc
                      ),
                    }
                  : m
              )
            )
          }
          break
        }

        case "error": {
          setError(event.data.message as string)
          break
        }

        default:
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
      }
      setMessages((prev) => [...prev, assistantMessage])

      setIsStreaming(true)
      toolCallsRef.current = new Map()

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
      }))
    )
  }, [])

  return {
    messages,
    isStreaming,
    sessionId,
    error,
    sendMessage,
    stopGeneration,
    clearMessages,
    loadSession,
  }
}
