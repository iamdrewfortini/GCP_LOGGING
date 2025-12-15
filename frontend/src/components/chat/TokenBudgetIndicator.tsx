/**
 * Token Budget Indicator Component
 * Phase 3, Task 3.6: Create TokenBudgetIndicator component
 * 
 * Displays token usage with a progress bar and color coding
 */

import { useMemo } from "react"
import { Progress } from "@/components/ui/progress"
import { Card, CardContent } from "@/components/ui/card"
import { AlertCircle, CheckCircle, AlertTriangle } from "lucide-react"
import type { TokenBudget } from "@/hooks/use-chat-stream"

interface TokenBudgetIndicatorProps {
  tokenBudget: TokenBudget | null
  className?: string
}

export function TokenBudgetIndicator({ tokenBudget, className }: TokenBudgetIndicatorProps) {
  const budgetStatus = useMemo(() => {
    if (!tokenBudget) {
      return {
        percentage: 0,
        color: "bg-gray-500",
        icon: CheckCircle,
        status: "idle",
        message: "No token usage yet",
      }
    }

    const percentage = (tokenBudget.totalTokens / tokenBudget.budgetMax) * 100

    if (percentage >= 90) {
      return {
        percentage,
        color: "bg-red-500",
        icon: AlertCircle,
        status: "critical",
        message: "Token budget critical",
      }
    } else if (percentage >= 70) {
      return {
        percentage,
        color: "bg-yellow-500",
        icon: AlertTriangle,
        status: "warning",
        message: "Token budget high",
      }
    } else {
      return {
        percentage,
        color: "bg-green-500",
        icon: CheckCircle,
        status: "healthy",
        message: "Token budget healthy",
      }
    }
  }, [tokenBudget])

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat("en-US").format(num)
  }

  if (!tokenBudget) {
    return null
  }

  const Icon = budgetStatus.icon

  return (
    <Card className={className}>
      <CardContent className="pt-6">
        <div className="space-y-3">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Icon className={`h-4 w-4 ${
                budgetStatus.status === "critical" ? "text-red-500" :
                budgetStatus.status === "warning" ? "text-yellow-500" :
                "text-green-500"
              }`} />
              <span className="text-sm font-medium">Token Usage</span>
            </div>
            <span className="text-xs text-muted-foreground">
              {budgetStatus.message}
            </span>
          </div>

          {/* Progress Bar */}
          <div className="space-y-2">
            <Progress 
              value={budgetStatus.percentage} 
              className="h-2"
              indicatorClassName={budgetStatus.color}
            />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {formatNumber(tokenBudget.totalTokens)} / {formatNumber(tokenBudget.budgetMax)} tokens
              </span>
              <span>
                {budgetStatus.percentage.toFixed(1)}% used
              </span>
            </div>
          </div>

          {/* Token Breakdown */}
          <div className="grid grid-cols-3 gap-2 pt-2 border-t">
            <div className="text-center">
              <div className="text-xs text-muted-foreground">Input</div>
              <div className="text-sm font-medium">
                {formatNumber(tokenBudget.promptTokens)}
              </div>
            </div>
            <div className="text-center">
              <div className="text-xs text-muted-foreground">Output</div>
              <div className="text-sm font-medium">
                {formatNumber(tokenBudget.completionTokens)}
              </div>
            </div>
            <div className="text-center">
              <div className="text-xs text-muted-foreground">Remaining</div>
              <div className="text-sm font-medium">
                {formatNumber(tokenBudget.budgetRemaining)}
              </div>
            </div>
          </div>

          {/* Model Info */}
          <div className="flex items-center justify-between pt-2 border-t text-xs text-muted-foreground">
            <span>Model: {tokenBudget.model}</span>
            {tokenBudget.shouldSummarize && (
              <span className="text-yellow-600 dark:text-yellow-400">
                ⚠️ Summarization recommended
              </span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
