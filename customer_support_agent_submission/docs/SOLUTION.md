# Solution Notes

## Approach

The prototype separates the support-agent workflow into three clear responsibilities:

- `MockJiraClient` retrieves existing ticket records and creates new mock Jira issues.
- `KnowledgeBase` retrieves relevant support guidance from a markdown KnowledgeBase.
- `AgentScratchpad` records observations and decisions before writing tickets or KnowledgeBase updates.
- `SupportAgent` runs an explicit ReAct loop, calls tools, records observations, and then generates a response.

## ReAct Loop

The support agent uses a ReAct-style loop:

1. `extract_ticket_reference`: inspect the customer message for a ticket such as `AUTH-1001`.
2. `retrieve_ticket`: if a ticket reference exists, retrieve details from the mock System of Record.
3. `create_ticket`: create a new mock Jira issue when the scratchpad says no usable ticket exists.
4. `search_knowledge_base`: search KnowledgeBase sections using the customer issue and ticket context.
5. `update_knowledge_base`: append generated guidance when the scratchpad says no relevant KB match exists.
6. `final_answer`: respond using the gathered observations.

## Mock Jira Integration

The prototype uses `MockJiraClient` as a stand-in for Jira:

- Existing issues are loaded from `data/tickets.json`.
- `get(ticket_id)` simulates Jira issue lookup.
- `create_issue(customer_message, source_ticket_id)` simulates Jira issue creation.
- Created issues use IDs like `SUP-5001`, inferred product area, inferred priority, and recommended next step.
- Created issues are appended to `data/tickets.json`, so subsequent lookups can retrieve them from the mock System of Record.
- Created issues are also copied to `data/created_tickets.json` as an audit trail.

In a production version, `MockJiraClient` is the boundary that would be replaced by the Jira REST API.

Each loop iteration stores:

- `reason`: concise explanation for the next action.
- `action`: selected tool or `final_answer`.
- `action_input`: JSON input passed to the action.
- `observation`: result returned by the action.

The loop is visible in the Streamlit sidebar under `ReAct Loop`.

## Scratchpad

The scratchpad is persisted to `data/agent_scratchpad.json` on every run. It records:

- observed ticket reference,
- whether a ticket was found,
- whether the agent should log a new ticket,
- KnowledgeBase matches,
- whether there is a KnowledgeBase gap,
- whether the KnowledgeBase was updated,
- action observations.

The deterministic planner and the Groq planner both receive scratchpad state. The deterministic planner only runs `create_ticket` when `should_log_ticket` is true, and only runs `update_knowledge_base` when `should_update_knowledge_base` is true.

## Ticket Detection

Customer messages are scanned for ticket identifiers with this pattern:

```python
r"\b[A-Z][A-Z0-9]+-\d+\b"
```

This matches references such as `AUTH-1001`, `BILL-2044`, and `SYNC-3120`.

## Retrieval

The KnowledgeBase is split into markdown sections. The `search_knowledge_base` loop action scores each section by overlapping keywords from:

- the customer's message,
- the ticket summary,
- the ticket product area.

The highest-scoring sections are stored in the agent state and passed into the final response step.

## ChatGroq Usage

When `GROQ_API_KEY` is available, the agent creates a LangChain `ChatGroq` client:

```python
ChatGroq(
    model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
    temperature=0.2,
)
```

The LLM receives:

- a system instruction defining support-agent behavior,
- the customer message,
- ticket context,
- KnowledgeBase context.

## Demo Mode

If the Groq key or LangChain packages are unavailable, the agent falls back to a deterministic local planner and response. This keeps the prototype runnable for reviewers while preserving the same ReAct loop contract.

## Production Considerations

For a production version, I would add:

- OAuth or service authentication for Jira/System-of-Record access,
- customer identity and ticket ownership checks,
- PII redaction before sending context to the LLM,
- vector embeddings for KnowledgeBase retrieval,
- observability for retrieved docs, generated answers, and escalations,
- human handoff when confidence is low or the issue is account-sensitive.
