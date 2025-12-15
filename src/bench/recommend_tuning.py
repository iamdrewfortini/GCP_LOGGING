"""
Generate tuning recommendations from benchmark results.

Based on spec: bench.harness tuning recommendations.
"""

import os
import sqlite3
from typing import List, Dict, Any
from src.bench.run_benchmarks import BenchHarness


class TuningRecommender:
    """Analyze bench results and recommend changes."""

    def __init__(self):
        self.harness = BenchHarness()

    def recommend_for_run(self, run_id: str) -> Dict[str, Any]:
        """Generate recommendations for a bench run."""
        conn = sqlite3.connect(self.harness.db_path)
        cursor = conn.cursor()

        recommendations = {
            "hnsw_ef_adjustments": [],
            "new_indexes": [],
            "schema_changes": [],
            "other": []
        }

        # Check latency regressions
        cursor.execute("""
            SELECT scenario, AVG(latency_ms) as avg_lat
            FROM bench_queries 
            WHERE run_id = ? AND error IS NULL
            GROUP BY scenario
        """, (run_id,))
        current_latencies = {row[0]: row[1] for row in cursor.fetchall()}

        # Compare to baseline
        cursor.execute("SELECT run_id FROM bench_runs WHERE run_id != ? ORDER BY started_at DESC LIMIT 1", (run_id,))
        baseline_row = cursor.fetchone()
        if baseline_row:
            baseline_id = baseline_row[0]
            cursor.execute("""
                SELECT scenario, AVG(latency_ms) as avg_lat
                FROM bench_queries 
                WHERE run_id = ? AND error IS NULL
                GROUP BY scenario
            """, (baseline_id,))
            baseline_latencies = {row[0]: row[1] for row in cursor.fetchall()}

            for scenario, current in current_latencies.items():
                baseline = baseline_latencies.get(scenario, current)
                if current > baseline * 1.1:  # 10% regression
                    if "semantic" in scenario:
                        recommendations["hnsw_ef_adjustments"].append(f"Increase hnsw_ef for {scenario} to improve recall.")
                    else:
                        recommendations["new_indexes"].append(f"Add index for filters in {scenario}.")

        # Check quality metrics
        cursor.execute("""
            SELECT scenario, metric, value
            FROM bench_quality 
            WHERE run_id = ?
        """, (run_id,))
        for row in cursor.fetchall():
            scenario, metric, value = row
            if metric == "recall@10" and value < 0.8:
                recommendations["hnsw_ef_adjustments"].append(f"Boost hnsw_ef for {scenario} - recall {value:.2f} < 0.8")

        # Placeholder for other recs
        recommendations["other"].append("Consider OnDisk storage if memory usage high.")
        recommendations["other"].append("Add PQ quantization if vector storage > 50GB.")

        conn.close()
        return recommendations


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python recommend_tuning.py <run_id>")
        sys.exit(1)
    run_id = sys.argv[1]
    recommender = TuningRecommender()
    recs = recommender.recommend_for_run(run_id)
    print(f"Tuning recommendations for run {run_id}:")
    for category, items in recs.items():
        if items:
            print(f"{category}:")
            for item in items:
                print(f"  - {item}")