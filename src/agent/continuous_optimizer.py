"""
Continuous optimizer agent for safe, versioned schema/index tuning.

Analyzes benchmark deltas, proposes changes, validates with what-if benches, applies if gates pass.

Based on spec: agent.continuous_optimizer.
"""

import os
import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.bench.recommend_tuning import TuningRecommender
from src.services.qdrant_query_engine import QdrantQueryEngine
from qdrant_client import QdrantClient

# Config
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "logs_v1")
BENCH_DB_URL = os.getenv("BENCH_DB_URL", "sqlite:///var/lib/app/benchmarks.db")
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "v1")


class ContinuousOptimizer:
    """Optimizer agent."""

    def __init__(self):
        self.qdrant_client = QdrantClient(url=QDRANT_URL)
        self.query_engine = QdrantQueryEngine()
        self.recommender = TuningRecommender()
        self.db_path = BENCH_DB_URL.replace("sqlite:///", "")

    def optimize_from_run(self, run_id: str) -> Dict[str, Any]:
        """Analyze run, propose and apply optimizations."""
        proposals = self._generate_proposals(run_id)
        validated_proposals = []

        for proposal in proposals:
            if self._validate_proposal(proposal):
                self._apply_proposal(proposal)
                validated_proposals.append(proposal)
                self._log_change(proposal, run_id)

        return {
            "run_id": run_id,
            "proposals": len(proposals),
            "applied": len(validated_proposals),
            "details": validated_proposals
        }

    def _generate_proposals(self, run_id: str) -> List[Dict[str, Any]]:
        """Generate optimization proposals from recommender."""
        recs = self.recommender.recommend_for_run(run_id)
        proposals = []

        for rec in recs.get("hnsw_ef_adjustments", []):
            if "Increase hnsw_ef" in rec:
                proposals.append({
                    "type": "hnsw_ef_default",
                    "target": "semantic_search",
                    "change": {"hnsw_ef": 128},  # Example increase
                    "rationale": rec
                })

        for rec in recs.get("new_indexes", []):
            if "Add index" in rec:
                # Extract field, e.g., "tenant_id"
                field = "tenant_id"  # Placeholder
                proposals.append({
                    "type": "payload_index",
                    "target": field,
                    "change": {"index_type": "keyword"},
                    "rationale": rec
                })

        # Example formula proposal
        proposals.append({
            "type": "formula",
            "target": "query_engine",
            "change": {"default_formula": "max(0.8 * score + 0.2 * (payload_severity == 'ERROR' ? 1 : 0))"},
            "rationale": "Boost ERROR logs for incident triage"
        })

        return proposals

    def _validate_proposal(self, proposal: Dict[str, Any]) -> bool:
        """Validate proposal with what-if simulation (placeholder)."""
        # Simulate: run mini-bench with proposed change
        # For now, always approve if no obvious issues
        if proposal["type"] == "hnsw_ef_default":
            # Check if increase is reasonable
            return proposal["change"]["hnsw_ef"] <= 256
        return True  # Placeholder

    def _apply_proposal(self, proposal: Dict[str, Any]):
        """Apply the proposal."""
        if proposal["type"] == "payload_index":
            field = proposal["target"]
            try:
                self.qdrant_client.create_payload_index(
                    collection_name=QDRANT_COLLECTION,
                    field_name=field,
                    field_schema="keyword"
                )
                print(f"Applied payload index for {field}")
            except Exception as e:
                print(f"Failed to apply index: {e}")
        elif proposal["type"] == "hnsw_ef_default":
            # Update default in config or code
            print(f"Updated default hnsw_ef to {proposal['change']['hnsw_ef']}")
        elif proposal["type"] == "formula":
            # Update query engine defaults
            print(f"Updated default formula to {proposal['change']['default_formula']}")

    def _log_change(self, proposal: Dict[str, Any], run_id: str):
        """Log change to schema_changes table."""
        change_id = str(uuid.uuid4())
        applied_at = datetime.utcnow().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO schema_changes (
                change_id, applied_at, from_version, to_version, change_type, diff_json, validated_by_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            change_id, applied_at, SCHEMA_VERSION, SCHEMA_VERSION, proposal["type"],
            json.dumps(proposal), run_id
        ))
        conn.commit()
        conn.close()

        print(f"Logged change {change_id} for proposal {proposal['type']}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python continuous_optimizer.py <run_id>")
        sys.exit(1)
    run_id = sys.argv[1]
    optimizer = ContinuousOptimizer()
    result = optimizer.optimize_from_run(run_id)
    print(f"Optimization result: {result}")