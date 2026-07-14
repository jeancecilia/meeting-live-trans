# Translation Evaluation Report

**Samples:** 5
**Provider:** openai-transcribe-then-translate

## Results by Category

| Category | Count | Avg Latency (ms) |
|----------|------:|-----------------:|
| business | 1 | 144.0 |
| dates | 1 | 159.0 |
| names | 1 | 144.0 |
| prices | 1 | 144.0 |
| tech | 1 | 159.0 |

## Individual Results

| ID | Category | Source | Expected | Latency (ms) |
|----|----------|--------|----------|-------------:|
| biz-001 | business | We need to launch the app by September, ... | We need to launch the application by Sep... | 144.0 |
| tech-001 | tech | The API endpoint returns JSON with user ... | The API endpoint returns JSON with user ... | 159.0 |
| name-002 | names | Please contact Jennifer Williams at exte... | Please contact Jennifer Williams at exte... | 144.0 |
| date-001 | dates | The meeting is on Monday, July fifteenth... | The meeting is scheduled for Monday, Jul... | 159.0 |
| price-001 | prices | Total cost is one thousand two hundred f... | The total cost is $1,250.50 or approxima... | 144.0 |

## 2026-07-14 live provider validation

The Realtime Translation WebSocket was exercised with 24 kHz PCM synthetic
speech in both directions. No transcript or translated content was written to
the probe output; checks were recorded as semantic booleans and character-class
counts.

| Pipeline | Direction | First partial | Result |
|----------|-----------|--------------:|--------|
| `gpt-realtime-translate` | English → Thai | 2.20 s from speech start | Thai output; software, Tuesday, and 3:30 checks passed |
| `gpt-realtime-translate` | Thai → English | 1.52–2.89 s from speech start | Output language passed, but date/time checks were inconsistent across runs |
| transcribe then translate | Thai → English | partial before final | Stable event ID/revisions; selected as the quality fallback |

Chosen test policy: `openai-hybrid`, with direct translation enabled only for
English source audio and automatic per-track fallback. Thai source audio uses
transcribe-then-translate. Realistic microphone, accent, and noise UAT remains
required before this test policy is treated as a final production benchmark.
