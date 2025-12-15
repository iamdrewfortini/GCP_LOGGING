import { useState, useRef, useEffect } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Bot,
  User,
  Send,
  Loader2,
  Square,
  ChevronDown,
  ChevronRight,
  Wrench,
  Sparkles,
  Trash2,
  X,
} from "lucide-react"
import { useChat, type ChatMessage, type ToolCall } from "@/hooks/use-chat"
import { cn } from "@/lib/utils"

// Quick suggestions for the modal
const QUICK_SUGGESTIONS = [
  "Show me recent errors",
  "Health summary",
  "What's causing high latency?",
  "Find connection timeouts",
]

interface AIChatModalProps {
  trigger?: React.ReactNode
  context?: Record<string, unknown>
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
}

export function AIChatModal({
  trigger,
  context = {},
  defaultOpen = false,
  onOpenChange,
}: AIChatModalProps) {
  const [open, setOpen] = useState(defaultOpen)
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    messages,
    isStreaming,
    error,
    sendMessage,
    stopGeneration,
    clearMessages,
  } = useChat()

  // Scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  // Focus input when dialog opens
  useEffect(() => {
    if (open && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open])

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen)
    onOpenChange?.(newOpen)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return

    sendMessage(input.trim(), context)
    setInput("")
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="icon" className="relative">
            <Sparkles className="h-4 w-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-3xl h-[80vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 py-4 border-b shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <div>
                <DialogTitle>AI Log Debugger</DialogTitle>
                <DialogDescription>
                  Ask questions about your logs and infrastructure
                </DialogDescription>
              </div>
            </div>
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
          </div>
        </DialogHeader>

        {/* Messages Area */}
        <ScrollArea ref={scrollRef} className="flex-1 px-6 py-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Bot className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <h3 className="text-lg font-medium">How can I help you?</h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                I can help you analyze logs, troubleshoot issues, and understand
                your GCP infrastructure.
              </p>
              <div className="flex flex-wrap gap-2 mt-4 justify-center">
                {QUICK_SUGGESTIONS.map((suggestion) => (
                  <Button
                    key={suggestion}
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      sendMessage(suggestion)
                    }}
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              {isStreaming && (
                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Thinking...
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

        {/* Input Area */}
        <div className="px-6 py-4 border-t shrink-0">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your logs..."
              disabled={isStreaming}
              className="flex-1"
            />
            {isStreaming ? (
              <Button type="button" variant="destructive" onClick={stopGeneration}>
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button type="submit" disabled={!input.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            )}
          </form>
          <p className="text-xs text-muted-foreground mt-2 text-center">
            AI responses are generated and may not always be accurate.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// Message Bubble Component
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div
      className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={cn(
          "flex flex-col gap-2 max-w-[80%]",
          isUser ? "items-end" : "items-start"
        )}
      >
        <div
          className={cn(
            "rounded-lg px-4 py-2 text-sm",
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

// Tool Call Display Component
function ToolCallDisplay({ toolCall }: { toolCall: ToolCall }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-between h-auto py-2 px-3 bg-muted/50 hover:bg-muted"
        >
          <div className="flex items-center gap-2">
            <Wrench className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs font-mono">{toolCall.tool}</span>
            {toolCall.status === "running" ? (
              <Loader2 className="h-3 w-3 animate-spin text-primary" />
            ) : (
              <Badge variant="secondary" className="text-xs">
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
              <span className="text-muted-foreground">Input:</span>
              <pre className="mt-1 overflow-auto max-h-32">
                {JSON.stringify(toolCall.input, null, 2)}
              </pre>
            </div>
          )}
          {toolCall.output !== undefined && (
            <div>
              <span className="text-muted-foreground">Output:</span>
              <pre className="mt-1 overflow-auto max-h-48 text-xs">
                {formatToolOutput(toolCall.output)}
              </pre>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
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
              <pre className="bg-muted p-2 rounded-md overflow-x-auto text-xs my-2">
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
            <h1 className="text-base font-bold mt-3 mb-2">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-bold mt-2 mb-1">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>
          ),
          // Style blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-primary pl-2 italic my-2 text-xs">
              {children}
            </blockquote>
          ),
          // Style paragraphs
          p: ({ children }) => <p className="my-1">{children}</p>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

// Helper to format tool output for display
function formatToolOutput(output: unknown): string {
  if (output === null || output === undefined) {
    return "null"
  }
  if (typeof output === "string") {
    const truncated = output.slice(0, 1500)
    return output.length > 1500 ? truncated + "\n... (truncated)" : truncated
  }
  try {
    const str = JSON.stringify(output, null, 2)
    const truncated = str.slice(0, 1500)
    return str.length > 1500 ? truncated + "\n... (truncated)" : truncated
  } catch {
    return String(output)
  }
}

export default AIChatModal
