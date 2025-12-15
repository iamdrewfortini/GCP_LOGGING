# GraphQL Frontend Wiring

## Apollo Client Setup
- **File**: `frontend/src/lib/apollo.ts`
- **Features**:
  - HTTP link to `/graphql`
  - Auth link attaching Firebase ID token as `Authorization: Bearer <token>`
  - InMemoryCache with type policies for `LogEntry` (keyFields: ['id']) and `logs` query (pagination merge)

## TanStack Query Integration
- **File**: `frontend/src/hooks/useGraphQL.ts`
- **Wrappers**:
  - `useLogsQuery(filter)`: Wraps Apollo query for logs with TanStack Query caching
  - `useHealthQuery()`: Health check query
  - `useMarkReviewedMutation()`: Mutation to mark log reviewed, invalidates logs queries on success
- **Query Key Convention**: `['logs', filter]` for logs, aligned to GraphQL filters

## Firebase Realtime Integration
- **Hook**: `useRealtimeLogsInvalidation()` in `useGraphQL.ts`
- **Mechanism**: `onSnapshot` on Firestore collection 'logs', invalidates TanStack `['logs']` queries on changes
- **Dedupe**: Uses Firestore snapshot listeners to avoid storms

## Provider Setup
- **File**: `frontend/src/main.tsx`
- **Order**: ApolloProvider > QueryClientProvider > AuthProvider > RouterProvider
- **Purpose**: Ensures Apollo client available for GraphQL operations, TanStack for orchestration

## Usage Example
```tsx
import { useLogsQuery, useRealtimeLogsInvalidation } from '../hooks/useGraphQL';

function LogsPage() {
  const filter = { hours: 24, limit: 50 };
  const { data, isLoading } = useLogsQuery(filter);
  useRealtimeLogsInvalidation(); // Enable realtime invalidation

  if (isLoading) return <div>Loading...</div>;
  return <div>{data.logs.map(log => <LogItem key={log.id} log={log} />)}</div>;
}
```

## No Breaking Changes
- Existing REST calls remain, GraphQL used additively
- Firebase auth integration reused