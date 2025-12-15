# Next 10 Commits Checklist

**Date:** 2025-12-15

This checklist outlines small, mergeable steps to continue building out the AI Log/Chat Intelligence Stack.

1.  **Integrate `search_memory` tool into LangGraph.**
    *   Modify `src/agent/graph.py` to add `search_memory` to the agent's tools.
    *   Add a new node or integrate into `retrieval` node to call `search_memory` based on user intent.
    *   *Verification:* Write a unit test for the LangGraph agent to ensure it can call `search_memory` and process its output.

2.  **Implement `bq_query_readonly` tool via MCP Generator.**
    *   Create `specs/tools/bq_query_readonly.yaml`.
    *   Run `scripts/generate_mcp_tool.py` to generate `src/agent/tools/generated/bq_query_readonly.py`.
    *   *Verification:* Write a simple Python script to directly call the generated `bq_query_readonly` tool (with a safe `SELECT` query) and assert its output.

3.  **Enhance `src/security/policy.py` for dynamic policy loading.**
    *   Modify `enforce_policy` to read policies from tool YAML specs (e.g., `deny_keywords`, `allowed_datasets`).
    *   *Verification:* Add unit tests for `enforce_policy` covering allowed and denied BigQuery queries.

4.  **Frontend: Integrate `ArtifactViewer` into `EnhancedChat` component.**
    *   Modify `frontend/src/components/chat/enhanced-chat.tsx` to display `ArtifactViewer` when an artifact event is received from the SSE stream.
    *   *Verification:* Manually test the frontend with a mock artifact stream event to ensure the component renders correctly.

5.  **Develop `bq_get_schema` tool via MCP Generator.**
    *   Create `specs/tools/bq_get_schema.yaml`.
    *   Implement `src/services/bigquery_service.get_table_schema` stub.
    *   Generate the tool.
    *   *Verification:* Call the generated tool to get a known table's schema and verify the output structure.

6.  **Implement full `repo_search` tool (hybrid) via MCP Generator.**
    *   Create `specs/tools/repo_search.yaml`.
    *   Implement `src/services/qdrant_service.hybrid_repo_search` that combines keyword and vector search.
    *   Generate the tool.
    *   *Verification:* Run a test with an indexed repository, perform a semantic search, and verify relevant code chunks are returned.

7.  **Implement `RepoIndexSnapshot` creation and listing.**
    *   Create `repo_snapshot_create` and `repo_snapshot_list` tools (YAML specs + service stubs + generator).
    *   *Verification:* Use the tools to create a snapshot and list existing ones.

8.  **Frontend: Implement `useArtifacts` hook and Artifacts Panel.**
    *   Create a React hook (`frontend/src/hooks/use-artifacts.ts`) to manage artifact state.
    *   Build a UI panel to list and open artifacts associated with a session.
    *   *Verification:* Ensure artifacts are listed and can be opened/viewed from the chat UI.

9.  **Frontend: Implement Chat Replay / Debug Mode.**
    *   Develop UI to fetch a conversation from BigQuery (via new API endpoint) and replay events visually.
    *   *Verification:* Replay a conversation and ensure event timeline is accurate.

10. **Implement Token Budgeting and Summarization in LangGraph.**
    *   Add a `token_counter` to `AgentState` and `summarizer` node to periodically summarize long conversations, offloading to Qdrant/Firebase.
    *   *Verification:* Run a long conversation and verify summaries are generated and context window is managed.
