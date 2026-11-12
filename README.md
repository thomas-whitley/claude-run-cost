# claude-run-cost

One script, no dependencies. Point it at a project and it prints what each Claude Code session and every subagent it spawned actually cost, and flags the three shapes that make a run expensive.

```
$ python measure_run_cost.py --days 1

                                                TOTAL    msgs  maxctx   output  fetches
----------------------------------------------------------------------------------------
main  2ca32e43                                  12.1M     388    118K     141K        4
  agent Scan boards A to H                      31.1M     485    210K      64K      132 !turns !ctx
  agent Scan boards I to P                      30.1M     490    217K      59K      158 !turns !ctx
  agent Company career pages                    14.6M     212    161K      31K       71 !turns !ctx !fanout(4)
    agent Career pages, part 1                   9.9M     140    155K      12K       40 !ctx
    agent Career pages, part 2                   9.7M     131    149K      11K       38
    ...
----------------------------------------------------------------------------------------
RUN COST: 127.0M
```

## Why this exists

On 3 September 2026 I ran a web research pipeline through eight Claude Code agents. It cost 127 million tokens and, with the rest of the day's work, hit my usage limit that afternoon.

Output tokens were 0.3 million of the 127. More than 90 percent was cache reads: agents re-reading their own context on every turn. The two biggest agents ran to 485 and 490 messages with contexts over 200K. One agent spawned four more, none of them capped, and all four died on the limit with nothing written down. 38 million tokens returned nothing.

I did not know any of that until I wrote this script; the numbers had been on disk the whole time.

The deterministic part of the job, fetching and filtering, moved into plain Python. The agents kept only the part that needed judgment, with a turn cap, a fetch cap and a rule against spawning their own. The same pipeline two weeks later cost 2.5 million tokens.

## What it reads

Claude Code writes a JSONL transcript per session at `~/.claude/projects/<project>/<session>.jsonl`, where `<project>` is the repo's absolute path with `:` and separators replaced by `-` (`C:\Users\me\repo` becomes `C--Users-me-repo`, `/home/me/repo` becomes `-home-me-repo`). Subagents get `~/.claude/projects/<project>/<session>/subagents/agent-*.jsonl`, with a `.meta.json` beside each holding the description and spawn depth.

Every assistant turn carries a `usage` block with `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` and `output_tokens`. The script sums them per transcript and nests subagents under the session that spawned them.

## Usage

```
python measure_run_cost.py                        # this project, sessions touched today
python measure_run_cost.py --days 3
python measure_run_cost.py --session 2ca32e43      # one session, by id prefix
python measure_run_cost.py --project ~/src/thing   # another project
python measure_run_cost.py --budget 15000000       # exit code 2 if over, for a CI or a hook
python measure_run_cost.py --top 10              # show only the N most expensive rows
```

Python 3.8 or later, standard library only.

## Reading the table

| Column | Meaning |
|---|---|
| TOTAL | input + cache creation + cache read + output tokens, which is what the API bills |
| msgs | lines in the transcript, roughly turns |
| maxctx | the largest single-turn input. Past about 150K, every further turn re-reads all of it |
| output | output tokens alone. If this is under 1 percent of TOTAL, the run was re-reading, not writing |
| fetches | WebFetch plus WebSearch calls |

The flags:

- `!turns`: more than 200 messages. An agent with no scope limit, or one that was resumed after saturating.
- `!ctx`: a turn with more than 150K of input. From here cost grows with the square of the turn count.
- `!fanout(n)`: the agent called the Agent tool n times. Its children are listed indented beneath it. In my 127M run, the 38M that returned nothing all sat under one fanout.

## What I changed after reading it

- Anything deterministic (fetch, parse, filter, dedupe) became a script. That removed 200 of 732 fetches and most of the failures.
- Every agent brief carries a turn cap and a fetch cap, and the scope is kept small enough that neither is reached.
- No agent may spawn agents.
- An agent writes findings to a file as it goes, not into its context, so a dead agent still leaves its work behind.
- A saturated agent is never resumed. Read its file, start a fresh one with the file as input.
- Run this after every pass with `--budget`, so an overrun fails loudly instead of showing up on the bill.

## Limits

Tokens, not dollars: rates differ by model and cache tier, so multiply by your own. It reads what is on disk, so if you clear transcripts you lose the history. `maxctx` is the biggest single turn, not the average. The paths are what Claude Code writes as of September 2026; if they move, `project_dir` is the one function to fix.

MIT licence.
