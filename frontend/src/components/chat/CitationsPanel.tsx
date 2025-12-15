/**
 * Citations Panel Component
 * Phase 3, Task 3.8: Create CitationsPanel component
 * 
 * Displays sources and citations with relevance scores and excerpts
 */

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ChevronDown, ChevronRight, FileText, ExternalLink } from "lucide-react"
import type { Citation } from "@/hooks/use-chat-stream"

interface CitationsPanelProps {
  citations: Citation[]
  className?: string
}

export function CitationsPanel({ citations, className }: CitationsPanelProps) {
  if (!citations || citations.length === 0) {
    return null
  }

  // Sort citations by relevance score (highest first)
  const sortedCitations = [...citations].sort(
    (a, b) => b.relevanceScore - a.relevanceScore
  )

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <FileText className="h-4 w-4" />
          Sources & Citations ({citations.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {sortedCitations.map((citation, index) => (
            <CitationItem key={index} citation={citation} index={index} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

interface CitationItemProps {
  citation: Citation
  index: number
}

function CitationItem({ citation, index }: CitationItemProps) {
  const [isOpen, setIsOpen] = useState(false)

  const getRelevanceColor = (score: number) => {
    if (score >= 0.8) return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
    if (score >= 0.6) return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
    if (score >= 0.4) return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
    return "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200"
  }

  const getRelevanceLabel = (score: number) => {
    if (score >= 0.8) return "High"
    if (score >= 0.6) return "Medium"
    if (score >= 0.4) return "Low"
    return "Very Low"
  }

  const highlightExcerpt = (content: string) => {
    // Simple highlighting - could be enhanced with actual search term matching
    return content
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
              <span className="text-xs font-medium text-muted-foreground">
                [{index + 1}]
              </span>
              <span className="text-sm font-medium truncate max-w-[200px]">
                {citation.source}
              </span>
            </div>
            <Badge 
              variant="outline" 
              className={getRelevanceColor(citation.relevanceScore)}
            >
              {getRelevanceLabel(citation.relevanceScore)} ({(citation.relevanceScore * 100).toFixed(0)}%)
            </Badge>
          </div>
        </CollapsibleTrigger>

        {/* Collapsible Content */}
        <CollapsibleContent className="space-y-3 pt-2">
          {/* Excerpt */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">Excerpt:</div>
            <div className="bg-muted rounded p-3 text-sm">
              <p className="text-foreground/90 leading-relaxed">
                {highlightExcerpt(citation.content)}
              </p>
            </div>
          </div>

          {/* Metadata */}
          {citation.metadata && Object.keys(citation.metadata).length > 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground">Metadata:</div>
              <div className="bg-muted rounded p-2 text-xs font-mono">
                <dl className="space-y-1">
                  {Object.entries(citation.metadata).map(([key, value]) => (
                    <div key={key} className="flex gap-2">
                      <dt className="font-semibold text-muted-foreground">{key}:</dt>
                      <dd className="text-foreground">
                        {typeof value === "string" ? value : JSON.stringify(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2 border-t">
            <button
              className="text-xs text-primary hover:underline flex items-center gap-1"
              onClick={() => {
                // Could open source in new tab or copy to clipboard
                console.log("View source:", citation.source)
              }}
            >
              <ExternalLink className="h-3 w-3" />
              View Source
            </button>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}
