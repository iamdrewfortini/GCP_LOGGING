import { createRoute } from "@tanstack/react-router"
import { Route as rootRoute } from "./__root"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { DollarSign, TrendingUp, TrendingDown, AlertCircle } from "lucide-react"

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/costs",
  component: CostsPage,
})

const costData = [
  { service: "Cloud Run", cost: 456.78, change: 12, budget: 500 },
  { service: "BigQuery", cost: 234.56, change: -5, budget: 300 },
  { service: "Cloud Storage", cost: 123.45, change: 8, budget: 150 },
  { service: "Cloud Functions", cost: 89.12, change: 25, budget: 100 },
  { service: "Pub/Sub", cost: 45.67, change: -2, budget: 60 },
  { service: "Cloud Logging", cost: 34.89, change: 15, budget: 50 },
]

export function CostsPage() {
  const totalCost = costData.reduce((sum, item) => sum + item.cost, 0)
  const totalBudget = costData.reduce((sum, item) => sum + item.budget, 0)
  const percentUsed = (totalCost / totalBudget) * 100

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Cost Analytics</h1>
          <p className="text-muted-foreground">
            Monitor and optimize your GCP spending
          </p>
        </div>
        <Select defaultValue="30d">
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
            <SelectItem value="90d">Last 90 days</SelectItem>
            <SelectItem value="ytd">Year to date</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Spend (MTD)</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${totalCost.toFixed(2)}</div>
            <p className="text-xs text-muted-foreground">
              of ${totalBudget.toFixed(2)} budget
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Budget Used</CardTitle>
            {percentUsed > 90 ? (
              <AlertCircle className="h-4 w-4 text-destructive" />
            ) : (
              <TrendingUp className="h-4 w-4 text-green-500" />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{percentUsed.toFixed(1)}%</div>
            <div className="mt-2 h-2 rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${
                  percentUsed > 90 ? "bg-destructive" :
                  percentUsed > 75 ? "bg-yellow-500" : "bg-green-500"
                }`}
                style={{ width: `${Math.min(percentUsed, 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Forecast (EOM)</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${(totalCost * 1.15).toFixed(2)}</div>
            <p className="text-xs text-muted-foreground">
              Based on current usage
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">vs Last Month</CardTitle>
            <TrendingDown className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">-8.5%</div>
            <p className="text-xs text-muted-foreground">
              $89.45 savings
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Cost Breakdown Table */}
      <Card>
        <CardHeader>
          <CardTitle>Cost by Service</CardTitle>
          <CardDescription>Breakdown of spending across GCP services</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Service</TableHead>
                <TableHead className="text-right">Cost (MTD)</TableHead>
                <TableHead className="text-right">Budget</TableHead>
                <TableHead className="text-right">% Used</TableHead>
                <TableHead className="text-right">Change</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {costData.map((item) => {
                const percentUsed = (item.cost / item.budget) * 100
                return (
                  <TableRow key={item.service}>
                    <TableCell className="font-medium">{item.service}</TableCell>
                    <TableCell className="text-right">${item.cost.toFixed(2)}</TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      ${item.budget.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 h-2 rounded-full bg-muted">
                          <div
                            className={`h-full rounded-full ${
                              percentUsed > 90 ? "bg-destructive" :
                              percentUsed > 75 ? "bg-yellow-500" : "bg-green-500"
                            }`}
                            style={{ width: `${Math.min(percentUsed, 100)}%` }}
                          />
                        </div>
                        <span className="text-sm">{percentUsed.toFixed(0)}%</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <span className={item.change >= 0 ? "text-red-500" : "text-green-500"}>
                        {item.change >= 0 ? "+" : ""}{item.change}%
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={percentUsed > 90 ? "destructive" : "secondary"}
                      >
                        {percentUsed > 90 ? "Over Budget" :
                         percentUsed > 75 ? "Warning" : "On Track"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
