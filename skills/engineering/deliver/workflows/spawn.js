export const meta = {
  name: __NAME__,
  description: __DESCRIPTION__,
  phases: [{ title: __PHASE__ }],
}

// One deliver spawn point, rendered by scripts/workflow.py, which fills in the literals above and
// ROLES below. args.agents lists the agents to run side by side: [{label, agentType, brief}].
// ROLES holds the model and effort each agent type runs on (`workflow.py settings`): a workflow
// agent otherwise runs on the session's, whatever its agent type says. Returns {label: final
// report}, with null for an agent that ended without one.
const PHASE = __PHASE__
const ROLES = __ROLES__

const agents = typeof args.agents === 'string' ? JSON.parse(args.agents) : args.agents
for (const a of agents) {
  if (!ROLES[a.agentType]) throw new Error(`agent type ${a.agentType} was not rendered into this script`)
}

phase(PHASE)
const reports = await parallel(agents.map(a => () =>
  agent(a.brief, { label: a.label, phase: PHASE, agentType: a.agentType, ...ROLES[a.agentType] })))
return Object.fromEntries(agents.map((a, i) => [a.label, reports[i] ?? null]))
