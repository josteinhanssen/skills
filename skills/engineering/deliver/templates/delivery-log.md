# Delivery log

State of record for `/deliver` batches in this repository. Appended per event, newest at the bottom of each batch section; survives orchestrator restarts.

## Batch {slug} ({date})

**Plan:** `{plan path}`, approved {date}. Base `{branch}` @ `{head}`. Tickets: {list with model}.

**Rulings shaping the batch:** {bullets}

**Events:**

- {time}Z {event: spawned / grant / READY-TO-MERGE / merged → head / BLOCKED → ruling / respawned / run of record / deploy run id}

**Run of record:** {command} on {head}: {expected}/{unexpected}/{flaky}/{skipped}, {wall}, {summed}.

**Close:** deploy run {id} {result}; cleanup {removed n worktrees, m branches; kept: list}; follow-ups {ticket ids}.

**Cost:**

| Ticket | Plan | Implement | Review | Rulings | Rounds | Raw tokens | Weighted | Findings after merge |
|---|---|---|---|---|---|---|---|---|
