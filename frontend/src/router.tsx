import { createRouter, createRoute } from "@tanstack/react-router"
import { Route as rootRoute } from "./routes/__root"
import { Route as indexRoute } from "./routes/index"
import { Route as logsRoute } from "./routes/logs"
import { Route as chatRoute } from "./routes/chat"
import { Route as costsRoute } from "./routes/costs"
import { Route as cloudRunRoute } from "./routes/services/cloud-run"

// Create placeholder routes for services that will be implemented
const servicesIndexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">GCP Services Overview</h1>
      <p className="text-muted-foreground mt-2">Select a service from the sidebar to view details.</p>
    </div>
  ),
})

const functionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/functions",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">Cloud Functions</h1>
      <p className="text-muted-foreground mt-2">Cloud Functions dashboard - coming soon</p>
    </div>
  ),
})

const gkeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/gke",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">Google Kubernetes Engine</h1>
      <p className="text-muted-foreground mt-2">GKE dashboard - coming soon</p>
    </div>
  ),
})

const computeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/compute",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">Compute Engine</h1>
      <p className="text-muted-foreground mt-2">Compute Engine dashboard - coming soon</p>
    </div>
  ),
})

const storageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/storage",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">Cloud Storage</h1>
      <p className="text-muted-foreground mt-2">Cloud Storage dashboard - coming soon</p>
    </div>
  ),
})

const bigqueryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/bigquery",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">BigQuery</h1>
      <p className="text-muted-foreground mt-2">BigQuery dashboard - coming soon</p>
    </div>
  ),
})

const pubsubRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/pubsub",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">Pub/Sub</h1>
      <p className="text-muted-foreground mt-2">Pub/Sub dashboard - coming soon</p>
    </div>
  ),
})

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: () => (
    <div className="p-4">
      <h1 className="text-3xl font-bold">Settings</h1>
      <p className="text-muted-foreground mt-2">Application settings - coming soon</p>
    </div>
  ),
})

// Build the route tree
const routeTree = rootRoute.addChildren([
  indexRoute,
  logsRoute,
  chatRoute,
  costsRoute,
  servicesIndexRoute,
  cloudRunRoute,
  functionsRoute,
  gkeRoute,
  computeRoute,
  storageRoute,
  bigqueryRoute,
  pubsubRoute,
  settingsRoute,
])

// Create the router
export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
})

// Register the router for type safety
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
