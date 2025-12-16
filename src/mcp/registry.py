"""Tool Registry

Manages registered MCP tools in Firestore.

IMPORTANT: Do not initialize Firebase/Firestore at import time.
- CI environments may not have ADC.
- Import-time side effects can break pytest collection.

Phase 4, Task 4.4: ToolRegistry
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import firestore

logger = logging.getLogger(__name__)

_db_lock = threading.Lock()


def _registry_enabled() -> bool:
    """Whether the MCP tool registry is enabled.

    Defaults to FIREBASE_ENABLED for Cloud Run deploy parity.
    """
    v = os.getenv("MCP_REGISTRY_ENABLED")
    if v is None:
        v = os.getenv("FIREBASE_ENABLED", "false")
    return v.lower() == "true"


class ToolRegistry:
    """Registry for managing generated MCP tools."""

    def __init__(self):
        """Initialize tool registry.

        NOTE: This must remain side-effect free (no network/ADC).
        """
        self._db: Optional[Any] = None
        self._db_init_error: Optional[Exception] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.collection_name = "mcp_tools"

    def _get_db(self) -> Any:
        """Get (or initialize) the Firestore client.

        Raises:
            RuntimeError: If registry is disabled.
            Exception: If Firestore initialization fails.
        """
        if self._db is not None:
            return self._db

        if not _registry_enabled():
            raise RuntimeError(
                "MCP registry is disabled (set MCP_REGISTRY_ENABLED=true or FIREBASE_ENABLED=true)."
            )

        if self._db_init_error is not None:
            raise self._db_init_error

        with _db_lock:
            if self._db is not None:
                return self._db
            if self._db_init_error is not None:
                raise self._db_init_error

            try:
                try:
                    firebase_admin.get_app()
                except ValueError:
                    firebase_admin.initialize_app()

                self._db = firestore.client()
                return self._db
            except Exception as e:
                self._db_init_error = e
                raise
    def register(
        self,
        tool_id: str,
        version: str,
        spec_hash: str,
        module_path: str,
        safety_config: Dict[str, Any],
        permissions: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Register a generated tool.
        
        Args:
            tool_id: Tool identifier
            version: Tool version
            spec_hash: Hash of tool specification
            module_path: Python module path
            safety_config: Safety configuration
            permissions: Required permissions
            metadata: Additional metadata
        """
        tool_doc = {
            "tool_id": tool_id,
            "version": version,
            "spec_hash": spec_hash,
            "module_path": module_path,
            "safety_config": safety_config,
            "permissions": permissions,
            "metadata": metadata or {},
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "status": "active"
        }
        
        # Save to Firestore
        db = self._get_db()
        db.collection(self.collection_name).document(tool_id).set(tool_doc)
        
        # Invalidate cache
        self._cache.pop(tool_id, None)
        
        logger.info(f"Registered tool: {tool_id} v{version} (hash={spec_hash})")
    
    def get_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Get tool metadata by ID.
        
        Args:
            tool_id: Tool identifier
            
        Returns:
            Tool metadata or None if not found
        """
        # Check cache first
        if tool_id in self._cache:
            return self._cache[tool_id]
        
        # Query Firestore
        db = self._get_db()
        doc = db.collection(self.collection_name).document(tool_id).get()
        
        if doc.exists:
            tool_data = doc.to_dict()
            self._cache[tool_id] = tool_data
            return tool_data
        
        return None
    
    def list_tools(
        self,
        status: str = "active",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List registered tools.
        
        Args:
            status: Filter by status (active, deprecated, disabled)
            limit: Maximum number of tools to return
            
        Returns:
            List of tool metadata
        """
        db = self._get_db()
        query = (
            db.collection(self.collection_name)
            .where("status", "==", status)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        
        tools = []
        for doc in query.stream():
            tool_data = doc.to_dict()
            tools.append(tool_data)
        
        return tools
    
    def update_tool(
        self,
        tool_id: str,
        updates: Dict[str, Any]
    ) -> None:
        """Update tool metadata.
        
        Args:
            tool_id: Tool identifier
            updates: Fields to update
        """
        updates["updated_at"] = firestore.SERVER_TIMESTAMP
        
        db = self._get_db()
        db.collection(self.collection_name).document(tool_id).update(updates)
        
        # Invalidate cache
        self._cache.pop(tool_id, None)
        
        logger.info(f"Updated tool: {tool_id}")
    
    def delete_tool(self, tool_id: str) -> None:
        """Delete (soft delete) a tool.
        
        Args:
            tool_id: Tool identifier
        """
        self.update_tool(tool_id, {"status": "deleted"})
        
        logger.info(f"Deleted tool: {tool_id}")
    
    def deprecate_tool(self, tool_id: str, reason: str = "") -> None:
        """Deprecate a tool.
        
        Args:
            tool_id: Tool identifier
            reason: Deprecation reason
        """
        self.update_tool(
            tool_id,
            {
                "status": "deprecated",
                "deprecation_reason": reason,
                "deprecated_at": datetime.now(timezone.utc).isoformat()
            }
        )
        
        logger.info(f"Deprecated tool: {tool_id} (reason: {reason})")
    
    def get_tool_by_hash(self, spec_hash: str) -> Optional[Dict[str, Any]]:
        """Get tool by spec hash.
        
        Args:
            spec_hash: Specification hash
            
        Returns:
            Tool metadata or None if not found
        """
        db = self._get_db()
        query = (
            db.collection(self.collection_name)
            .where("spec_hash", "==", spec_hash)
            .limit(1)
        )
        
        for doc in query.stream():
            return doc.to_dict()
        
        return None
    
    def search_tools(
        self,
        tags: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search tools by tags or permissions.
        
        Args:
            tags: Filter by tags
            permissions: Filter by permissions
            
        Returns:
            List of matching tools
        """
        db = self._get_db()
        query = db.collection(self.collection_name).where("status", "==", "active")
        
        tools = []
        for doc in query.stream():
            tool_data = doc.to_dict()
            
            # Filter by tags
            if tags:
                tool_tags = tool_data.get("metadata", {}).get("tags", [])
                if not any(tag in tool_tags for tag in tags):
                    continue
            
            # Filter by permissions
            if permissions:
                tool_perms = tool_data.get("permissions", [])
                if not any(perm in tool_perms for perm in permissions):
                    continue
            
            tools.append(tool_data)
        
        return tools
    
    def clear_cache(self) -> None:
        """Clear the tool cache."""
        self._cache.clear()
        logger.info("Tool registry cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics.
        
        Returns:
            Statistics about registered tools
        """
        all_tools = self.list_tools(status="active", limit=1000)
        
        stats = {
            "total_tools": len(all_tools),
            "by_status": {},
            "by_permission": {},
            "total_cached": len(self._cache)
        }
        
        # Count by status
        for status in ["active", "deprecated", "disabled", "deleted"]:
            count = len(self.list_tools(status=status, limit=1000))
            stats["by_status"][status] = count
        
        # Count by permission prefix
        for tool in all_tools:
            for perm in tool.get("permissions", []):
                prefix = perm.split(".")[0]
                stats["by_permission"][prefix] = stats["by_permission"].get(prefix, 0) + 1
        
        return stats


# Global registry instance
tool_registry = ToolRegistry()
