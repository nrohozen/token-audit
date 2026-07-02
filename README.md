# token-audit

Scan your local Claude Code session transcripts and report token usage with estimated costs.

All data stays local — no network calls, no telemetry.

## Requirements

- Python 3.11 or later (uses `tomllib` from the standard library)
- No third-party dependencies

## Install

```bash
git clone <repo>
cd token-audit
pip install -e .
```

Or run directly without installing:

```bash
python3 -m token_audit.cli <command>
```

## Usage

```
token-audit [OPTIONS] COMMAND
```

### Commands

| Command      | Description                              |
|--------------|------------------------------------------|
| `summary`    | Total token usage across all projects    |
| `by-project` | Breakdown by project directory           |
| `by-model`   | Breakdown by model                       |
| `by-day`     | Breakdown by calendar day                |

### Global options

| Option | Default | Description |
|--------|---------|-------------|
| `--data-dir PATH` | `~/.claude/projects` | Claude projects directory |
| `--prices PATH` | bundled `prices.toml` | Custom pricing config |
| `--no-cost` | off | Skip cost estimation |
| `--format {table,csv,json}` | `table` | Output format |
| `--efficiency` | off | Switch breakdown tables to the full efficiency view, replacing the token-count columns (see [Efficiency metrics](#efficiency-metrics)) |
| `--since YYYY-MM-DD` | — | Include only records on or after this date |
| `--until YYYY-MM-DD` | — | Include only records on or before this date |

### Examples

```bash
# Total usage across everything
token-audit summary

# Costs broken down by project, as JSON
token-audit --format json by-project

# Usage for a specific month, no cost column
token-audit --since 2026-05-01 --until 2026-05-31 --no-cost by-day

# Point at a different Claude data directory
token-audit --data-dir /path/to/.claude/projects by-model

# Use your own pricing file
token-audit --prices ~/my-prices.toml summary

# Show efficiency ratios per model instead of token counts
token-audit --efficiency by-model
```

## Efficiency metrics

Beyond raw token counts, the tool derives four efficiency ratios from the same
data:

- The `summary` output shows all four automatically.
- The breakdown tables (`by-project` / `by-model` / `by-day`) show the two most
  actionable ones — **cache hit rate** and **cost/turn** — inline by default.
  Pass `--efficiency` to switch those tables to the full ratio view (all four
  metrics, replacing the token-count columns).
- `csv` and `json` output **always** include all four, regardless of the flag.

| Metric | Formula | What it tells you |
|--------|---------|-------------------|
| **Cache hit rate** | `cache_read / (cache_read + cache_write + input)` | Share of input-side tokens served cheaply from the prompt cache. Higher is better — cache reads bill at a fraction of fresh input. |
| **Output yield** | `output / (input + cache_write + cache_read)` | Output tokens generated per input-side token. Most useful compared *across* projects/models than as an absolute target. |
| **Cost / turn** | `cost / turns` | Average cost per API round-trip. |
| **Cost / session** | `cost / sessions` | Average cost per session. |

Ratios are `n/a` (table) / empty (csv) / `null` (json) when undefined — e.g. a
model with no input-side tokens, or cost-per-* when cost estimation is off.
In `csv`/`json` the fields are named `cache_hit_rate`, `output_yield`,
`cost_per_turn_usd`, and `cost_per_session_usd`.

```bash
# Efficiency ratios per project
token-audit --efficiency by-project

# Efficiency ratios always present in machine-readable output
token-audit --format json by-model
```

## Pricing configuration

Prices live in `token_audit/prices.toml` (bundled with the package). To override:

1. Copy it to `~/.config/token-audit/prices.toml` and edit — that file is checked first automatically.
2. Or pass `--prices /path/to/your/prices.toml` on each invocation.

The format is TOML with prices in **USD per million tokens**:

```toml
[models.claude-sonnet-4-6]
input_per_mtok     = 3.00
output_per_mtok    = 15.00
cache_write_per_mtok = 3.75
cache_read_per_mtok  = 0.30

[unknown_model_fallback]
input_per_mtok     = 3.00
output_per_mtok    = 15.00
cache_write_per_mtok = 3.75
cache_read_per_mtok  = 0.30
```

Set `unknown_model_fallback` values to `0.0` to suppress cost estimation for models not in the table.

## Token types reported

| Column | Field in transcript | Notes |
|--------|--------------------|----|
| Input | `usage.input_tokens` | Tokens in the prompt (including context) |
| Output | `usage.output_tokens` | Tokens generated |
| Cache Write | `usage.cache_creation_input_tokens` | Tokens written to prompt cache |
| Cache Read | `usage.cache_read_input_tokens` | Tokens read from prompt cache |

## Data source

Transcripts are stored as JSONL files under `~/.claude/projects/<project>/`. Each line is a JSON object. The tool reads only lines with `"type": "assistant"` and looks for the `message.usage` and `message.model` fields. All other content is ignored.

Malformed lines are skipped and counted; the total is reported at the end of each run.

## Tests

```bash
python3 -m pytest tests/ -v
```

Fixtures in `tests/fixtures/` are entirely synthetic — no real transcript data.

## License

[MIT](LICENSE).
