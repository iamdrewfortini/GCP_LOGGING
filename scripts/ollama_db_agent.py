#!/usr/bin/env python3
"""Local Ollama agent with DB tools.

This script runs an Ollama chat loop with tool calling enabled.
The "model" runs locally (Ollama). Database access is done by these local tools.

Notes:
- BigQuery + Firestore require Google auth (ADC). Use GOOGLE_APPLICATION_CREDENTIALS or gcloud auth.
- Redis/Qdrant can be local containers or remote endpoints.

Security defaults:
- BigQuery DDL/DML is blocked unless you run with --allow-writes.
- Write-oriented tools (Firestore writes, Redis writes, Qdrant writes) are only registered when --allow-writes is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# Ensure repo root is on sys.path so `import src.*` works when running from scripts/
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

# Load environment variables from .env file
load_dotenv(REPO_ROOT / ".env")


def _ensure_python_deps() -> None:
  """Fail fast with a clear message if dependencies aren't installed.

  This repo uses a local venv at .venv/ for Python deps.
  """
  try:
    import google.cloud  # noqa: F401
    import firebase_admin  # noqa: F401
    import redis  # noqa: F401
    import qdrant_client  # noqa: F401
  except ModuleNotFoundError as e:
    venv_py = REPO_ROOT / ".venv" / "bin" / "python"
    hint = ""
    if venv_py.exists():
      hint = f"\nTry: {venv_py} scripts/ollama_db_agent.py ...\nOr:  source .venv/bin/activate"
    raise SystemExit(f"Missing Python dependencies for DB tools.{hint}") from e


_ensure_python_deps()

from google.cloud.firestore_v1.base_query import FieldFilter  # type: ignore
from google.cloud import bigquery  # type: ignore
from qdrant_client.http import models  # type: ignore

from src.agent.tools.bq import get_client as get_bq_client
from src.agent.tools.bq import run_bq_query
from src.agent.tools.contracts import BQQueryInput
from src.services.firebase_service import FirebaseService, _serialize_firestore_doc
from src.services.qdrant_service import qdrant_service
from src.services.redis_service import redis_service


def _ollama_host() -> str:
  host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
  return host.rstrip("/")


def _ollama_chat(model: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
  url = f"{_ollama_host()}/api/chat"
  payload: Dict[str, Any] = {
    "model": model,
    "messages": messages,
    "stream": False,
  }
  if tools:
    payload["tools"] = tools

  with httpx.Client(timeout=60.0) as client:
    resp = client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def _ollama_embed(text: str, embed_model: str) -> List[float]:
  url = f"{_ollama_host()}/api/embed"
  payload = {"model": embed_model, "input": text}
  with httpx.Client(timeout=60.0) as client:
    resp = client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()

  embeddings = data.get("embeddings")
  if not embeddings or not isinstance(embeddings, list) or not embeddings[0]:
    raise ValueError("No embeddings returned from Ollama")

  return embeddings[0]


# -----------------------------
# Tool implementations
# -----------------------------

# Set by run_agent() at runtime.
ALLOW_WRITES = False

_BQ_WRITE_RE = re.compile(r"\b(insert|update|delete|merge|create|drop|alter|truncate|grant|revoke)\b", re.IGNORECASE)


def _bq_build_query_params(params: Optional[Dict[str, Any]]) -> List[bigquery.ScalarQueryParameter]:
  if not params:
    return []
  out: List[bigquery.ScalarQueryParameter] = []
  for k, v in params.items():
    if isinstance(v, bool):
      out.append(bigquery.ScalarQueryParameter(k, "BOOL", v))
    elif isinstance(v, int):
      out.append(bigquery.ScalarQueryParameter(k, "INT64", v))
    elif isinstance(v, float):
      out.append(bigquery.ScalarQueryParameter(k, "FLOAT64", v))
    else:
      out.append(bigquery.ScalarQueryParameter(k, "STRING", str(v)))
  return out


def bq_query(sql: str, params: Optional[Dict[str, Any]] = None, max_rows: int = 50) -> Dict[str, Any]:
  """Run a BigQuery query.

  - For SELECT/WITH queries: uses the repo's safe dry-run gate.
  - For DDL/DML: allowed only when running with --allow-writes.
  """
  if _BQ_WRITE_RE.search(sql or ""):
    if not ALLOW_WRITES:
      return {"error": "BigQuery write/DDL requested but writes are disabled. Re-run with --allow-writes."}

    try:
      job_config = bigquery.QueryJobConfig(query_parameters=_bq_build_query_params(params))
      job = get_bq_client().query(sql, job_config=job_config)
      job.result()  # wait
      return {
        "job_id": job.job_id,
        "state": job.state,
        "total_bytes_processed": int(job.total_bytes_processed or 0),
        "num_dml_affected_rows": int(getattr(job, "num_dml_affected_rows", 0) or 0),
        "ddl_operation_performed": getattr(job, "ddl_operation_performed", None),
        "ddl_target_table": str(getattr(job, "ddl_target_table", "") or "") or None,
      }
    except Exception as e:
      return {"error": str(e)}

  try:
    out = run_bq_query(BQQueryInput(sql=sql, params=params, max_rows=max_rows))
    # Keep output bounded.
    rows = out.rows[:max_rows]
    return {
      "job_id": out.job_id,
      "rows": rows,
      "total_bytes_processed": out.total_bytes_processed,
      "cache_hit": out.cache_hit,
      "rows_returned": len(rows),
    }
  except Exception as e:
    return {"error": str(e)}


_fire = FirebaseService()


def _coerce_json_object(value: Any, *, field_name: str) -> Dict[str, Any]:
  if value is None:
    return {}
  if isinstance(value, dict):
    return value
  if isinstance(value, str):
    s = value.strip()
    if not s:
      return {}
    try:
      parsed = json.loads(s)
    except json.JSONDecodeError as e:
      raise ValueError(f"{field_name} must be an object or a JSON object string") from e
    if isinstance(parsed, dict):
      return parsed
  raise ValueError(f"{field_name} must be an object or a JSON object string")


def _normalize_firestore_doc_path(doc_path: str) -> str:
  # Firestore document paths must have an EVEN number of segments: collection/doc[/collection/doc...]
  p = (doc_path or "").strip().strip("/")
  parts = [seg for seg in p.split("/") if seg]
  if not parts:
    raise ValueError("doc_path is required")
  if len(parts) % 2 != 0:
    raise ValueError(
      "Invalid doc_path. Document paths must have an even number of segments like 'collection/doc' (no leading '/')."
    )
  return "/".join(parts)


def _normalize_firestore_collection_path(collection: str) -> str:
  # Firestore collection paths must have an ODD number of segments: collection[/doc/collection...]
  p = (collection or "").strip().strip("/")
  parts = [seg for seg in p.split("/") if seg]
  if not parts:
    raise ValueError("collection is required")
  if len(parts) % 2 == 0:
    raise ValueError(
      "Invalid collection path. Collection paths must have an odd number of segments like 'collection' or 'doc/collection' (no leading '/')."
    )
  return "/".join(parts)


def firestore_get(doc_path: str) -> Dict[str, Any]:
  """Fetch a Firestore document by path, e.g. "sessions/<id>"."""
  try:
    doc_path_norm = _normalize_firestore_doc_path(doc_path)
    doc = _fire.db.document(doc_path_norm).get()
    if not doc.exists:
      return {"found": False, "path": doc_path_norm}
    return {
      "found": True,
      "path": doc_path_norm,
      "id": doc.id,
      "data": _serialize_firestore_doc(doc.to_dict() or {}),
    }
  except Exception as e:
    return {"error": str(e)}


def firestore_query(
  collection: str,
  filters: Optional[List[Dict[str, Any]]] = None,
  limit: int = 20,
) -> Dict[str, Any]:
  """Query a Firestore collection with simple filters.

  filters format: [{"field": "userId", "op": "==", "value": "abc"}, ...]
  """
  try:
    collection_norm = _normalize_firestore_collection_path(collection)
    q = _fire.db.collection(collection_norm)
    for f in (filters or []):
      field = f.get("field")
      op = f.get("op")
      value = f.get("value")
      if not field or not op:
        continue
      q = q.where(filter=FieldFilter(field, op, value))

    q = q.limit(limit)
    docs = []
    for d in q.stream():
      docs.append(_serialize_firestore_doc(d.to_dict() or {}) | {"id": d.id})

    return {"collection": collection_norm, "count": len(docs), "docs": docs}
  except Exception as e:
    return {"error": str(e)}


def firestore_set(doc_path: str, data: Any, merge: bool = False) -> Dict[str, Any]:
  """Create/replace a document at doc_path. Use merge=true to merge fields."""
  if not ALLOW_WRITES:
    return {"error": "Firestore write requested but writes are disabled. Re-run with --allow-writes."}

  try:
    doc_path_norm = _normalize_firestore_doc_path(doc_path)
    data_obj = _coerce_json_object(data, field_name="data")
    _fire.db.document(doc_path_norm).set(data_obj, merge=merge)
    return {"status": "ok", "path": doc_path_norm, "merge": merge}
  except Exception as e:
    return {"error": str(e)}


def firestore_update(doc_path: str, updates: Any) -> Dict[str, Any]:
  """Update fields of an existing document."""
  if not ALLOW_WRITES:
    return {"error": "Firestore write requested but writes are disabled. Re-run with --allow-writes."}

  try:
    doc_path_norm = _normalize_firestore_doc_path(doc_path)
    updates_obj = _coerce_json_object(updates, field_name="updates")
    _fire.db.document(doc_path_norm).update(updates_obj)
    return {"status": "ok", "path": doc_path_norm, "updated_fields": list(updates_obj.keys())}
  except Exception as e:
    return {"error": str(e)}


def firestore_delete(doc_path: str) -> Dict[str, Any]:
  """Delete a document."""
  if not ALLOW_WRITES:
    return {"error": "Firestore write requested but writes are disabled. Re-run with --allow-writes."}

  try:
    doc_path_norm = _normalize_firestore_doc_path(doc_path)
    _fire.db.document(doc_path_norm).delete()
    return {"status": "ok", "path": doc_path_norm}
  except Exception as e:
    return {"error": str(e)}


def firestore_add(collection: str, data: Any) -> Dict[str, Any]:
  """Add a new document with an auto ID to a collection."""
  if not ALLOW_WRITES:
    return {"error": "Firestore write requested but writes are disabled. Re-run with --allow-writes."}

  try:
    collection_norm = _normalize_firestore_collection_path(collection)
    data_obj = _coerce_json_object(data, field_name="data")
    ref = _fire.db.collection(collection_norm).document()
    ref.set(data_obj)
    return {"status": "ok", "collection": collection_norm, "id": ref.id, "path": ref.path}
  except Exception as e:
    return {"error": str(e)}


def redis_ping() -> Dict[str, Any]:
  """Check Redis connectivity."""
  try:
    return {"ping": bool(redis_service.ping())}
  except Exception as e:
    return {"error": str(e)}


def redis_type(key: str) -> Dict[str, Any]:
  """Return Redis key type (string, list, hash, set, zset, none)."""
  try:
    if not redis_service.client:
      return {"error": "Redis client not available. Check REDIS_HOST/REDIS_PORT and that Redis is running."}
    t = redis_service.client.type(key)
    return {"key": key, "type": t}
  except Exception as e:
    return {"error": str(e)}


def redis_get_raw(key: str) -> Dict[str, Any]:
  """Get a raw string value from Redis (GET)."""
  try:
    if not redis_service.client:
      return {"error": "Redis client not available. Check REDIS_HOST/REDIS_PORT and that Redis is running."}
    val = redis_service.client.get(key)
    return {"key": key, "value": val}
  except Exception as e:
    return {"error": str(e)}


def redis_list_range(key: str, start: int = 0, stop: int = 9) -> Dict[str, Any]:
  """Read a range from a Redis list (LRANGE). Useful for queue inspection."""
  try:
    if not redis_service.client:
      return {"error": "Redis client not available. Check REDIS_HOST/REDIS_PORT and that Redis is running."}
    items = redis_service.client.lrange(key, start, stop)
    return {"key": key, "start": start, "stop": stop, "items": items, "count": len(items)}
  except Exception as e:
    return {"error": str(e)}


def redis_scan(pattern: str = "*", limit: int = 50) -> Dict[str, Any]:
  """Scan Redis keys by pattern (SCAN)."""
  try:
    if not redis_service.client:
      return {"error": "Redis client not available. Check REDIS_HOST/REDIS_PORT and that Redis is running."}
    keys: List[str] = []
    for k in redis_service.client.scan_iter(match=pattern, count=min(limit, 1000)):
      keys.append(k)
      if len(keys) >= limit:
        break
    return {"pattern": pattern, "count": len(keys), "keys": keys}
  except Exception as e:
    return {"error": str(e)}


def redis_get_cache(key: str) -> Dict[str, Any]:
  """Get a JSON value from Redis cache (GET + JSON decode)."""
  try:
    val = redis_service.get_cache(key)
    return {"key": key, "value": val}
  except Exception as e:
    return {"error": str(e)}


def redis_set_cache(key: str, value: Any, ttl: int = 3600) -> Dict[str, Any]:
  """Set a JSON value in Redis cache with TTL (seconds)."""
  try:
    redis_service.set_cache(key, value, ttl=ttl)
    return {"status": "ok", "key": key, "ttl": ttl}
  except Exception as e:
    return {"error": str(e)}


def qdrant_list_collections() -> Dict[str, Any]:
  """List Qdrant collections."""
  try:
    cols = qdrant_service.get_collections()
    return {"collections": [c.name for c in cols]}
  except Exception as e:
    return {"error": str(e)}


def qdrant_create_collection(collection: str, vector_size: int, distance: str = "COSINE") -> Dict[str, Any]:
  """Create a Qdrant collection."""
  if not qdrant_service.client:
    return {"error": "Qdrant client not available. Check QDRANT_URL/QDRANT_API_KEY and that Qdrant is running."}

  if not ALLOW_WRITES:
    return {"error": "Qdrant create_collection requested but writes are disabled. Re-run with --allow-writes."}

  try:
    dist = distance.upper()
    if dist == "COSINE":
      d = models.Distance.COSINE
    elif dist in ("DOT", "DOTPRODUCT", "DOT_PRODUCT"):
      d = models.Distance.DOT
    elif dist in ("EUCLID", "EUCLIDEAN"):
      d = models.Distance.EUCLID
    else:
      return {"error": f"Unsupported distance: {distance}. Use COSINE|DOT|EUCLID."}

    qdrant_service.client.create_collection(
      collection_name=collection,
      vectors_config=models.VectorParams(size=vector_size, distance=d),
    )
    return {"status": "ok", "collection": collection, "vector_size": vector_size, "distance": dist}
  except Exception as e:
    return {"error": str(e)}


def qdrant_upsert_text(
  collection: str,
  text: str,
  payload: Optional[Dict[str, Any]] = None,
  id: Optional[str] = None,
  embed_model: Optional[str] = None,
) -> Dict[str, Any]:
  """Embed text locally (Ollama) and upsert into Qdrant."""
  if not qdrant_service.client:
    return {"error": "Qdrant client not available. Check QDRANT_URL/QDRANT_API_KEY and that Qdrant is running."}

  if not ALLOW_WRITES:
    return {"error": "Qdrant upsert requested but writes are disabled. Re-run with --allow-writes."}

  if not text or not text.strip():
    return {"error": "text is required"}

  try:
    em = embed_model or os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    vec = _ollama_embed(text, em)

    # Best-effort dimension check
    try:
      info = qdrant_service.client.get_collection(collection)
      expected = info.config.params.vectors.size  # type: ignore[attr-defined]
      if expected and len(vec) != expected:
        return {"error": f"Embedding dim mismatch: got {len(vec)} but collection expects {expected}."}
    except Exception:
      pass

    point_id = id or str(__import__("uuid").uuid4())
    qdrant_service.client.upsert(
      collection_name=collection,
      points=[models.PointStruct(id=point_id, vector=vec, payload=payload or {})],
    )

    return {"status": "ok", "collection": collection, "id": point_id, "embed_model": em}
  except Exception as e:
    return {"error": str(e)}


def qdrant_delete_points(collection: str, ids: List[str]) -> Dict[str, Any]:
  """Delete points from a Qdrant collection by ID."""
  if not qdrant_service.client:
    return {"error": "Qdrant client not available. Check QDRANT_URL/QDRANT_API_KEY and that Qdrant is running."}

  if not ALLOW_WRITES:
    return {"error": "Qdrant delete requested but writes are disabled. Re-run with --allow-writes."}

  try:
    qdrant_service.client.delete(
      collection_name=collection,
      points_selector=models.PointIdsList(points=ids),
    )
    return {"status": "ok", "collection": collection, "deleted": len(ids)}
  except Exception as e:
    return {"error": str(e)}


def qdrant_scroll(collection: str, must: Optional[Dict[str, Any]] = None, limit: int = 20) -> Dict[str, Any]:
  """Scroll points from a Qdrant collection with optional exact-match filters."""
  if not qdrant_service.client:
    return {"error": "Qdrant client not available. Check QDRANT_URL/QDRANT_API_KEY and that Qdrant is running."}

  try:
    must_conditions = []
    for k, v in (must or {}).items():
      must_conditions.append(models.FieldCondition(key=str(k), match=models.MatchValue(value=v)))

    scroll_filter = models.Filter(must=must_conditions) if must_conditions else None

    points, next_page = qdrant_service.client.scroll(
      collection_name=collection,
      scroll_filter=scroll_filter,
      limit=limit,
      with_payload=True,
      with_vectors=False,
    )

    out_points = []
    for p in points:
      out_points.append({"id": p.id, "payload": p.payload})

    return {"collection": collection, "count": len(out_points), "points": out_points, "next_page": next_page}
  except Exception as e:
    return {"error": str(e)}


def qdrant_search(
  collection: str,
  query_text: str,
  limit: int = 5,
  must: Optional[Dict[str, Any]] = None,
  embed_model: Optional[str] = None,
) -> Dict[str, Any]:
  """Vector search Qdrant using an embedding generated locally via Ollama.

  IMPORTANT: For good results, your Qdrant collection must contain embeddings created by the same embedding model.
  """
  if not qdrant_service.client:
    return {"error": "Qdrant client not available. Check QDRANT_URL/QDRANT_API_KEY and that Qdrant is running."}

  try:
    em = embed_model or os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    vec = _ollama_embed(query_text, em)

    # Try to validate expected vector size.
    try:
      info = qdrant_service.client.get_collection(collection)
      expected = info.config.params.vectors.size  # type: ignore[attr-defined]
      if expected and len(vec) != expected:
        return {"error": f"Embedding dim mismatch: got {len(vec)} but collection expects {expected}."}
    except Exception:
      pass

    must_conditions = []
    for k, v in (must or {}).items():
      must_conditions.append(models.FieldCondition(key=str(k), match=models.MatchValue(value=v)))

    q_filter = models.Filter(must=must_conditions) if must_conditions else None

    hits = qdrant_service.client.search(
      collection_name=collection,
      query_vector=vec,
      query_filter=q_filter,
      limit=limit,
      with_payload=True,
      with_vectors=False,
    )

    results = []
    for h in hits:
      results.append({"id": h.id, "score": h.score, "payload": h.payload})

    return {"collection": collection, "count": len(results), "results": results, "embed_model": em}
  except Exception as e:
    return {"error": str(e)}


# -----------------------------
# Tool schemas (JSON Schema)
# -----------------------------

def _tool_schema(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
  return {
    "type": "function",
    "function": {
      "name": name,
      "description": description,
      "parameters": parameters,
    },
  }


def build_tools(allow_writes: bool) -> List[Dict[str, Any]]:
  tools: List[Dict[str, Any]] = []

  tools.append(
    _tool_schema(
      "bq_query",
      "Run a BigQuery query (read-only by default).",
      {
        "type": "object",
        "required": ["sql"],
        "properties": {
          "sql": {"type": "string", "description": "SQL to execute. Prefer SELECT/WITH and include LIMIT."},
          "params": {"type": "object", "description": "Optional named parameters (key/value)."},
          "max_rows": {"type": "integer", "description": "Max rows to return.", "default": 50},
        },
      },
    )
  )

  tools.append(
    _tool_schema(
      "firestore_get",
      "Fetch a Firestore document by path (e.g. sessions/<id>).",
      {
        "type": "object",
        "required": ["doc_path"],
        "properties": {
          "doc_path": {"type": "string"},
        },
      },
    )
  )

  tools.append(
    _tool_schema(
      "firestore_query",
      "Query a Firestore collection with simple filters.",
      {
        "type": "object",
        "required": ["collection"],
        "properties": {
          "collection": {"type": "string"},
          "filters": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "field": {"type": "string"},
                "op": {"type": "string", "description": "Firestore operator, e.g. ==, >=, <=, in"},
                "value": {},
              },
            },
          },
          "limit": {"type": "integer", "default": 20},
        },
      },
    )
  )

  if allow_writes:
    tools.append(
      _tool_schema(
        "firestore_set",
        "Create/replace a Firestore document at doc_path.",
        {
          "type": "object",
          "required": ["doc_path", "data"],
          "properties": {
            "doc_path": {"type": "string"},
            "data": {"type": "object"},
            "merge": {"type": "boolean", "default": False},
          },
        },
      )
    )

    tools.append(
      _tool_schema(
        "firestore_update",
        "Update fields of an existing Firestore document.",
        {
          "type": "object",
          "required": ["doc_path", "updates"],
          "properties": {
            "doc_path": {"type": "string"},
            "updates": {"type": "object"},
          },
        },
      )
    )

    tools.append(
      _tool_schema(
        "firestore_delete",
        "Delete a Firestore document.",
        {
          "type": "object",
          "required": ["doc_path"],
          "properties": {
            "doc_path": {"type": "string"},
          },
        },
      )
    )

    tools.append(
      _tool_schema(
        "firestore_add",
        "Add a new Firestore document with an auto ID to a collection.",
        {
          "type": "object",
          "required": ["collection", "data"],
          "properties": {
            "collection": {"type": "string"},
            "data": {"type": "object"},
          },
        },
      )
    )

  tools.append(
    _tool_schema(
      "redis_ping",
      "Check Redis connectivity.",
      {"type": "object", "properties": {}},
    )
  )

  tools.append(
    _tool_schema(
      "redis_scan",
      "Scan Redis keys by pattern (SCAN).",
      {
        "type": "object",
        "properties": {
          "pattern": {"type": "string", "default": "*"},
          "limit": {"type": "integer", "default": 50},
        },
      },
    )
  )

  tools.append(
    _tool_schema(
      "redis_type",
      "Get the type of a Redis key (string, list, hash, set, zset, none).",
      {
        "type": "object",
        "required": ["key"],
        "properties": {
          "key": {"type": "string"},
        },
      },
    )
  )

  tools.append(
    _tool_schema(
      "redis_get_raw",
      "Get a raw string value from Redis (GET).",
      {
        "type": "object",
        "required": ["key"],
        "properties": {
          "key": {"type": "string"},
        },
      },
    )
  )

  tools.append(
    _tool_schema(
      "redis_list_range",
      "Read a range from a Redis list (LRANGE).",
      {
        "type": "object",
        "required": ["key"],
        "properties": {
          "key": {"type": "string"},
          "start": {"type": "integer", "default": 0},
          "stop": {"type": "integer", "default": 9},
        },
      },
    )
  )

  tools.append(
    _tool_schema(
      "redis_get_cache",
      "Get a JSON value from Redis cache (GET + JSON decode).",
      {
        "type": "object",
        "required": ["key"],
        "properties": {
          "key": {"type": "string"},
        },
      },
    )
  )

  if allow_writes:
    tools.append(
      _tool_schema(
        "redis_set_cache",
        "Set a JSON value in Redis cache (write).",
        {
          "type": "object",
          "required": ["key", "value"],
          "properties": {
            "key": {"type": "string"},
            "value": {},
            "ttl": {"type": "integer", "default": 3600},
          },
        },
      )
    )

  tools.append(
    _tool_schema(
      "qdrant_list_collections",
      "List Qdrant collections.",
      {"type": "object", "properties": {}},
    )
  )

  if allow_writes:
    tools.append(
      _tool_schema(
        "qdrant_create_collection",
        "Create a Qdrant collection.",
        {
          "type": "object",
          "required": ["collection", "vector_size"],
          "properties": {
            "collection": {"type": "string"},
            "vector_size": {"type": "integer"},
            "distance": {"type": "string", "default": "COSINE"},
          },
        },
      )
    )

    tools.append(
      _tool_schema(
        "qdrant_upsert_text",
        "Embed text locally (Ollama) and upsert into Qdrant.",
        {
          "type": "object",
          "required": ["collection", "text"],
          "properties": {
            "collection": {"type": "string"},
            "text": {"type": "string"},
            "payload": {"type": "object"},
            "id": {"type": "string", "description": "Optional point id. If omitted, a UUID is generated."},
            "embed_model": {"type": "string", "description": "Embedding model name in Ollama (default from OLLAMA_EMBED_MODEL)."},
          },
        },
      )
    )

    tools.append(
      _tool_schema(
        "qdrant_delete_points",
        "Delete points from a Qdrant collection by ID.",
        {
          "type": "object",
          "required": ["collection", "ids"],
          "properties": {
            "collection": {"type": "string"},
            "ids": {"type": "array", "items": {"type": "string"}},
          },
        },
      )
    )

  tools.append(
    _tool_schema(
      "qdrant_scroll",
      "Scroll points from a Qdrant collection with optional exact-match filters.",
      {
        "type": "object",
        "required": ["collection"],
        "properties": {
          "collection": {"type": "string"},
          "must": {"type": "object", "description": "Exact-match filters (key/value)."},
          "limit": {"type": "integer", "default": 20},
        },
      },
    )
  )

  tools.append(
    _tool_schema(
      "qdrant_search",
      "Vector search Qdrant using an Ollama embedding model.",
      {
        "type": "object",
        "required": ["collection", "query_text"],
        "properties": {
          "collection": {"type": "string"},
          "query_text": {"type": "string"},
          "limit": {"type": "integer", "default": 5},
          "must": {"type": "object", "description": "Exact-match filters (key/value)."},
          "embed_model": {"type": "string", "description": "Embedding model name in Ollama (default from OLLAMA_EMBED_MODEL)."},
        },
      },
    )
  )

  return tools


_TOOL_DISPATCH = {
  "bq_query": bq_query,
  "firestore_get": firestore_get,
  "firestore_query": firestore_query,
  "firestore_set": firestore_set,
  "firestore_update": firestore_update,
  "firestore_delete": firestore_delete,
  "firestore_add": firestore_add,
  "redis_ping": redis_ping,
  "redis_scan": redis_scan,
  "redis_type": redis_type,
  "redis_get_raw": redis_get_raw,
  "redis_list_range": redis_list_range,
  "redis_get_cache": redis_get_cache,
  "redis_set_cache": redis_set_cache,
  "qdrant_list_collections": qdrant_list_collections,
  "qdrant_create_collection": qdrant_create_collection,
  "qdrant_upsert_text": qdrant_upsert_text,
  "qdrant_delete_points": qdrant_delete_points,
  "qdrant_scroll": qdrant_scroll,
  "qdrant_search": qdrant_search,
}


def run_agent(model: str, prompt: str, allow_writes: bool, max_steps: int) -> str:
  global ALLOW_WRITES
  ALLOW_WRITES = allow_writes

  tools = build_tools(allow_writes=allow_writes)
  messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]

  for _ in range(max_steps):
    resp = _ollama_chat(model=model, messages=messages, tools=tools)
    msg = resp.get("message") or {}

    # append assistant message (may contain tool_calls)
    assistant_msg: Dict[str, Any] = {"role": "assistant"}
    if "content" in msg:
      assistant_msg["content"] = msg.get("content")
    if "tool_calls" in msg:
      assistant_msg["tool_calls"] = msg.get("tool_calls")
    messages.append(assistant_msg)

    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
      return (msg.get("content") or "").strip()

    for tc in tool_calls:
      fn = (tc.get("function") or {})
      name = fn.get("name")
      args = fn.get("arguments") or {}
      if name not in _TOOL_DISPATCH:
        tool_out = {"error": f"Unknown tool: {name}"}
      else:
        try:
          tool_out = _TOOL_DISPATCH[name](**args)
        except TypeError as e:
          tool_out = {"error": f"Bad arguments for {name}: {e}", "args": args}
        except Exception as e:
          tool_out = {"error": str(e)}

      messages.append({"role": "tool", "tool_name": name, "content": json.dumps(tool_out)})

  return "Stopped: max tool-calling steps reached. Try narrowing the request or increasing --max-steps."


def main() -> None:
  parser = argparse.ArgumentParser(description="Run a local Ollama DB agent.")
  parser.add_argument("prompt", nargs="?", help="Prompt/question for the agent. If omitted, reads from stdin.")
  parser.add_argument("--model", default="gcp-db-agent", help="Ollama model name to use.")
  parser.add_argument("--allow-writes", action="store_true", help="Register write-capable tools (e.g., redis_set_cache).")
  parser.add_argument("--max-steps", type=int, default=8, help="Max tool-calling loop steps.")
  args = parser.parse_args()

  prompt = args.prompt
  if not prompt:
    prompt = sys.stdin.read().strip()

  if not prompt:
    print("No prompt provided.", file=sys.stderr)
    raise SystemExit(2)

  out = run_agent(model=args.model, prompt=prompt, allow_writes=args.allow_writes, max_steps=args.max_steps)
  print(out)


if __name__ == "__main__":
  main()
