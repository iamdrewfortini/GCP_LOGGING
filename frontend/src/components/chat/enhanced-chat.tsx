import { useState, useRef, useEffect, useCallback } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Bot,
  User,
  Send,
  Loader2,
  Square,
  ChevronDown,
  ChevronRight,
  Wrench,
  Plus,
  MessageSquare,
  Trash2,
  X,
  Sparkles,
  AlertTriangle,
  CheckCircle,
  Search,
  Activity,
  TrendingUp,
  Zap,
  RefreshCw,
} from "lucide-react"
import { useChat, type ChatMessage, type ToolCall } from "@/hooks/use-chat"
import { useSessions } from "@/hooks/use-sessions"
import { cn } from "@/lib/utils"

// Quick action suggestions
const QUICK_ACTIONS = [
  {
    label: "System Health",
    query: "Give me a health summary of all logs",
    icon: Activity,
    color: "text-green-500",
  },
  {
    label: "Recent Errors",
    query: "Show me all errors from the last hour",
    icon: AlertTriangle,
    color: "text-red-500",
  },
  {
    label: "Warning Trends",
    query: "Analyze warning patterns from the last 24 hours",
    icon: TrendingUp,
    color: "text-yellow-500",
  },
  {
    label: "Service Status",
    query: "Which services have the most errors?",
    icon: Zap,
    color: "text-blue-500",
  },
]

// Smart suggestions based on context
const SMART_SUGGESTIONS = [
  "Show me errors from the last hour",
  "What's causing the most issues?",
  "Analyze logs for glass-pane service",
  "Find connection timeout errors",
  "Show me critical alerts",
  "Summarize today's log activity",
]

interface EnhancedChatProps {
  showSidebar?: boolean
}

export function EnhancedChat({ showSidebar = true }: EnhancedChatProps) {
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    messages,
    isStreaming,
    sessionId,
    error,
    sendMessage,
    stopGeneration,
    clearMessages,
  } = useChat()

  const { data: sessionsData, isLoading: sessionsLoading } = useSessions("active")

  // Scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])


  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return
    sendMessage(input.trim())
    setInput("")
  }, [input, isStreaming, sendMessage])

  const handleQuickAction = useCallback((query: string) => {
    sendMessage(query)
  }, [sendMessage])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleNewChat = () => {
    clearMessages()
    setInput("")
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Sidebar - Sessions */}
      {showSidebar && (
        <Card className="w-64 shrink-0 flex flex-col">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Sessions</CardTitle>
              <Button variant="ghost" size="icon" onClick={handleNewChat}>
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden p-2">
            <ScrollArea className="h-full">
              {sessionsLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : sessionsData?.sessions.length === 0 ? (
                <div className="text-center py-8">
                  <MessageSquare className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">No sessions yet</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {sessionsData?.sessions.map((session) => (
                    <Button
                      key={session.id}
                      variant={sessionId === session.id ? "secondary" : "ghost"}
                      className="w-full justify-start text-left h-auto py-2 px-3"
                    >
                      <div className="flex flex-col items-start gap-1 truncate">
                        <span className="text-sm truncate w-full">
                          {session.title}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(session.updatedAt).toLocaleDateString()}
                        </span>
                      </div>
                    </Button>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {/* Main Chat Area */}
      <Card className="flex-1 flex flex-col">
        {/* Header */}
        <CardHeader className="pb-2 border-b shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600">
                <Bot className="h-5 w-5 text-white" />
              </div>
              <div>
                <CardTitle className="text-lg">AI Log Debugger</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Powered by Gemini - Intelligent log analysis
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {messages.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearMessages}
                  className="text-muted-foreground"
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  Clear
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNewChat}
                className="text-muted-foreground"
              >
                <RefreshCw className="h-4 w-4 mr-1" />
                New
              </Button>
            </div>
          </div>
        </CardHeader>

        {/* Messages */}
        <ScrollArea ref={scrollRef} className="flex-1 p-4">
          {messages.length === 0 ? (
            <WelcomeScreen
              onQuickAction={handleQuickAction}
              onSuggestionClick={(s) => setInput(s)}
            />
          ) : (
            <div className="space-y-6 max-w-4xl mx-auto">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              {isStreaming &&
                messages.length > 0 &&
                messages[messages.length - 1]?.role === "assistant" &&
                messages[messages.length - 1]?.content === "" && (
                  <div className="flex items-center gap-2 text-muted-foreground text-sm ml-11">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Analyzing logs...
                  </div>
                )}
              {error && (
                <div className="flex items-center gap-2 text-destructive text-sm bg-destructive/10 p-3 rounded-md">
                  <X className="h-4 w-4" />
                  {error}
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        {/* Quick suggestions when typing */}
        {!isStreaming && input.length === 0 && messages.length > 0 && (
          <div className="px-4 pb-2">
            <div className="flex flex-wrap gap-2">
              {SMART_SUGGESTIONS.slice(0, 4).map((suggestion) => (
                <Button
                  key={suggestion}
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => handleQuickAction(suggestion)}
                >
                  {suggestion}
                </Button>
              ))}
            </div>
          </div>
        )}

        {/* Input */}
        <CardContent className="border-t p-4 shrink-0">
          <form onSubmit={handleSubmit} className="flex gap-2 max-w-4xl mx-auto">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your logs, errors, traces..."
                disabled={isStreaming}
                className="pl-9"
              />
            </div>
            {isStreaming ? (
              <Button
                type="button"
                variant="destructive"
                size="icon"
                onClick={stopGeneration}
              >
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button type="submit" size="icon" disabled={!input.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            )}
          </form>
          <p className="text-xs text-muted-foreground mt-2 text-center">
            <Sparkles className="inline h-3 w-3 mr-1" />
            Try: "Show me errors from the last hour" or "Health summary"
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

// Welcome screen with quick actions
function WelcomeScreen({
  onQuickAction,
  onSuggestionClick,
}: {
  onQuickAction: (query: string) => void
  onSuggestionClick: (suggestion: string) => void
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center max-w-2xl mx-auto">
      <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-purple-600/20 mb-6">
        <Bot className="h-10 w-10 text-violet-500" />
      </div>
      <h3 className="text-xl font-semibold">How can I help you today?</h3>
      <p className="text-muted-foreground mt-2 mb-6">
        I can analyze logs, find errors, trace requests, and help troubleshoot your GCP infrastructure.
      </p>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 gap-3 w-full max-w-md mb-6">
        {QUICK_ACTIONS.map((action) => {
          const Icon = action.icon
          return (
            <Button
              key={action.label}
              variant="outline"
              className="h-auto py-4 px-4 flex flex-col items-center gap-2 hover:bg-muted/50"
              onClick={() => onQuickAction(action.query)}
            >
              <Icon className={cn("h-5 w-5", action.color)} />
              <span className="font-medium">{action.label}</span>
            </Button>
          )
        })}
      </div>

      {/* Suggestion chips */}
      <div className="flex flex-wrap gap-2 justify-center">
        {SMART_SUGGESTIONS.map((suggestion) => (
          <Button
            key={suggestion}
            variant="ghost"
            size="sm"
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => onSuggestionClick(suggestion)}
          >
            {suggestion}
          </Button>
        ))}
      </div>
    </div>
  )
}

// Enhanced message bubble with markdown rendering
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-gradient-to-br from-violet-500 to-purple-600 text-white"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={cn(
          "flex flex-col gap-2 max-w-[85%]",
          isUser ? "items-end" : "items-start"
        )}
      >
        <div
          className={cn(
            "rounded-lg px-4 py-3 text-sm",
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-foreground"
          )}
        >
          {isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            <MarkdownContent content={message.content} />
          )}
        </div>

        {/* Tool Calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="w-full space-y-2">
            {message.toolCalls.map((toolCall) => (
              <ToolCallDisplay key={toolCall.id} toolCall={toolCall} />
            ))}
          </div>
        )}

        <span className="text-xs text-muted-foreground">
          {message.timestamp.toLocaleTimeString()}
        </span>
      </div>
    </div>
  )
}

// Markdown renderer component
function MarkdownContent({ content }: { content: string }) {
  if (!content) {
    return <span className="text-muted-foreground italic">Generating...</span>
  }

  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Style tables
          table: ({ children }) => (
            <div className="overflow-x-auto my-2">
              <table className="min-w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-border bg-muted px-2 py-1 text-left font-medium">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-border px-2 py-1">{children}</td>
          ),
          // Style code blocks
          code: ({ className, children, ...props }) => {
            const isInline = !className
            if (isInline) {
              return (
                <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono" {...props}>
                  {children}
                </code>
              )
            }
            return (
              <pre className="bg-muted p-3 rounded-md overflow-x-auto text-xs my-2">
                <code className="font-mono" {...props}>{children}</code>
              </pre>
            )
          },
          // Style lists
          ul: ({ children }) => (
            <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>
          ),
          // Style headers
          h1: ({ children }) => (
            <h1 className="text-lg font-bold mt-4 mb-2">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-bold mt-3 mb-2">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-bold mt-2 mb-1">{children}</h3>
          ),
          // Style blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-primary pl-3 italic my-2">
              {children}
            </blockquote>
          ),
          // Style horizontal rules
          hr: () => <hr className="my-4 border-border" />,
          // Style paragraphs
          p: ({ children }) => <p className="my-2">{children}</p>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

// Enhanced tool call display
function ToolCallDisplay({ toolCall }: { toolCall: ToolCall }) {
  const [isOpen, setIsOpen] = useState(false)

  // Determine tool icon and color based on tool name
  const getToolStyle = (toolName: string) => {
    if (toolName.includes("error") || toolName.includes("Error")) {
      return { icon: AlertTriangle, color: "text-red-500" }
    }
    if (toolName.includes("summary") || toolName.includes("health")) {
      return { icon: CheckCircle, color: "text-green-500" }
    }
    if (toolName.includes("analyze")) {
      return { icon: Activity, color: "text-blue-500" }
    }
    return { icon: Wrench, color: "text-muted-foreground" }
  }

  const { icon: ToolIcon, color } = getToolStyle(toolCall.tool)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-between h-auto py-2 px-3 bg-muted/50 hover:bg-muted"
        >
          <div className="flex items-center gap-2">
            <ToolIcon className={cn("h-3 w-3", color)} />
            <span className="text-xs font-mono">{toolCall.tool}</span>
            {toolCall.status === "running" ? (
              <Loader2 className="h-3 w-3 animate-spin text-violet-500" />
            ) : (
              <Badge variant="secondary" className="text-xs">
                <CheckCircle className="h-2 w-2 mr-1" />
                done
              </Badge>
            )}
          </div>
          {isOpen ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1">
        <div className="bg-muted/30 rounded-md p-3 text-xs font-mono space-y-2">
          {toolCall.input && (
            <div>
              <span className="text-muted-foreground font-sans text-xs">Input:</span>
              <pre className="mt-1 overflow-auto max-h-32 bg-background/50 p-2 rounded">
                {JSON.stringify(toolCall.input, null, 2)}
              </pre>
            </div>
          )}
          {toolCall.output !== undefined && (
            <div>
              <span className="text-muted-foreground font-sans text-xs">Output:</span>
              <pre className="mt-1 overflow-auto max-h-48 bg-background/50 p-2 rounded text-[10px]">
                {formatToolOutput(toolCall.output)}
              </pre>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// Format tool output for display
function formatToolOutput(output: unknown): string {
  if (output === null || output === undefined) {
    return "null"
  }
  if (typeof output === "string") {
    const truncated = output.slice(0, 2000)
    return output.length > 2000 ? truncated + "\n... (truncated)" : truncated
  }
  try {
    const str = JSON.stringify(output, null, 2)
    const truncated = str.slice(0, 2000)
    return str.length > 2000 ? truncated + "\n... (truncated)" : truncated
  } catch {
    return String(output)
  }
}

export default EnhancedChat
