# Eval Baselines

`eval_baseline.json` is the commit-friendly baseline manifest for the offline
Lexa eval suite. It stores only case IDs, suite names, risk levels, expected
status, and blocking policy. It does not store model answers, prompts, traces,
tool arguments, reports, or user data.

Update this baseline only from a fully green offline eval report:

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --all --json-report .test-tmp\current_eval_report.json
venv\Scripts\python.exe evals\runners\update_eval_baseline.py --current .test-tmp\current_eval_report.json --output evals\baselines\eval_baseline.json --created-from phase_3f_green
```

Do not update the baseline to accept high/critical failures, secret leaks, or
policy violations. If the regression gate fails, fix the regression or add an
intentional new passing case and then regenerate the baseline from a green run.
