import { ApolloClient, InMemoryCache, createHttpLink, from } from '@apollo/client';
import { setContext } from '@apollo/client/link/context';
import { getAuth } from 'firebase/auth';

// HTTP Link to GraphQL endpoint
const httpLink = createHttpLink({
  uri: '/graphql', // Relative to frontend server, assume proxy or same origin
});

// Auth Link to attach Firebase ID token
const authLink = setContext(async (_, { headers }) => {
  const auth = getAuth();
  const user = auth.currentUser;
  let token = null;
  if (user) {
    token = await user.getIdToken();
  }
  return {
    headers: {
      ...headers,
      authorization: token ? `Bearer ${token}` : '',
    },
  };
});

// Apollo Client
export const apolloClient = new ApolloClient({
  link: from([authLink, httpLink]),
  cache: new InMemoryCache({
    // Configure cache policies for pagination, id fields
    typePolicies: {
      Query: {
        fields: {
          logs: {
            // Pagination policy
            keyArgs: ['filter'],
            merge(existing, incoming) {
              if (!existing) return incoming;
              return {
                ...incoming,
                logs: [...existing.logs, ...incoming.logs],
              };
            },
          },
        },
      },
      LogEntry: {
        keyFields: ['id'],
      },
    },
  }),
});