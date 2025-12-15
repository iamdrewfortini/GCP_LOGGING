/**
 * Tool Call Timeline Component
 * Phase 3, Task 3.7: Create ToolCallTimeline component
 * 
 * Displays tool execution timeline with collapsible input/output
 */

import { useState } from "react"
import { ChevronDown, ChevronRight, CheckCircle, Loader2, XCircle, Clock } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Badge } from "@/components/ui/badge"
import type { ToolCall } from "@/hooks/use-chat-stream"

interface ToolCallTimelineProps {
  toolCalls: ToolCall[]
  className?: string
}

export function ToolCallTimeline({ toolCalls, className }: ToolCallTimelineProps) {
  if (!toolCalls || toolCalls.length === 0) {
    return null
  }

  return (
    <Card className={className}>
      <CardContent className="pt-6">
        <div className="space-y-1">
          <h4 className="text-sm font-medium mb-3">Tool Executions</h4>
          <div className="space-y-2">
            {toolCalls.map((toolCall) => (
              <ToolCallItem key={toolCall.id} toolCall={toolCall} />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

interface ToolCallItemProps {
  toolCall: ToolCall
}

function ToolCallItem({ toolCall }: ToolCallItemProps) {
  const [isOpen, setIsOpen] = useState(false)

  const statusIcon = {
    running: <Loader2 className="h-4 w-4 animate-spin text-blue-500" />,
    completed: <CheckCircle className="h-4 w-4 text-green-500" />,
    error: <XCircle className="h-4 w-4 text-red-500" />,
  }[toolCall.status]

  const statusColor = {
    running: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    completed: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    error: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  }[toolCall.status]

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const formatCost = (usd: number) => {
    return `$${usd.toFixed(4)}`
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="border rounded-lg p-3 space-y-2">
        {/* Header */}
        <CollapsibleTrigger className="w-full">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isOpen ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
              {statusIcon}
              <span className="text-sm font-medium">{toolCall.tool}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={statusColor}>
                {toolCall.status}
              </Badge>
              {toolCall.durationMs !== undefined && (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {formatDuration(toolCall.durationMs)}
                </div>
              )}
            </div>
          </div>
        </CollapsibleTrigger>

        {/* Collapsible Content */}
        <CollapsibleContent className="space-y-3 pt-2">
          {/* Input */}
          {toolCall.input && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground">Input:</div>
              <div className="bg-muted rounded p-2 text-xs font-mono overflow-x-auto">
                <pre>{JSON.stringify(toolCall.input, null, 2)}</pre>
              </div>
            </div>
          )}

          {/* Output */}
          {toolCall.output && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground">Output:</div>
              <div className="bg-muted rounded p-2 text-xs font-mono overflow-x-auto max-h-48 overflow-y-auto">
                <pre>
                  {typeof toolCall.output === "string"
                    ? toolCall.output
                    : JSON.stringify(toolCall.output, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground pt-2 border-t">
            {toolCall.tokenCount !== undefined && (
              <span>Tokens: {toolCall.tokenCount.toLocaleString()}</span>
            )}
            {toolCall.costUsd !== undefined && (
              <span>Cost: {formatCost(toolCall.costUsd)}</span>
            )}
            {toolCall.startedAt && (
              <span>
                Started: {new Date(toolCall.startedAt).toLocaleTimeString()}
              </span>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}
