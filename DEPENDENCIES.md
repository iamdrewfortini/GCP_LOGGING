# Dependencies Plan

## Backend Additions (Python/requirements.txt)
- `strawberry-graphql[fastapi]==0.236.0`: Strawberry GraphQL for FastAPI integration, provides GraphQL router and schema definition. Chosen for seamless FastAPI compatibility and type safety.

## Frontend Additions (JS/package.json)
- `@apollo/client==3.11.0`: Apollo Client for GraphQL queries/mutations with caching and link support.
- `graphql==16.9.0`: GraphQL.js library for parsing and executing GraphQL operations.

## Rationale
- Strawberry selected over Graphene due to better FastAPI integration and modern Python support.
- Apollo Client chosen for robust caching, error handling, and TanStack Query compatibility.
- Versions pinned to latest stable as of 2024, compatible with existing FastAPI (0.104+) and React 19.

## Installation Commands
```bash
# Backend
pip install strawberry-graphql[fastapi]==0.236.0

# Frontend
cd frontend
npm install @apollo/client@3.11.0 graphql@16.9.0
# or pnpm add @apollo/client@3.11.0 graphql@16.9.0
```

## No Changes to Existing Deps
- Existing @tanstack/react-query and firebase remain unchanged.
- No breaking changes to current stack.