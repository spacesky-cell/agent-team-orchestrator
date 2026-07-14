# Examples

## Verify the npm-managed runtime

```bash
ato --version
ato doctor
ato doctor
```

The version command does not create Python state. The first doctor may download dependencies; the second reuses the same managed executable.

## Repository review in the foreground

```bash
ato run "Review this repository, identify one blocking reliability issue, fix it, and run the relevant tests"
```

The attached CLI follows status changes. If a mutating tool pauses, answer the approval prompt. The task resumes from its checkpoint.

## Detached implementation task

```bash
ato run "Add input validation to the public API and cover allowed and denied cases" --detach
ato tasks
ato status <task-id>
ato audit <task-id>
```

Use detached mode for MCP-like asynchronous operation or when another process will monitor status.

## Explicit approval

```bash
ato status task-abcd
ato approve task-abcd approval-1234
```

The request ID must match `active_approval.request_id`. To deny the mutation:

```bash
ato approve task-abcd approval-1234 --reject
```

## Team memory

```bash
ato memory
ato memory --query "authentication architecture" --top-k 3
```

Memory is project-root scoped. Semantic search is used when ChromaDB is available; otherwise ATO returns its local structured context.

## MCP request sequence

1. Call `create_team_task` with `description` and `projectRoot`.
2. Save the returned `task_id`.
3. Call `get_task_status` with that ID.
4. When approval is active, call `approve_step` with `taskId`, `requestId`, and `approved`.
5. Call `get_task_audit` for redacted tool history.

See [demo/task.json](demo/task.json) and [demo/tool-audit.jsonl](demo/tool-audit.jsonl) for redacted artifact shapes.
