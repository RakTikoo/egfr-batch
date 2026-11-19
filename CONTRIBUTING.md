# Contributing

Thanks for looking. egfr-batch is a small, single-purpose tool; these
house rules keep changes easy to review.

> **Research and educational tool only. Not a medical device.** This
> tool does published-formula arithmetic only — it does not diagnose,
> stage, or interpret anything.

## Run the tests

```console
$ python3 run_tests.py
```

All tests must pass before a change is considered. Add tests in `tests/`
for any new behaviour. New equation behaviour needs an oracle case
computed by hand from the published equation, or an independently
published worked example — never a value produced by the tool itself.

## House rules

- Keep the tool single-purpose and dependency-free (standard library
  only). Equations are used exactly as published; nothing is fitted,
  adjusted or "improved".
- No staging, diagnosis, reference-range flagging or interpretation —
  arithmetic only, by design. Pull requests adding interpretation will
  not be accepted.
- The refusal to guess `--scr-unit` is the product; a change that makes
  it optional will not be accepted.
- The README's Honest limits section is a promise. If a change alters a
  documented limit or behaviour, update the README in the same pull
  request — and SKILL.md too if the CLI, its flags or its exit codes
  changed.
- Plain words in docs and messages. No marketing language.

## Claiming an issue

Comment on the issue saying you are taking it, then open a pull request
that mentions the issue number.
