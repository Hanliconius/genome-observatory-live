# Publication validation and recovery review

Review date: 14 October 2026. Recovery branch: pegasus-publication-recovery-20261014T183358Z.

The audited unit suite passed in the isolated Python 3.12 retry environment after installing requirements.txt (including pycountry). The original failure was a missing dependency. This applies to the audited checkout, not all subsequent commits.

From a fresh environment and repository root:
```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

Record git rev-parse HEAD, python --version, and python -m pip freeze with results. A full live data refresh and rendered-site verification were not performed by the publication audit. The absent Pegasus source directory is not itself evidence that GitHub code is missing. Publish source-specific acquisition/provenance instructions; avoid importing cluster outputs or caches as source code.

Publication scope: maintained source, configuration, dependency definitions, reproduction commands, and small intentional test fixtures. Raw scientific data, intermediates, caches, installed environments, and generated run directories stay outside the code release. Passing syntax/tests is distinct from reproducing accepted scientific outputs.
