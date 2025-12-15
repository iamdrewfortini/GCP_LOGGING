import { createRoute } from "@tanstack/react-router"
import { Route as rootRoute } from "../__root"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ExternalLink, RefreshCw, MoreVertical, Activity } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/cloud-run",
  component: CloudRunPage,
})

// Mock data
const services = [
  {
    name: "glass-pane",
    region: "us-central1",
    url: "https://glass-pane-845772051724.us-central1.run.app",
    revision: "glass-pane-00062-jb5",
    status: "READY",
    traffic: 100,
    lastDeployed: "2025-12-15T09:00:44Z",
    metrics: {
      requests: 1234,
      errorRate: 0.02,
      p50: 45,
      p95: 120,
    },
  },
  {
    name: "api-gateway",
    region: "us-central1",
    url: "https://api-gateway-845772051724.us-central1.run.app",
    revision: "api-gateway-00015-abc",
    status: "READY",
    traffic: 100,
    lastDeployed: "2025-12-14T15:30:00Z",
    metrics: {
      requests: 5678,
      errorRate: 0.05,
      p50: 32,
      p95: 89,
    },
  },
  {
    name: "auth-service",
    region: "us-central1",
    url: "https://auth-service-845772051724.us-central1.run.app",
    revision: "auth-service-00008-xyz",
    status: "DEPLOYING",
    traffic: 80,
    lastDeployed: "2025-12-15T08:45:00Z",
    metrics: {
      requests: 890,
      errorRate: 0.01,
      p50: 28,
      p95: 65,
    },
  },
]

function CloudRunPage() {
  const getStatusColor = (status: string) => {
    switch (status) {
      case "READY": return "bg-green-100 text-green-800"
      case "DEPLOYING": return "bg-blue-100 text-blue-800"
      case "ERROR": return "bg-red-100 text-red-800"
      default: return "bg-gray-100 text-gray-800"
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Cloud Run Services</h1>
          <p className="text-muted-foreground">
            Manage and monitor your Cloud Run deployments
          </p>
        </div>
        <Button>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total Services</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{services.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total Requests (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {services.reduce((sum, s) => sum + s.metrics.requests, 0).toLocaleString()}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Avg Error Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(services.reduce((sum, s) => sum + s.metrics.errorRate, 0) / services.length * 100).toFixed(1)}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Avg P95 Latency</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {Math.round(services.reduce((sum, s) => sum + s.metrics.p95, 0) / services.length)}ms
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Services Table */}
      <Card>
        <CardHeader>
          <CardTitle>Services</CardTitle>
          <CardDescription>All Cloud Run services in your project</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Service</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Region</TableHead>
                <TableHead>Revision</TableHead>
                <TableHead>Traffic</TableHead>
                <TableHead>Requests</TableHead>
                <TableHead>Error Rate</TableHead>
                <TableHead>P95</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {services.map((service) => (
                <TableRow key={service.name}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{service.name}</span>
                      <a
                        href={service.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge className={getStatusColor(service.status)} variant="secondary">
                      {service.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{service.region}</TableCell>
                  <TableCell className="font-mono text-xs">{service.revision}</TableCell>
                  <TableCell>{service.traffic}%</TableCell>
                  <TableCell>{service.metrics.requests.toLocaleString()}</TableCell>
                  <TableCell>
                    <span className={service.metrics.errorRate > 0.03 ? "text-red-500" : ""}>
                      {(service.metrics.errorRate * 100).toFixed(1)}%
                    </span>
                  </TableCell>
                  <TableCell>{service.metrics.p95}ms</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem>
                          <Activity className="mr-2 h-4 w-4" />
                          View Metrics
                        </DropdownMenuItem>
                        <DropdownMenuItem>View Logs</DropdownMenuItem>
                        <DropdownMenuItem>View Revisions</DropdownMenuItem>
                        <DropdownMenuItem>Edit Service</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
