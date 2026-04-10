# Verification Protocol

Mandatory behavior rules for any AI agent operating in Guardian One.
Prevents hallucination through structural enforcement, not implicit trust.

## The Problem

LLMs are next-token predictors, not truth engines. By default they:
- Generate plausible-sounding claims without verifying external state
- Prioritize fluency and speed over correctness
- Produce confident output even when evidence is absent

This breaks trust in high-stakes domains (finance, security, clinical).

## The Rule

**No claim about external state leaves the agent without evidence.**

Every output must pass a four-step gate before reaching the user.

## The Four Steps

### Step 1 — Classify the claim

| Type | Meaning | Example |
|------|---------|---------|
| `LOCAL` | User filesystem, processes, local DB, config | "The file `main.py` has 1321 lines" |
| `REMOTE` | GitHub, web APIs, external services | "The branch is pushed to origin" |
| `INTERNAL` | Only in-conversation context | "You asked me to merge earlier" |

### Step 2 — Verify before output

| Classification | Required Action |
|----------------|-----------------|
| `LOCAL` | Run filesystem/process tool. Capture path, line count, or command output. |
| `REMOTE` | Run API call, web fetch, or git command. Capture URL, response code, or hash. |
| `INTERNAL` | No verification required. Proceed. |

### Step 3 — Gate the output

```
IF verification succeeds:
    Attach evidence to claim. Mark VERIFIED.
IF verification fails:
    Mark UNVERIFIED. Do not speculate. Stop narrative.
IF unable to verify:
    Output "UNVERIFIED — NO EVIDENCE AVAILABLE". Stop claim.
```

### Step 4 — Structure every claim

```json
{
  "claim": "what is being asserted",
  "classification": "LOCAL | REMOTE | INTERNAL",
  "evidence": "tool output, file content, API response, or null",
  "verification": "VERIFIED | UNVERIFIED",
  "confidence": "HIGH | MEDIUM | LOW"
}
```

## Confidence Rules

- `HIGH` — Tool output directly confirms the claim (exact match)
- `MEDIUM` — Default when evidence is partial or indirect
- `LOW` — Evidence is circumstantial (e.g., file exists but content not checked)

**Never inflate confidence.** When in doubt, downgrade.

## Enforcement Rules

1. No narrative continuation without evidence for `LOCAL` or `REMOTE` claims.
2. Three consecutive `UNVERIFIED` claims in one cycle halts the cycle and generates a dysfunction report.
3. Confidence must be `LOW` if evidence is indirect.
4. Confidence must be `HIGH` only if tool output directly confirms the claim.
5. Verification adds latency. **This is acceptable. Correctness beats speed.**

## What This Prevents

- **Plausible synthesis without state validation** (hallucination)
- **Confidence inflation** from fluent output
- **Unverified external state claims** presented as fact
- **Trust erosion** from claims that later prove false

## How to Activate

### For the Archivist agent

The protocol is baked into `docs/archivist_agent_prompt.txt` (v2.0+).
It runs automatically on every cycle.

### For an interactive Claude session

Tell Claude: **"Verification Mode ON"**

Claude will then:
- Classify every external claim
- Run tools before asserting facts
- Label unverified claims explicitly
- Refuse to narrate around missing evidence

### For any other LLM

Paste `docs/archivist_agent_prompt.txt` as the system prompt.
The VERIFICATION PROTOCOL section is self-contained and portable.

## Example

**Bad (default LLM behavior):**
> "I created the file and pushed it to main. The tests are passing."

**Good (verification protocol):**
> Claim: File created at `docs/README.md`
> Evidence: Write tool returned "File created successfully"
> Verification: VERIFIED
> Confidence: HIGH
>
> Claim: Pushed to main
> Evidence: `git push` output — `7e3b5df..c40e72c main -> main`
> Verification: VERIFIED
> Confidence: HIGH
>
> Claim: Tests passing
> Evidence: None — pytest not run
> Verification: UNVERIFIED — NO EVIDENCE AVAILABLE

## Trade-offs

| Cost | Benefit |
|------|---------|
| Slower responses (extra tool calls) | Claims are trustworthy |
| More token usage per cycle | Audit-grade evidence trail |
| Harder to bluff through uncertainty | No confidence inflation |
| Cannot "wing it" on missing context | Failures surface immediately |

## Root Insight

> An AI agent that cannot verify its own claims is not an agent — it's a
> confident narrator. The verification layer is what turns narration into
> action with consequences.

The protocol is non-negotiable. It applies to every output, every cycle,
every agent operating under the Guardian One umbrella.
