# Generated Types

## Current State
- **Manual Types**: `frontend/src/types/graphql.ts` with basic interfaces for `LogEntry`, `LogQuery`, `Health`, etc.
- **No Codegen Configured**: Repo does not have GraphQL codegen setup.

## Path to Add Codegen Later
1. Install codegen packages:
   ```bash
   cd frontend
   npm install --save-dev @graphql-codegen/cli @graphql-codegen/typescript @graphql-codegen/typescript-operations @graphql-codegen/typescript-react-apollo
   ```

2. Create `codegen.yml` in frontend/:
   ```yaml
   schema: http://localhost:8000/graphql
   documents: src/**/*.tsx
   generates:
     src/types/generated.ts:
       plugins:
         - typescript
         - typescript-operations
         - typescript-react-apollo
   ```

3. Add script to `package.json`:
   ```json
   "scripts": {
     "generate": "graphql-codegen"
   }
   ```

4. Run `npm run generate` to generate types/hooks from schema.

## Rationale
- Manual types used initially for speed.
- Codegen recommended for long-term type safety and auto-generated hooks.
- Single source of truth: GraphQL schema drives types.