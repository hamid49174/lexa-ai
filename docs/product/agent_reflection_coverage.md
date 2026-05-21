# Agent Reflection Coverage

This document maps Agent Reflection v1 coverage after the abuse-coverage sprint. It is local safety evidence only. It does not change InternalRC, PublicRC, or PublicRelease status.

## Flow

```text
LLM/tool parser
  -> registry JSON Schema validation
  -> permission classification
  -> deterministic ReflectionDecision
  -> if blocked: do not execute, return/audit safe failure
  -> permission + confirmation enforcement
  -> validate_params sanitization
  -> Companion / Personal OS / scheduler / workflow execution
  -> audit + result handling
```

Reflection is deterministic and policy-based. It is not LLM-based and does not implement Tree-of-Thought, MCTS, parallel tool execution, background execution, or a new planning framework.

## Path Map

| Path | Schema validation | Reflection behavior | Confirmation/permission enforcement | `validate_params` | Execution behavior | Audit behavior | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `action_executor.execute_action` | `validate_tool_arguments()` before permission and reflection | Called after schema validation for valid registered tools; low-risk read-only may return `None` | Blocked/unknown/confirmation enforced after reflection | Runs only after positive/non-blocking reflection | Companion called only after all gates pass | Reflection audit logs risk, confidence, decision, plan length, redacted arg keys only | `tests/test_action_executor_schema_validation.py` |
| `agent_loop._execute_tool` | `validate_tool_arguments()` before permission and reflection | Called after schema validation with `plan_length` and optional `low_confidence` | Blocked/unknown/confirmation enforced after reflection | Runs only after positive/non-blocking reflection | Companion or Personal OS bridge called only after all gates pass | Reflection block is returned to the agent as a failed tool result without executing | `tests/test_agent_loop.py`, `tests/test_agent_reflection.py` |
| `router_companion.execute_command` | `_validate_registry_params()` before reflection | Called after schema validation for direct Companion and Personal OS commands | Unknown/unregistered commands blocked before execution; confirmation-required commands still require consumed confirmation after positive reflection | Runs only after reflection | Companion or Personal OS action runs only after all gates pass | Client receives generic reflection-block message; audit omits argument values | `tests/test_router_companion.py`, `tests/test_companion_confirmation.py` |
| `router_companion.execute_batch` | Valid allowed batch commands are schema-validated before reflection | Allowed commands reflect with `plan_length=len(commands)`; confirmation-required and unknown commands are skipped by batch policy and never execute | Batch mode refuses blocked, unknown, and confirmation-required commands | Runs only for allowed, reflected commands | Only allowed validated commands execute; blocked/confirmation commands are skipped | Batch reflection blocks are audited without argument values | `tests/test_router_companion.py` |
| `scheduler._run_routine` | `validate_tool_arguments()` before permission/reflection | Called for valid routine actions, including confirmation-required actions, with routine action count | Blocked/unknown/confirmation actions are skipped after reflection and never execute | Runs only after positive reflection and allowed permission | `_companion_execute` fake/real callback is reached only after all gates pass | Reflection and skip decisions are audited with command/routine IDs, not argument values | `tests/test_scheduler_schema_validation.py` |
| `WorkflowEngine._step_tool` | `validate_tool_arguments()` before permission/reflection | Called after schema validation with workflow step count | Blocked, unknown, and confirmation-required tools raise before execution | Runs only after positive reflection and allowed permission | `_companion_execute` callback is reached only after all gates pass | Reflection audit omits nested prompt/action payload values | `tests/test_workflows.py` |
| Personal OS read tools | Registry schema validation at caller path | `personal_os_*` read tools are at least medium risk and reflect unless disabled | Existing permission policy still applies | Existing parameter/path policy still applies | `execute_personal_os_action()` runs only after gates | Safe arg keys only; no OS content or paths in Reflection audit | `tests/test_router_companion.py`, `tests/test_agent_loop.py` |
| OS-agent / draft-like tools | Registry schema validation at caller path | `os_agent_*` write/review-draft tools are high/critical and require reflection | Confirmation-required policy still applies | Existing parameter policy still applies | No direct execution in tests; only mocked or blocked paths | Safer read-only alternative is suggested for risky OS boundary | `tests/test_agent_reflection.py` |
| Unknown tools | Rejected by registry schema | Reflection does not run because schema validation fails first | Permission is not consulted in unified executor/agent loop for schema-invalid tools | Does not run | No execution | Schema-invalid audit only | `tests/test_action_executor_schema_validation.py`, `tests/test_agent_loop.py`, `tests/test_action_parser.py` |
| Malformed params | Rejected by registry schema | Reflection does not run | Permission is not consulted in strict executor paths | Does not run | No execution | Schema-invalid audit only | `tests/test_action_executor_schema_validation.py`, `tests/test_scheduler_schema_validation.py`, `tests/test_workflows.py`, `tests/test_router_companion.py` |
| Low-confidence parsed calls | N/A after parsing/schema validation | `low_confidence=True` forces reflection; risky write-like actions are blocked | If not blocked, normal permission still applies | Runs only if reflection allows | No execution when blocked | Reflection reason is `low_confidence_risky_action_blocked` | `tests/test_agent_reflection.py`, `tests/test_agent_loop.py` |
| Multi-step plans | N/A after parsing/schema validation | `plan_length > 1` forces reflection even for read-only tools | Normal permission still applies | Normal parameter policy still applies | Safe read-only actions may still execute through fakes/tests | Plan length recorded in audit | `tests/test_agent_reflection.py`, `tests/test_agent_loop.py`, `tests/test_router_companion.py`, `tests/test_workflows.py` |
| Low-risk read-only single action | Registry schema still applies at caller path | May intentionally skip reflection | Normal permission still applies | Normal parameter policy still applies | Executes only after existing gates | No reflection audit when skipped | `tests/test_agent_reflection.py`, existing executor tests |

## Abuse Cases Covered

- Unknown tools fail schema validation before reflection, permission checks, or execution.
- Malformed argument objects fail schema validation before reflection.
- High-risk and confirmation-required actions trigger reflection.
- Write-like actions trigger reflection.
- Low-confidence risky actions are blocked before sanitization and execution.
- Multi-step plans force reflection even for otherwise read-only tools.
- Personal OS and OS-agent boundaries trigger reflection and preserve existing confirmation/permission behavior.
- Scheduler and workflow tool paths are covered with fake execution callbacks only.
- Reflection blocks prevent Companion, Personal OS, scheduler, and workflow side effects.
- Prompt-injection strings and nested malicious action payloads are treated as argument data, not instructions.

## Audit Redaction Contract

Reflection audit entries may include:

- command name
- source
- risk level
- should-execute decision
- confidence
- confirmation requirement
- plan length
- redacted argument key list
- short reason code

Reflection audit entries must not include:

- argument values
- API keys or tokens
- bearer/authorization strings
- passwords, secrets, credentials, or private key material
- file paths or path-like values
- raw prompt payloads
- nested malicious action payload values

Sensitive-looking keys such as `api_key`, `token`, `authorization`, `password`, `secret`, `credential`, `path`, and `file` are redacted as `[REDACTED_KEY]`.

## Remaining Gaps

- Reflection v1 is policy-based. It does not prove semantic plan quality or full autonomous reasoning safety.
- Batch confirmation-required commands are skipped by batch policy before reflection because batch mode cannot collect user confirmation; this is intentionally fail-closed.
- Reflection does not replace registry schema validation, permission checks, confirmation tokens, `validate_params`, Personal OS draft/review rules, or release gates.
- PublicRC remains blocked by external proof requirements: remote CI, VM installer proof, signing, website release target/CDN/CSP/SRI decision, OS cleanup review, license decision, and privacy/trace consent for PublicRelease.
