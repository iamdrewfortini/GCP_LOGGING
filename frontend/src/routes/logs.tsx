import { createRoute } from "@tanstack/react-router"
import { Route as rootRoute } from "./__root"
import { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Search,
  RefreshCw,
  Download,
  Play,
  Pause,
  AlertCircle,
  Loader2,
} from "lucide-react"
import { useLogs, useSeverityStats } from "@/hooks/use-logs"
import type { LogEntry, LogSeverity } from "@/types/api"

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/logs",
  component: LogsPage,
})

const severityColors: Record<string, string> = {
  DEFAULT: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
  DEBUG: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
  INFO: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  NOTICE: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200",
  WARNING: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  ERROR: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  CRITICAL: "bg-red-200 text-red-900 dark:bg-red-800 dark:text-red-100",
  ALERT: "bg-orange-200 text-orange-900 dark:bg-orange-800 dark:text-orange-100",
  EMERGENCY: "bg-purple-200 text-purple-900 dark:bg-purple-800 dark:text-purple-100",
}

const severityOptions: LogSeverity[] = [
  "DEBUG",
  "INFO",
  "NOTICE",
  "WARNING",
  "ERROR",
  "CRITICAL",
  "ALERT",
  "EMERGENCY",
]

function LogsPage() {
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [severity, setSeverity] = useState<string>("all")
  const [service, setService] = useState<string>("all")
  const [hours, setHours] = useState(24)
  const [limit] = useState(100)
  const [isStreaming, setIsStreaming] = useState(false)
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null)

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  // Fetch logs with TanStack Query
  const {
    data: logsData,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useLogs({
    hours,
    limit,
    severity: severity !== "all" ? (severity as LogSeverity) : undefined,
    service: service !== "all" ? service : undefined,
    search: debouncedSearch || undefined,
  })

  // Fetch severity stats for overview
  const { data: severityStats } = useSeverityStats(hours)

  // Extract unique services from logs for the filter dropdown
  const services = logsData?.data
    ? [...new Set(logsData.data.map((log) => log.service_name).filter(Boolean))]
    : []

  const handleRefresh = () => {
    refetch()
  }

  const handleExport = () => {
    if (!logsData?.data) return

    const csv = [
      ["Timestamp", "Severity", "Service", "Source", "Message"].join(","),
      ...logsData.data.map((log) =>
        [
          log.event_timestamp,
          log.severity,
          log.service_name || "",
          log.source_table,
          `"${(log.display_message || "").replace(/"/g, '""')}"`,
        ].join(",")
      ),
    ].join("\n")

    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `logs-${new Date().toISOString()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Log Explorer</h1>
          <p className="text-muted-foreground">
            Search and analyze logs across all GCP services
          </p>
        </div>
        {logsData && (
          <div className="text-sm text-muted-foreground">
            Showing {logsData.count} logs from last {hours}h
          </div>
        )}
      </div>

      {/* Stats Cards */}
      {severityStats && (
        <div className="grid gap-2 md:grid-cols-5">
          {["ERROR", "WARNING", "INFO", "DEBUG"].map((sev) => (
            <Card key={sev} className="py-2">
              <CardContent className="flex items-center justify-between p-3">
                <Badge className={severityColors[sev]} variant="secondary">
                  {sev}
                </Badge>
                <span className="text-2xl font-bold">
                  {severityStats.data[sev] || 0}
                </span>
              </CardContent>
            </Card>
          ))}
          <Card className="py-2">
            <CardContent className="flex items-center justify-between p-3">
              <span className="text-sm text-muted-foreground">Total</span>
              <span className="text-2xl font-bold">
                {Object.values(severityStats.data).reduce((a, b) => a + b, 0)}
              </span>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap gap-4">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search logs..."
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <Select value={severity} onValueChange={setSeverity}>
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Severity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Severities</SelectItem>
                {severityOptions.map((sev) => (
                  <SelectItem key={sev} value={sev}>
                    {sev}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={service} onValueChange={setService}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Service" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Services</SelectItem>
                {services.map((svc) => (
                  <SelectItem key={svc} value={svc!}>
                    {svc}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={String(hours)} onValueChange={(v) => setHours(Number(v))}>
              <SelectTrigger className="w-[120px]">
                <SelectValue placeholder="Time Range" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Last 1h</SelectItem>
                <SelectItem value="6">Last 6h</SelectItem>
                <SelectItem value="24">Last 24h</SelectItem>
                <SelectItem value="72">Last 3d</SelectItem>
                <SelectItem value="168">Last 7d</SelectItem>
              </SelectContent>
            </Select>

            <div className="flex gap-2">
              <Button
                variant="outline"
                size="icon"
                onClick={handleRefresh}
                disabled={isFetching}
              >
                {isFetching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
              </Button>
              <Button variant="outline" size="icon" onClick={handleExport}>
                <Download className="h-4 w-4" />
              </Button>
              <Button
                variant={isStreaming ? "destructive" : "default"}
                onClick={() => setIsStreaming(!isStreaming)}
              >
                {isStreaming ? (
                  <>
                    <Pause className="mr-2 h-4 w-4" />
                    Stop
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Stream
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error State */}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="flex items-center gap-3 py-4">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Failed to load logs</p>
              <p className="text-sm text-muted-foreground">
                {error instanceof Error ? error.message : "Unknown error"}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()} className="ml-auto">
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Log Table */}
      <Card className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <Table>
            <TableHeader className="sticky top-0 bg-card z-10">
              <TableRow>
                <TableHead className="w-[180px]">Timestamp</TableHead>
                <TableHead className="w-[100px]">Severity</TableHead>
                <TableHead className="w-[150px]">Service</TableHead>
                <TableHead className="w-[150px]">Source</TableHead>
                <TableHead>Message</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                // Loading skeleton
                Array.from({ length: 10 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      <Skeleton className="h-4 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-24" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-28" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              ) : logsData?.data.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8">
                    <p className="text-muted-foreground">No logs found</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Try adjusting your filters or time range
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                logsData?.data.map((log) => (
                  <TableRow
                    key={log.insert_id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setSelectedLog(log)}
                  >
                    <TableCell className="font-mono text-xs">
                      {new Date(log.event_timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={severityColors[log.severity]}
                        variant="secondary"
                      >
                        {log.severity}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-medium">
                      {log.service_name || "-"}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {log.source_table.split("_").slice(0, 2).join("_")}
                    </TableCell>
                    <TableCell className="max-w-[500px] truncate font-mono text-sm">
                      {log.display_message || "-"}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </Card>

      {/* Log Detail Sheet */}
      <Sheet open={!!selectedLog} onOpenChange={() => setSelectedLog(null)}>
        <SheetContent className="w-[600px] sm:max-w-[600px]">
          <SheetHeader>
            <SheetTitle>Log Details</SheetTitle>
            <SheetDescription>
              {selectedLog?.event_timestamp &&
                new Date(selectedLog.event_timestamp).toLocaleString()}
            </SheetDescription>
          </SheetHeader>
          {selectedLog && (
            <div className="mt-6 space-y-4">
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Severity
                </label>
                <div className="mt-1">
                  <Badge
                    className={severityColors[selectedLog.severity]}
                    variant="secondary"
                  >
                    {selectedLog.severity}
                  </Badge>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Service
                </label>
                <p className="mt-1 font-medium">
                  {selectedLog.service_name || "-"}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Source Table
                </label>
                <p className="mt-1 font-mono text-sm">{selectedLog.source_table}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Log Name
                </label>
                <p className="mt-1 font-mono text-sm text-muted-foreground">
                  {selectedLog.log_name || "-"}
                </p>
              </div>
              {selectedLog.trace_id && (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">
                    Trace ID
                  </label>
                  <p className="mt-1 font-mono text-sm">{selectedLog.trace_id}</p>
                </div>
              )}
              {selectedLog.span_id && (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">
                    Span ID
                  </label>
                  <p className="mt-1 font-mono text-sm">{selectedLog.span_id}</p>
                </div>
              )}
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Message
                </label>
                <pre className="mt-1 whitespace-pre-wrap rounded-md bg-muted p-3 font-mono text-sm max-h-[300px] overflow-auto">
                  {selectedLog.display_message || "-"}
                </pre>
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Insert ID
                </label>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {selectedLog.insert_id}
                </p>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
