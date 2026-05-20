# Eval Failure Triage

Failure triage records explain what broke, how risky it is, and what to do next.
They are generated from local eval regression reports and must not contain raw
prompts, user data, secrets, full tool arguments, traces, or private content.

High and critical failures are blocking. Secret leaks are always blocking.
Direct writes without approval, unapproved apply, permission bypass, unbounded
agent loops, and failed verification marked as success are treated as blocking
policy violations.

Generated triage reports belong under ignored paths such as `evals/results/` or
test temp directories. Commit only this schema and documentation.
