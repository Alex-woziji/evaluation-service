"""
Stress / load test for the Evaluation Service.

Usage:
    # Start the service first
    python main.py

    # Run load test (default: 50 concurrent users, 200 total requests)
    python -m tests.load_test

    # Custom parameters
    python -m tests.load_test --users 100 --requests 500 --ramp-up 5

    # Test only the health endpoint
    python -m tests.load_test --target health

    # Test batch endpoint with multiple metrics
    python -m tests.load_test --target batch

    # Test single metric endpoint
    python -m tests.load_test --target single
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8000/api/v1/evaluation"

# Sample data for faithfulness metric
SAMPLE_TEST_CASES = [
    {
        "response": "Gradient descent is an optimization algorithm used to minimize loss functions.",
        "retrieved_contexts": "Gradient Descent is an optimization algorithm used to minimize a loss function by iteratively moving in the direction of steepest descent.",
        "user_input": "What is gradient descent?",
    },
    {
        "response": "Python is a compiled programming language that runs very fast.",
        "retrieved_contexts": "Python is an interpreted, high-level programming language known for its readability and simplicity.",
        "user_input": "Tell me about Python.",
    },
    {
        "response": "The Eiffel Tower is located in London and was built in 1990.",
        "retrieved_contexts": "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France. It was built from 1887 to 1889.",
        "user_input": "Where is the Eiffel Tower?",
    },
]


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class RequestResult:
    status_code: int
    latency_s: float
    success: bool
    error: Optional[str] = None


@dataclass
class LoadTestReport:
    target: str
    total_requests: int
    concurrency: int
    ramp_up_s: float
    results: list[RequestResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_s(self) -> float:
        return round(self.end_time - self.start_time, 2)

    @property
    def rps(self) -> float:
        return round(self.total_requests / self.duration_s, 2) if self.duration_s > 0 else 0

    def print_report(self) -> None:
        latencies = [r.latency_s for r in self.results]
        successes = [r for r in self.results if r.success]
        failures = [r for r in self.results if not r.success]
        status_codes = {}
        for r in self.results:
            status_codes[r.status_code] = status_codes.get(r.status_code, 0) + 1

        print("\n" + "=" * 70)
        print(f"  LOAD TEST REPORT  —  target: {self.target}")
        print("=" * 70)
        print(f"  Total requests : {self.total_requests}")
        print(f"  Concurrency    : {self.concurrency}")
        print(f"  Ramp-up        : {self.ramp_up_s}s")
        print(f"  Duration       : {self.duration_s}s")
        print(f"  Throughput     : {self.rps} req/s")
        print(f"  Success / Fail : {len(successes)} / {len(failures)}")
        print(f"  Status codes   : {dict(sorted(status_codes.items()))}")
        print("-" * 70)

        if latencies:
            latencies_sorted = sorted(latencies)
            print(f"  Latency (s)    :")
            print(f"    min          : {min(latencies_sorted):.3f}")
            print(f"    avg          : {statistics.mean(latencies_sorted):.3f}")
            print(f"    median       : {statistics.median(latencies_sorted):.3f}")
            print(f"    p90          : {self._percentile(latencies_sorted, 90):.3f}")
            print(f"    p95          : {self._percentile(latencies_sorted, 95):.3f}")
            print(f"    p99          : {self._percentile(latencies_sorted, 99):.3f}")
            print(f"    max          : {max(latencies_sorted):.3f}")

        if failures:
            print("-" * 70)
            print("  Sample errors (first 5):")
            for f in failures[:5]:
                print(f"    [{f.status_code}] {f.error}")

        print("=" * 70 + "\n")

    @staticmethod
    def _percentile(sorted_data: list[float], pct: int) -> float:
        idx = (pct / 100) * (len(sorted_data) - 1)
        lower = int(idx)
        upper = min(lower + 1, len(sorted_data) - 1)
        frac = idx - lower
        return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------

def build_health_request() -> tuple[str, str, None]:
    return "GET", f"{BASE_URL}/health", None


def build_batch_request() -> tuple[str, str, dict]:
    test_case = random.choice(SAMPLE_TEST_CASES)
    payload = {
        "metrics": ["faithfulness"],
        "test_case": test_case,
    }
    return "POST", f"{BASE_URL}/batch", payload


def build_single_request() -> tuple[str, str, dict]:
    test_case = random.choice(SAMPLE_TEST_CASES)
    return "POST", f"{BASE_URL}/llm_judge/faithfulness", test_case


TARGET_BUILDERS = {
    "health": build_health_request,
    "batch": build_batch_request,
    "single": build_single_request,
}


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

async def _send_request(
    client: httpx.AsyncClient,
    target: str,
    request_id: int,
) -> RequestResult:
    builder = TARGET_BUILDERS[target]
    method, url, payload = builder()

    start = time.monotonic()
    try:
        if method == "GET":
            resp = await client.get(url)
        else:
            resp = await client.post(url, json=payload)
        latency = time.monotonic() - start

        success = 200 <= resp.status_code < 300
        error = None
        if not success:
            try:
                error = json.dumps(resp.json(), ensure_ascii=False)[:200]
            except Exception:
                error = resp.text[:200]

        return RequestResult(
            status_code=resp.status_code,
            latency_s=round(latency, 4),
            success=success,
            error=error,
        )
    except Exception as exc:
        latency = time.monotonic() - start
        return RequestResult(
            status_code=0,
            latency_s=round(latency, 4),
            success=False,
            error=str(exc)[:200],
        )


async def _worker(
    worker_id: int,
    client: httpx.AsyncClient,
    target: str,
    requests_per_worker: int,
    report: LoadTestReport,
    sem: asyncio.Semaphore,
) -> None:
    for i in range(requests_per_worker):
        async with sem:
            result = await _send_request(client, target, worker_id * requests_per_worker + i)
            report.results.append(result)
            # Progress dot
            if len(report.results) % 50 == 0:
                print(f"  ... {len(report.results)}/{report.total_requests} requests completed", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_load_test(
    target: str = "batch",
    total_requests: int = 200,
    concurrency: int = 50,
    ramp_up_s: float = 2.0,
) -> LoadTestReport:
    report = LoadTestReport(
        target=target,
        total_requests=total_requests,
        concurrency=concurrency,
        ramp_up_s=ramp_up_s,
    )

    sem = asyncio.Semaphore(concurrency)
    requests_per_worker = max(1, total_requests // concurrency)
    num_workers = (total_requests + requests_per_worker - 1) // requests_per_worker

    print(f"\nStarting load test: target={target}, "
          f"requests={total_requests}, concurrency={concurrency}, "
          f"ramp_up={ramp_up_s}s, workers={num_workers}")
    print(f"Endpoint: {TARGET_BUILDERS[target]()[1]}\n")

    report.start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        # Health check first
        try:
            resp = await client.get(f"{BASE_URL}/health")
            resp.raise_for_status()
            print(f"  Health check passed: {resp.json()}")
        except Exception as e:
            print(f"  Health check FAILED: {e}")
            print("  Make sure the service is running: python main.py")
            return report

        print()

        # Launch workers with ramp-up
        tasks = []
        for wid in range(num_workers):
            t = asyncio.create_task(
                _worker(wid, client, target, requests_per_worker, report, sem)
            )
            tasks.append(t)
            if ramp_up_s > 0 and wid < num_workers - 1:
                await asyncio.sleep(ramp_up_s / num_workers)

        await asyncio.gather(*tasks)

    report.end_time = time.monotonic()
    return report


def main():
    parser = argparse.ArgumentParser(description="Evaluation Service Load Test")
    parser.add_argument(
        "--target", choices=["health", "batch", "single"], default="batch",
        help="Endpoint to test (default: batch)",
    )
    parser.add_argument(
        "--requests", "-n", type=int, default=200,
        help="Total number of requests to send (default: 200)",
    )
    parser.add_argument(
        "--users", "-u", type=int, default=50,
        help="Max concurrent users/connections (default: 50)",
    )
    parser.add_argument(
        "--ramp-up", type=float, default=2.0,
        help="Ramp-up time in seconds to spread worker launch (default: 2.0)",
    )
    args = parser.parse_args()

    report = asyncio.run(run_load_test(
        target=args.target,
        total_requests=args.requests,
        concurrency=args.users,
        ramp_up_s=args.ramp_up,
    ))
    report.print_report()


if __name__ == "__main__":
    main()
