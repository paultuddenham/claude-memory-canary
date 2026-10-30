# Memory Canary for Claude Code (free)
[![selftest](https://github.com/paultuddenham/claude-memory-canary/actions/workflows/selftest.yml/badge.svg)](https://github.com/paultuddenham/claude-memory-canary/actions/workflows/selftest.yml)

One Python file that proves your Claude Code sessions on two machines really share
memory. If you sync notes between a desktop and a laptop (a git repo, a shared
folder, anything), this is the test that tells you whether the other side actually
got them, instead of trusting that the push went out.

It is the "two-facts test" done at the right layer: seed two unguessable facts on
machine A, check for them on machine B. PASS or FAIL, with the reason and the age.

## Use it

You need Python 3.8+, git, and a git repository both machines clone (keep it
private).

1. Prove the script works on this machine (builds a throwaway repo, touches nothing
   else):
   ```
   python memory_canary.py selftest
   ```
   Five lines, all PASS.
2. On machine A:
   ```
   python memory_canary.py seed --repo ~/memory
   ```
   It writes `working/canary.md` with a code word and a number, commits and pushes,
   and prints both.
3. On machine B:
   ```
   python memory_canary.py check --repo ~/memory
   ```
   It pulls, then prints PASS only if the canary is there, unchanged, written by a
   different machine and under 24 hours old (`--max-age-h` to change).
4. The human half: open a Claude Code session on machine B and ask, in your own
   words, what the canary's code word is. A plausible guess instead of the word
   means your sessions are not loading what arrived.

Exit code 0 = PASS, 1 = FAIL, so it can run from a scheduler or a monitor.

## The full kit

Tudlab Code: Memory turns this into a working setup: a session-start pull and
stop-hook push of your private memory repo with a merge-never-clobber policy,
Claude Code memory notes that travel by tag, lessons loaded by topic the first time
a session needs them, a promote job for long-term notes, and a 19-page guide.
Write-up of the design: https://tudlab.com/memory
US$29: https://gumroad.com/l/tudlab-code-memory

MIT licence.
