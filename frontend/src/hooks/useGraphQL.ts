import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { gql, useApolloClient } from '@apollo/client';
import { onSnapshot, collection } from 'firebase/firestore';
import { getFirestore } from 'firebase/firestore';
import { useEffect } from 'react';

// GraphQL Documents
const LOGS_QUERY = gql`
  query GetLogs($filter: LogFilter!) {
    logs(filter: $filter) {
      logs {
        id
        eventTs
        ingestTs
        projectId
        env
        region
        serviceName
        severity
        eventType
        correlationIds
        labels
        message
        body
        httpMethod
        httpStatus
        traceId
        spanId
      }
      totalCount
      hasMore
    }
  }
`;

const HEALTH_QUERY = gql`
  query GetHealth {
    health {
      ok
      version
      services
    }
  }
`;

const MARK_REVIEWED_MUTATION = gql`
  mutation MarkReviewed($id: ID!) {
    markReviewed(id: $id)
  }
`;

// TanStack Query wrappers
export const useLogsQuery = (filter: any) => {
  const client = useApolloClient();
  return useQuery({
    queryKey: ['logs', filter],
    queryFn: async () => {
      const result = await client.query({
        query: LOGS_QUERY,
        variables: { filter },
      });
      return result.data.logs;
    },
    staleTime: 5 * 60 * 1000, // 5 min
  });
};

export const useHealthQuery = () => {
  const client = useApolloClient();
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const result = await client.query({
        query: HEALTH_QUERY,
      });
      return result.data.health;
    },
  });
};

export const useMarkReviewedMutation = () => {
  const client = useApolloClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const result = await client.mutate({
        mutation: MARK_REVIEWED_MUTATION,
        variables: { id },
      });
      return result.data.markReviewed;
    },
    onSuccess: () => {
      // Invalidate logs queries
      queryClient.invalidateQueries({ queryKey: ['logs'] });
    },
  });
};

// Firebase realtime integration
export const useRealtimeLogsInvalidation = () => {
  const queryClient = useQueryClient();
  const db = getFirestore();

  useEffect(() => {
    // Listen to Firebase RTDB or Firestore for log updates
    // Assume a collection 'logs' or path for realtime updates
    const unsubscribe = onSnapshot(collection(db, 'logs'), (snapshot) => {
      snapshot.docChanges().forEach((change) => {
        if (change.type === 'added' || change.type === 'modified') {
          // Invalidate TanStack queries for logs
          queryClient.invalidateQueries({ queryKey: ['logs'] });
        }
      });
    });

    return () => unsubscribe();
  }, [queryClient, db]);
};