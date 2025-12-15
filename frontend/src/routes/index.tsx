import { createRoute, Link } from "@tanstack/react-router"
import { Route as rootRoute } from "./__root"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Activity,
  AlertTriangle,
  Server,
  DollarSign,
  MessageSquare,
  Search,
  RefreshCw,
} from "lucide-react"
import { useSeverityStats, useServiceStats } from "@/hooks/use-logs"
import { AIChatModal } from "@/components/chat/ai-chat-modal"

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardPage,
})

export function DashboardPage() {
  const { data: severityStats, isLoading: severityLoading, refetch: refetchSeverity } = useSeverityStats(24)
  const { data: serviceStats, isLoading: serviceLoading, refetch: refetchServices } = useServiceStats(24)

  const totalLogs = severityStats
    ? Object.values(severityStats.data).reduce((a, b) => a + b, 0)
    : 0

  const errorCount = severityStats
    ? (severityStats.data["ERROR"] || 0) +
      (severityStats.data["CRITICAL"] || 0) +
      (severityStats.data["ALERT"] || 0) +
      (severityStats.data["EMERGENCY"] || 0)
    : 0

  const warningCount = severityStats?.data["WARNING"] || 0

  const handleRefresh = () => {
    refetchSeverity()
    refetchServices()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            GCP Infrastructure Portal - Real-time Overview
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <AIChatModal
            trigger={
              <Button size="sm">
                <MessageSquare className="h-4 w-4 mr-2" />
                AI Assistant
              </Button>
            }
          />
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Logs (24h)</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {severityLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {totalLogs.toLocaleString()}
                </div>
                <p className="text-xs text-muted-foreground">
                  Across all services
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Errors (24h)</CardTitle>
            <AlertTriangle className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            {severityLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold text-destructive">
                  {errorCount.toLocaleString()}
                </div>
                <Link to="/logs" search={{ severity: "ERROR" }}>
                  <p className="text-xs text-muted-foreground hover:underline cursor-pointer">
                    View all errors →
                  </p>
                </Link>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Warnings (24h)</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            {severityLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold text-yellow-600">
                  {warningCount.toLocaleString()}
                </div>
                <Link to="/logs" search={{ severity: "WARNING" }}>
                  <p className="text-xs text-muted-foreground hover:underline cursor-pointer">
                    View warnings →
                  </p>
                </Link>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Services</CardTitle>
            <Server className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {serviceLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {serviceStats?.data.length || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  Logging in last 24h
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Severity Breakdown & Services */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Severity Distribution</CardTitle>
            <CardDescription>Log counts by severity level (24h)</CardDescription>
          </CardHeader>
          <CardContent>
            {severityLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {[
                  { severity: "ERROR", color: "bg-red-500", textColor: "text-red-600" },
                  { severity: "WARNING", color: "bg-yellow-500", textColor: "text-yellow-600" },
                  { severity: "INFO", color: "bg-blue-500", textColor: "text-blue-600" },
                  { severity: "DEBUG", color: "bg-gray-500", textColor: "text-gray-600" },
                  { severity: "CRITICAL", color: "bg-red-700", textColor: "text-red-700" },
                ].map(({ severity, color, textColor }) => {
                  const count = severityStats?.data[severity] || 0
                  const percent = totalLogs > 0 ? (count / totalLogs) * 100 : 0
                  return (
                    <div key={severity} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{severity}</span>
                        <span className={textColor}>{count.toLocaleString()}</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div
                          className={`h-full rounded-full ${color}`}
                          style={{ width: `${Math.min(percent, 100)}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Services by Logs</CardTitle>
            <CardDescription>Services with most log entries (24h)</CardDescription>
          </CardHeader>
          <CardContent>
            {serviceLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {serviceStats?.data.slice(0, 6).map((svc) => {
                  const errorRate =
                    svc.count > 0 ? (svc.error_count / svc.count) * 100 : 0
                  return (
                    <div
                      key={svc.service}
                      className="flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`h-2 w-2 rounded-full ${
                            errorRate > 10
                              ? "bg-red-500"
                              : errorRate > 5
                              ? "bg-yellow-500"
                              : "bg-green-500"
                          }`}
                        />
                        <span className="font-medium truncate max-w-[150px]">
                          {svc.service || "unknown"}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">
                          {svc.count.toLocaleString()}
                        </span>
                        {svc.error_count > 0 && (
                          <Badge variant="destructive" className="text-xs">
                            {svc.error_count} errors
                          </Badge>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
          <CardDescription>Common tasks and shortcuts</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-4">
            <Link to="/logs">
              <Button variant="outline" className="w-full justify-start">
                <Search className="h-4 w-4 mr-2" />
                Search Logs
              </Button>
            </Link>
            <Link to="/logs" search={{ severity: "ERROR" }}>
              <Button variant="outline" className="w-full justify-start">
                <AlertTriangle className="h-4 w-4 mr-2" />
                View Errors
              </Button>
            </Link>
            <Link to="/chat">
              <Button variant="outline" className="w-full justify-start">
                <MessageSquare className="h-4 w-4 mr-2" />
                AI Debugger
              </Button>
            </Link>
            <Link to="/costs">
              <Button variant="outline" className="w-full justify-start">
                <DollarSign className="h-4 w-4 mr-2" />
                Cost Analytics
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
