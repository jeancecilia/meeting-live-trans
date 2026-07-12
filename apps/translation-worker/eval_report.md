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