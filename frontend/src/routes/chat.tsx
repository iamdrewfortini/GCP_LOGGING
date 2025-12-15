import { createRoute } from "@tanstack/react-router"
import { Route as rootRoute } from "./__root"
import { EnhancedChat } from "@/components/chat/enhanced-chat"

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chat",
  component: ChatPage,
})

export function ChatPage() {
  return <EnhancedChat showSidebar={true} />
}
