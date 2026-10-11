#!/usr/bin/env python3
"""Two-facts canary: prove that what one machine writes, the other one reads.

  memory_canary.py seed  [--repo PATH] [--machine NAME] [--no-push]
      On machine A. Writes two unguessable facts to working/canary.md in the
      memory repo, commits and pushes, and prints them.
  memory_canary.py check [--repo PATH] [--machine NAME] [--no-pull] [--max-age-h 24] [--expect WORD]
      On machine B. Pulls, then prints PASS only if the canary is there, intact,
      written by a different machine, and fresh. Prints FAIL with the reason otherwise.
  memory_canary.py selftest
      Builds a throwaway remote and two clones, and proves check FAILs before the
      pull, PASSes after it, and FAILs on a tampered file. Needs git; touches
      nothing outside a temp folder.

Then the human half: open a session on machine B and ask, in your own words (with
the word "canary" in it), what the canary's code word is. The note carries
`topic: canary`, so the plugin's lessons loader puts it in front of the session. A
plausible guess instead of the word means the sync or the loading is broken, not
the model.

One file, standard library only, Python 3.8+. Works on its own (with --repo) or
inside the tudlab-memory plugin, where it reads repo_path from the settings file.
Exit code: 0 PASS, 1 FAIL.
"""
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

REL = "working/canary.md"
WORDS = ("amber", "basalt", "cobalt", "delta", "ember", "fjord", "garnet", "harbor", "indigo", "juniper",
         "kestrel", "lantern", "meadow", "nimbus", "orchid", "pebble", "quartz", "raven", "saffron", "tundra",
         "umber", "velvet", "willow", "xenon", "yarrow", "zephyr", "anchor", "bramble", "cinder", "dune")


def settings():
    home = os.path.expanduser(os.environ.get("TMEM_HOME") or os.path.join("~", ".claude", "tudlab-memory"))
    try:
        with open(os.path.join(home, "config.json"), "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def git(repo, *args, timeout=90):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    extra = {"creationflags": 0x08000000} if os.name == "nt" else {}
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=env, stdin=subprocess.DEVNULL, **extra)


def has_upstream(repo):
    return git(repo, "rev-parse", "--abbrev-ref", "@{u}").returncode == 0


def checksum(word, number, epoch, machine):
    return hashlib.sha256(("%s|%s|%s|%s" % (word, number, epoch, machine)).encode("utf-8")).hexdigest()[:16]


def render(word, number, epoch, machine):
    when = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # The frontmatter lets the plugin's lessons loader put the canary in front of a
    # session that asks about it, so the human half tests loading, not just transport.
    head = "---\ndescription: Memory canary from %s - code word %s, number %s\ntopic: canary\n---\n" % (
        machine, word, number)
    return head + ("# Memory canary\n\n"
            "Seeded by %s at %s (epoch %d). Overwritten by every seed.\n\n"
            "- Code word: %s\n- Number: %s\n\n"
            "check: %s\n" % (machine, when, epoch, word, number, checksum(word, number, epoch, machine)))


def parse(text):
    m = {k: re.search(p, text or "") for k, p in (
        ("machine", r"Seeded by (.+?) at "), ("epoch", r"\(epoch (\d+)\)"), ("word", r"Code word:\s*(\S+)"),
        ("number", r"Number:\s*(\d+)"), ("check", r"check:\s*([0-9a-f]+)"))}
    if not all(m.values()):
        return None
    return {k: v.group(1) for k, v in m.items()}


def identity(repo, machine):
    if git(repo, "config", "user.email").stdout.strip():
        return []
    return ["-c", "user.name=" + machine, "-c", "user.email=" + machine + "@" + "memory.invalid"]


def pull_safely(repo, machine, keep):
    """Pull with merge, and never leave the repo half-merged.

    If the only conflict is the canary file itself (both machines seeded), keep="ours"
    keeps this machine's canary and keep="theirs" takes the other machine's. Any other
    conflict aborts the merge. Returns "" on success or the reason it failed.
    """
    r = git(repo, *identity(repo, machine), "pull", "--no-rebase", "--no-edit", "-q")
    if r.returncode == 0:
        return ""
    if git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0:
        return (r.stderr or r.stdout).strip()[:200] or "pull failed"
    unmerged = [n for n in git(repo, "diff", "--name-only", "--diff-filter=U", "-z").stdout.split("\0") if n]
    if unmerged != [REL]:
        git(repo, "merge", "--abort")
        return "merge conflict outside the canary; merge aborted, nothing changed"
    side = git(repo, "show", (":2:" if keep == "ours" else ":3:") + REL)
    with open(os.path.join(repo, REL), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(side.stdout)
    git(repo, "add", "--", REL)
    c = git(repo, *identity(repo, machine), "commit", "-q", "--no-verify", "--no-edit")
    if c.returncode != 0:
        git(repo, "merge", "--abort")
        return "could not finish the merge; aborted"
    return ""


def seed(repo, machine, push=True, rng=None):
    rng = rng or random.SystemRandom()
    word = "%s-%s-%04d" % (rng.choice(WORDS), rng.choice(WORDS), rng.randrange(10000))
    number = "%06d" % rng.randrange(1000000)
    epoch = int(time.time())
    path = os.path.join(repo, REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(word, number, epoch, machine))
    git(repo, "add", "--", REL)
    r = git(repo, *identity(repo, machine), "commit", "-q", "--no-verify", "-m", "memory canary: seeded by " + machine,
            "--", REL)
    if r.returncode != 0:
        return word, number, "FAIL: commit failed: " + (r.stderr or r.stdout).strip()[:200]
    if not push:
        return word, number, "committed, not pushed (--no-push)"
    if not has_upstream(repo):
        return word, number, "FAIL: committed, but the repo has no upstream, so no other machine can see it"
    for attempt in (1, 2):
        p = git(repo, "push", "-q")
        if p.returncode == 0:
            return word, number, "pushed"
        if attempt == 1:
            err = pull_safely(repo, machine, keep="ours")
            if err:
                return word, number, "FAIL: committed, but could not merge before pushing: " + err
    return word, number, "FAIL: push failed: " + (p.stderr or p.stdout).strip()[:200]


def check(repo, machine, pull=True, max_age_h=24.0, expect=None, allow_same=False, now=None):
    """Return (ok, message)."""
    now = time.time() if now is None else now
    if pull:
        if not has_upstream(repo):
            return False, "FAIL: the repo has no upstream, so nothing can arrive from another machine"
        err = pull_safely(repo, machine, keep="theirs")
        if err:
            return False, "FAIL: pull failed: " + err
    try:
        with open(os.path.join(repo, REL), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False, "FAIL: no canary in %s (not seeded yet, or this machine has not pulled it)" % REL
    c = parse(text)
    if not c:
        return False, "FAIL: canary file is damaged (cannot read its fields)"
    if checksum(c["word"], c["number"], c["epoch"], c["machine"]) != c["check"]:
        return False, "FAIL: canary was changed after seeding (checksum does not match)"
    age_h = (now - int(c["epoch"])) / 3600.0
    if c["machine"] == machine and not allow_same:
        return False, ("FAIL: the canary was seeded on this machine (%s); a check here proves nothing. "
                       "Seed on the other machine, or pass --allow-same for a dry run." % machine)
    if age_h > max_age_h:
        return False, ("FAIL: canary is %.1f h old (limit %.0f h): seed again on the other machine; if it "
                       "stays old after a fresh seed, this machine is not pulling" % (age_h, max_age_h))
    if expect and expect.strip().lower() != c["word"].lower():
        return False, "FAIL: code word here is not the one you were given (expected %s)" % expect
    return True, "PASS: canary from %s arrived intact, %.1f h old. Code word %s, number %s." % (
        c["machine"], age_h, c["word"], c["number"])


def selftest():
    if shutil.which("git") is None:
        print("FAIL: git is not installed")
        return 1
    tmp = tempfile.mkdtemp(prefix="canary-selftest-")
    results = []
    try:
        remote, a, b = (os.path.join(tmp, x) for x in ("remote.git", "a", "b"))
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True, capture_output=True)
        for clone in (a, b):
            subprocess.run(["git", "clone", "-q", remote, clone], check=True, capture_output=True)
            git(clone, "config", "user.name", "selftest")
            git(clone, "config", "user.email", "selftest" + "@" + "example.invalid")
        # an empty remote has no branch yet; give it one from A, and let B track it
        with open(os.path.join(a, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("selftest\n")
        git(a, "add", "README.md")
        git(a, "commit", "-q", "-m", "start")
        git(a, "push", "-q", "-u", "origin", "HEAD")
        git(b, "pull", "-q", "origin", git(a, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip())
        git(b, "branch", "-q", "--set-upstream-to=origin/" + git(a, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip())
        word, number, how = seed(a, "machine-a")
        results.append(("seed on A is pushed", how == "pushed", how))
        ok, msg = check(b, "machine-b", pull=False)
        results.append(("check on B before pulling FAILs", not ok, msg))
        ok, msg = check(b, "machine-b", pull=True, expect=word)
        results.append(("check on B after pulling PASSes", ok, msg))
        path = os.path.join(b, REL)
        with open(path, "r", encoding="utf-8") as fh:
            txt = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(txt.replace(number, "%06d" % ((int(number) + 1) % 1000000)))
        ok, msg = check(b, "machine-b", pull=False)
        results.append(("tampered canary FAILs", not ok, msg))
        ok, msg = check(a, "machine-a", pull=False)
        results.append(("check on the seeding machine FAILs", not ok, msg))
    except (OSError, subprocess.SubprocessError) as exc:
        results.append(("selftest ran", False, "%s: %s" % (type(exc).__name__, exc)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for name, good, msg in results:
        print("%s  %s  (%s)" % ("PASS" if good else "FAIL", name, msg[:110]))
    return 0 if results and all(g for _, g, _ in results) else 1


def arg(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "selftest":
        return selftest()
    if mode not in ("seed", "check"):
        print(__doc__)
        return 1
    cfg = settings()
    repo = os.path.abspath(os.path.expanduser(arg(argv, "--repo") or cfg.get("repo_path") or "~/memory"))
    machine = arg(argv, "--machine") or cfg.get("machine") or socket.gethostname().split(".")[0]
    if git(repo, "rev-parse", "--is-inside-work-tree").returncode != 0:
        print("FAIL: %s is not a git repository (pass --repo PATH)" % repo)
        return 1
    if mode == "seed":
        word, number, how = seed(repo, machine, push="--no-push" not in argv)
        print("Seeded on %s: code word %s, number %s (%s)." % (machine, word, number, how))
        print("On the other machine run:  memory_canary.py check  (or the canary skill), then open a session "
              "there and ask what the canary's code word is.")
        return 1 if how.startswith("FAIL") else 0
    try:
        max_age = float(arg(argv, "--max-age-h", "24"))
    except ValueError:
        print("FAIL: --max-age-h needs a number")
        return 1
    ok, msg = check(repo, machine, pull="--no-pull" not in argv, max_age_h=max_age,
                    expect=arg(argv, "--expect"), allow_same="--allow-same" in argv)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
