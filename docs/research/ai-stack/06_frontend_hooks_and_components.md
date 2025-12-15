# Frontend Hooks & Components

**Date:** 2025-12-15
**Goal:** Robust client-side handling of streaming chat and artifacts.

## 1. `useChatStream` Hook

This hook manages the SSE connection, state, and optimistic updates.

```typescript
// Conceptual Signature
function useChatStream(sessionId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortController = useRef<AbortController>(null);

  const sendMessage = async (content: string) => {
    // 1. Optimistic Update
    setMessages(prev => [...prev, { role: 'user', content }]);
    
    // 2. Setup Stream
    abortController.current = new AbortController();
    
    // 3. Fetch SSE
    await fetchEventSource('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: content, session_id: sessionId }),
        signal: abortController.current.signal,
        onmessage(ev) {
            const parsed = JSON.parse(ev.data);
            handleEvent(parsed);
        }
    });
  }
  
  // Event Reducer
  const handleEvent = (event: StreamEvent) => {
    switch(event.type) {
        case 'on_chat_model_stream':
            // Append token to last assistant message
            break;
        case 'on_tool_start':
            // Add "Tool Status" indicator
            break;
        case 'on_tool_end':
            // Update "Tool Status" with result/summary
            break;
    }
  }

  return { messages, sendMessage, isStreaming, stop: abortController.current.abort };
}
```

## 2. Component Hierarchy

- `ChatLayout`: Sidebar (Sessions) + Main Area.
- `ChatWindow`: Scrollable area.
  - `MessageList`: Virtualized list (if long history).
    - `MessageBubble`: Renders Markdown.
      - `CodeBlock`: Syntax highlighting + "Copy" button.
      - `ToolInvocation`: Collapsible details of tool use.
      - `ArtifactEmbed`: Preview of generated artifact.
  - `InputArea`: Textarea + Send Button + Attachments.

## 3. Artifact Viewer

A dedicated pane (or modal) to view complex outputs without cluttering the chat.

- **Types:**
  - `SQLPreview`: Syntax highlighted SQL.
  - `DashboardWidget`: Recharts graph.
  - `LogTable`: Interactive data table.
- **Hook:** `useArtifact(artifactId)` fetches metadata and content.

## 4. State Management

- **Global:** `@tanstack/react-query` for fetching Session List and History (initial load).
- **Local:** `useState` / `useReducer` for the active stream (appending tokens is too fast for React Query cache updates).

## 5. Error Handling

- **Network:** Auto-retry with backoff (handled by `fetchEventSource` library usually).
- **Stream Error:** Display inline error bubble, allow "Retry" of last user message.
