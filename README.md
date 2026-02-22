# Guardian

Web intelligence gathering tool. Searches the internet for publicly available information associated with a target name, evaluates relevance, and stores vetted results in a permanent record.

## How It Works

1. **Search** — Queries the web for the target name
2. **Hold** — Raw results stored in a transient folder
3. **Evaluate** — Each result scored for relevance (0–100)
4. **Store or Discard** — Relevant results go to permanent records; the rest are deleted
5. **Clean up** — Transient data is wiped after each run

## Usage

```bash
pip install -r requirements.txt
python -m src.main "John Smith"
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Project Structure

```
src/
  main.py        — Program entry point (the full workflow)
  searcher.py    — Searches the web for a target name
  evaluator.py   — Scores each result for relevance
  storage.py     — Manages transient and permanent storage
data/
  transient/     — Temporary holding area (cleared after each run)
  records/       — Permanent, append-only storage
tests/
  test_evaluator.py — Verifies the scoring logic works correctly
```
