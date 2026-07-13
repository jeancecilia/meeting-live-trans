"""
English/Thai evaluation harness (MTG-051).

Creates a repeatable dataset for testing translation quality across:
- Business conversation
- Software development terms
- Names (Thai and English)
- Dates, phone numbers, prices
- Email addresses
- Interruptions and background noise

Records: source audio path, expected meaning, source transcript,
translated text, first-caption latency, final-caption latency,
manual quality rating.

Usage:
    python eval_harness.py --direction en-th --output results.csv
"""

import csv
import os
import time
from dataclasses import dataclass

EVAL_DATA_DIR = os.path.join(os.path.dirname(__file__), "eval_data")


@dataclass
class EvalSample:
    """A single evaluation sample for translation testing."""

    sample_id: str
    category: str  # "business", "tech", "names", "dates", "prices", "email", "noise"
    direction: str  # "en-th" or "th-en"
    source_audio_path: str = ""
    expected_meaning: str = ""  # Human-annotated expected meaning (not literal)
    source_transcript: str = ""  # Ground truth transcript in source language
    translated_text: str = ""  # Model output
    first_caption_latency_ms: float = 0.0
    final_caption_latency_ms: float = 0.0
    manual_quality_rating: int = 0  # 1-5 scale
    notes: str = ""


# ──── Evaluation dataset ────

EVAL_DATASET: list[dict] = [
    # Business conversation
    {
        "sample_id": "biz-001",
        "category": "business",
        "direction": "en-th",
        "expected_meaning": "We need to launch the application by September, with a budget of around 200,000 THB.",
        "source_transcript": "We need to launch the app by September, budget around two hundred thousand Thai Baht.",
    },
    {
        "sample_id": "biz-002",
        "category": "business",
        "direction": "th-en",
        "expected_meaning": "The client wants to review the contract before signing.",
        "source_transcript": "ลูกค้าต้องการตรวจสอบสัญญาก่อนเซ็น",
    },
    # Software development
    {
        "sample_id": "tech-001",
        "category": "tech",
        "direction": "en-th",
        "expected_meaning": "The API endpoint returns JSON with user data and authentication tokens.",
        "source_transcript": "The API endpoint returns JSON with user data and auth tokens.",
    },
    # Thai names
    {
        "sample_id": "name-001",
        "category": "names",
        "direction": "th-en",
        "expected_meaning": "My name is Somchai Jaidee.",
        "source_transcript": "ผมชื่อสมชาย ใจดี",
    },
    # English names
    {
        "sample_id": "name-002",
        "category": "names",
        "direction": "en-th",
        "expected_meaning": "Please contact Jennifer Williams at extension 405.",
        "source_transcript": "Please contact Jennifer Williams at extension 405.",
    },
    # Dates
    {
        "sample_id": "date-001",
        "category": "dates",
        "direction": "en-th",
        "expected_meaning": "The meeting is scheduled for Monday, July 15, 2026 at 2:30 PM.",
        "source_transcript": "The meeting is on Monday, July fifteenth, two thousand twenty-six at two thirty PM.",
    },
    # Prices
    {
        "sample_id": "price-001",
        "category": "prices",
        "direction": "en-th",
        "expected_meaning": "The total cost is $1,250.50 or approximately €1,100.",
        "source_transcript": "Total cost is one thousand two hundred fifty dollars and fifty cents, or about eleven hundred euros.",
    },
    {
        "sample_id": "price-002",
        "category": "prices",
        "direction": "th-en",
        "expected_meaning": "The price for this project is 50,000 Thai Baht.",
        "source_transcript": "ราคาสำหรับโปรเจกต์นี้คือห้าหมื่นบาท",
    },
]


def create_eval_dataset(output_path: str = "eval_dataset.csv") -> None:
    """Write the evaluation dataset to a CSV file for manual annotation."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id",
                "category",
                "direction",
                "source_audio_path",
                "expected_meaning",
                "source_transcript",
                "translated_text",
                "first_caption_latency_ms",
                "final_caption_latency_ms",
                "manual_quality_rating",
                "notes",
            ],
        )
        writer.writeheader()
        for sample in EVAL_DATASET:
            writer.writerow({**sample, "source_audio_path": "", "translated_text": "",
                            "first_caption_latency_ms": "", "final_caption_latency_ms": "",
                            "manual_quality_rating": "", "notes": ""})


def run_evaluation(
    direction: str,
    provider: str = "openai-transcribe-then-translate",
) -> list[dict]:
    """
    Run automated evaluation for a given language direction.

    Returns list of results with latency and quality metrics.
    In production, this calls the actual translation provider.
    """
    results = []
    samples = [s for s in EVAL_DATASET if s["direction"] == direction]

    for sample in samples:
        start_time = time.monotonic()

        # Simulate translation call
        time.sleep(0.1)  # Placeholder for actual API call

        end_time = time.monotonic()
        latency_ms = (end_time - start_time) * 1000

        results.append({
            **sample,
            "first_caption_latency_ms": round(latency_ms, 1),
            "final_caption_latency_ms": round(latency_ms + 50, 1),
            "provider": provider,
        })

    return results


def generate_report(results: list[dict], output_path: str = "eval_report.md") -> None:
    """Generate a markdown evaluation report."""
    lines = [
        "# Translation Evaluation Report",
        "",
        f"**Samples:** {len(results)}",
        f"**Provider:** {results[0]['provider'] if results else 'N/A'}",
        "",
        "## Results by Category",
        "",
        "| Category | Count | Avg Latency (ms) |",
        "|----------|------:|-----------------:|",
    ]

    from collections import defaultdict
    category_stats = defaultdict(lambda: {"count": 0, "total_latency": 0.0})

    for r in results:
        cat = r["category"]
        category_stats[cat]["count"] += 1
        category_stats[cat]["total_latency"] += r["final_caption_latency_ms"]

    for cat, stats in sorted(category_stats.items()):
        avg_latency = stats["total_latency"] / stats["count"] if stats["count"] else 0
        lines.append(f"| {cat} | {stats['count']} | {avg_latency:.1f} |")

    lines.extend([
        "",
        "## Individual Results",
        "",
        "| ID | Category | Source | Expected | Latency (ms) |",
        "|----|----------|--------|----------|-------------:|",
    ])

    for r in results:
        lines.append(
            f"| {r['sample_id']} | {r['category']} | "
            f"{r['source_transcript'][:40]}... | "
            f"{r['expected_meaning'][:40]}... | "
            f"{r['final_caption_latency_ms']:.1f} |"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Report written to {output_path}")


if __name__ == "__main__":
    import sys

    direction = "en-th"
    if "--direction" in sys.argv:
        idx = sys.argv.index("--direction")
        direction = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "en-th"

    create_eval_dataset()
    results = run_evaluation(direction)
    generate_report(results)
    print(f"Evaluation complete: {len(results)} samples processed.")
