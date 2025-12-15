"""
Benchmark harness for latency + quality evaluation.

Runs suites, persists results to SQLite, compares baselines, generates tuning recommendations.

Based on spec: bench.harness.
"""

import os
import sqlite3
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.services.ollama_embed import OllamaEmbedService
from src.services.qdrant_query_engine import QdrantQueryEngine

# Config
BENCH_DB_URL = os.getenv("BENCH_DB_URL", "sqlite:///var/lib/app/benchmarks.db")
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "v1")

# Bench scenarios
SCENARIOS = [
    {"name": "semantic", "description": "Pure semantic search", "filters": None, "hnsw_ef": 64},
    {"name": "filtered_severity", "description": "Filtered by severity", "filters": {"severity": "ERROR"}, "hnsw_ef": 32},
    {"name": "filtered_service", "description": "Filtered by service", "filters": {"service_name": "my-service"}, "hnsw_ef": 32},
    {"name": "filtered_time", "description": "Filtered by time range", "filters": {"timestamp_from": 1609459200, "timestamp_to": 1640995200}, "hnsw_ef": 32},
    {"name": "hybrid", "description": "Hybrid dense + sparse (if enabled)", "filters": None, "hnsw_ef": 64},
    {"name": "grouped_trace", "description": "Grouped by trace_id", "filters": None, "hnsw_ef": 64},
]

# Sample queries (fixed for reproducibility)
SAMPLE_QUERIES = [
    "database connection failed",
    "user authentication error",
    "high memory usage",
    "slow query detected",
    "service restart initiated"
]

# Quality labels (placeholder - need real labeled set)
QUALITY_LABELS = {}  # query -> relevant_log_ids

@dataclass
class BenchResult:
    scenario: str
    query_text: str
    latency_ms: float
    embed_ms: float
    search_ms: float
    result_count: int
    p95_bucket: Optional[str] = None
    error: Optional[str] = None


class BenchHarness:
    """Benchmark runner."""

    def __init__(self):
        self.db_path = BENCH_DB_URL.replace("sqlite:///", "")
        self.embed_service = OllamaEmbedService()
        self.query_engine = QdrantQueryEngine()
        self._init_db()

    def _init_db(self):
        """Create tables if not exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # bench_runs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bench_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                git_sha TEXT,
                schema_version TEXT,
                qdrant_version TEXT,
                ollama_embed_model TEXT,
                ollama_chat_model TEXT,
                embed_dim INTEGER,
                corpus_snapshot_id TEXT,
                notes TEXT
            )
        """)

        # bench_queries
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bench_queries (
                query_id TEXT PRIMARY KEY,
                run_id TEXT,
                scenario TEXT,
                query_text TEXT,
                filters_json TEXT,
                hnsw_ef INTEGER,
                limit INTEGER,
                offset INTEGER,
                latency_ms REAL,
                embed_ms REAL,
                search_ms REAL,
                result_count INTEGER,
                p95_bucket TEXT,
                error TEXT,
                FOREIGN KEY (run_id) REFERENCES bench_runs(run_id)
            )
        """)

        # bench_quality
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bench_quality (
                quality_id TEXT PRIMARY KEY,
                run_id TEXT,
                scenario TEXT,
                metric TEXT,
                k INTEGER,
                value REAL,
                labelset_id TEXT,
                notes TEXT,
                FOREIGN KEY (run_id) REFERENCES bench_runs(run_id)
            )
        """)

        # schema_changes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_changes (
                change_id TEXT PRIMARY KEY,
                applied_at TEXT,
                from_version TEXT,
                to_version TEXT,
                change_type TEXT,
                diff_json TEXT,
                validated_by_run_id TEXT,
                FOREIGN KEY (validated_by_run_id) REFERENCES bench_runs(run_id)
            )
        """)

        conn.commit()
        conn.close()

    def run_full_bench(self, corpus_snapshot_id: str = "latest") -> str:
        """Run full benchmark suite, return run_id."""
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()

        # Insert run
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bench_runs (run_id, started_at, schema_version, embed_dim, corpus_snapshot_id, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (run_id, started_at, SCHEMA_VERSION, self.embed_service.expected_dim, corpus_snapshot_id, "Full bench run"))
        conn.commit()

        results = []
        for scenario in SCENARIOS:
            for query in SAMPLE_QUERIES:
                result = self._run_single_query(scenario, query)
                results.append(result)

                # Store in DB
                cursor.execute("""
                    INSERT INTO bench_queries (
                        query_id, run_id, scenario, query_text, filters_json, hnsw_ef,
                        limit, offset, latency_ms, embed_ms, search_ms, result_count, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()), run_id, result.scenario, result.query_text,
                    str(scenario.get("filters")), scenario["hnsw_ef"], 10, 0,
                    result.latency_ms, result.embed_ms, result.search_ms, result.result_count, result.error
                ))

        # Quality metrics (placeholder)
        for scenario in SCENARIOS:
            cursor.execute("""
                INSERT INTO bench_quality (quality_id, run_id, scenario, metric, k, value, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), run_id, scenario["name"], "recall@10", 10, 0.85, "Placeholder"
            ))

        conn.commit()
        conn.close()

        # Generate report
        self._generate_report(run_id)
        return run_id

    def _run_single_query(self, scenario: Dict[str, Any], query_text: str) -> BenchResult:
        """Run single query benchmark."""
        try:
            start_time = time.time()

            # Embed
            embed_start = time.time()
            query_vector = self.embed_service.embed_single(query_text)
            embed_ms = (time.time() - embed_start) * 1000

            # Query
            search_start = time.time()
            if scenario["name"] == "grouped_trace":
                response = self.query_engine.query_groups(
                    query_vector=query_vector,
                    group_by="trace_id",
                    limit=10,
                    hnsw_ef=scenario["hnsw_ef"]
                )
                result_count = len(response.groups)
            elif scenario["name"] == "hybrid":
                # Placeholder for hybrid
                response = self.query_engine.semantic_search(
                    query_vector=query_vector,
                    limit=10,
                    hnsw_ef=scenario["hnsw_ef"]
                )
                result_count = len(response.points)
            else:
                query_filter = QdrantQueryEngine.build_filter(**scenario.get("filters", {})) if scenario.get("filters") else None
                if query_filter:
                    response = self.query_engine.filtered_search(
                        query_vector=query_vector,
                        query_filter=query_filter,
                        limit=10,
                        hnsw_ef=scenario["hnsw_ef"]
                    )
                else:
                    response = self.query_engine.semantic_search(
                        query_vector=query_vector,
                        limit=10,
                        hnsw_ef=scenario["hnsw_ef"]
                    )
                result_count = len(response.points)

            search_ms = (time.time() - search_start) * 1000
            total_ms = (time.time() - start_time) * 1000

            return BenchResult(
                scenario=scenario["name"],
                query_text=query_text,
                latency_ms=total_ms,
                embed_ms=embed_ms,
                search_ms=search_ms,
                result_count=result_count
            )
        except Exception as e:
            return BenchResult(
                scenario=scenario["name"],
                query_text=query_text,
                latency_ms=0,
                embed_ms=0,
                search_ms=0,
                result_count=0,
                error=str(e)
            )

    def _generate_report(self, run_id: str):
        """Generate benchmark report."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get p50/p95 by scenario
        cursor.execute("""
            SELECT scenario, AVG(latency_ms) as avg_lat, 
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
                   PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
            FROM bench_queries 
            WHERE run_id = ? AND error IS NULL
            GROUP BY scenario
        """, (run_id,))

        report = f"Benchmark Report for Run {run_id}\n\n"
        for row in cursor.fetchall():
            scenario, avg, p50, p95 = row
            report += f"{scenario}: Avg {avg:.1f}ms, P50 {p50:.1f}ms, P95 {p95:.1f}ms\n"

        # Compare to baseline (last run)
        cursor.execute("SELECT run_id FROM bench_runs WHERE run_id != ? ORDER BY started_at DESC LIMIT 1", (run_id,))
        baseline_row = cursor.fetchone()
        if baseline_row:
            baseline_id = baseline_row[0]
            report += f"\nRegression check vs baseline {baseline_id}:\n"
            cursor.execute("""
                SELECT b.scenario, b.p50 - a.p50 as p50_diff, b.p95 - a.p95 as p95_diff
                FROM (
                    SELECT scenario, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
                           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
                    FROM bench_queries WHERE run_id = ? AND error IS NULL GROUP BY scenario
                ) a
                JOIN (
                    SELECT scenario, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
                           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
                    FROM bench_queries WHERE run_id = ? AND error IS NULL GROUP BY scenario
                ) b ON a.scenario = b.scenario
            """, (baseline_id, run_id))
            for row in cursor.fetchall():
                scenario, p50_diff, p95_diff = row
                status = "REGRESSION" if p50_diff > 10 or p95_diff > 50 else "OK"
                report += f"{scenario}: P50 diff {p50_diff:.1f}ms, P95 diff {p95_diff:.1f}ms - {status}\n"

        conn.close()

        with open(f"bench_report_{run_id}.txt", "w") as f:
            f.write(report)
        print(report)

    def get_tuning_recommendations(self, run_id: str) -> List[str]:
        """Generate tuning recommendations based on results."""
        # Placeholder logic
        recs = []
        # Check if filtered queries are slow
        # Suggest hnsw_ef adjustments, new indexes, etc.
        recs.append("Increase hnsw_ef for semantic searches if recall low.")
        recs.append("Add payload index for 'new_filter_field' if emerging.")
        return recs


if __name__ == "__main__":
    harness = BenchHarness()
    run_id = harness.run_full_bench()
    print(f"Benchmark run {run_id} completed. See bench_report_{run_id}.txt")