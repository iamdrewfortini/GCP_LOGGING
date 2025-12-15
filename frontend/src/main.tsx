import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ApolloProvider } from "@apollo/client"
import { apolloClient } from "./lib/apollo"
import { AuthProvider } from "./contexts/AuthContext"
import { AuthGuard } from "./components/auth/auth-guard"
import { router } from "./router"
import "./index.css"

// Create a query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ApolloProvider client={apolloClient}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthGuard>
            <RouterProvider router={router} />
          </AuthGuard>
        </AuthProvider>
      </QueryClientProvider>
    </ApolloProvider>
  </StrictMode>
)
