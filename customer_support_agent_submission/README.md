# Customer Support Agent Prototype

This prototype implements a customer support agent that can:

- detect a reference ticket in the customer's message,
- retrieve ticket details from a mock Jira/System of Record,
- create a new mock Jira ticket when no usable ticket exists,
- write and consult an agent scratchpad before ticket and KnowledgeBase updates,
- retrieve relevant snippets from a local KnowledgeBase,
- run an explicit ReAct loop with visible tool steps,
- produce a customer-facing support response using LangChain `ChatGroq`,
- run without credentials in deterministic demo mode.

## Assumptions

- Ticket references look like `ABC-123`, for example `AUTH-1001` or `BILL-2044`.
- The System of Record is represented by `data/tickets.json`, standing in for Jira or a similar platform. New tickets are appended to this file.
- The KnowledgeBase is represented by `data/knowledge_base.md`.
- LangChain `ChatGroq` is used when `GROQ_API_KEY` is configured. If dependencies or credentials are missing, the same orchestration runs with a local fallback responder so the prototype is still reviewable.
- The agent is intentionally small and transparent for an open-book exam setting. In production, ticket access, authentication, auditing, PII filtering, and vector search would be hardened.

## Supporting Docs

The implementation follows a simple retrieval-augmented ReAct loop:

1. The customer starts a chat and describes their issue.
2. The agent runs `extract_ticket_reference`.
3. The scratchpad records whether a new ticket should be logged.
4. If a ticket reference exists, the agent runs `retrieve_ticket`.
5. If no ticket exists or the referenced ticket is unknown, the agent runs `create_ticket` and appends the ticket to `data/tickets.json`.
6. The agent runs `search_knowledge_base`.
7. If the scratchpad records a KnowledgeBase gap, the agent runs `update_knowledge_base`.
8. The Streamlit UI shows the loop trace and scratchpad: reason, action, action input, observation, and decisions.
9. The final answer is generated with `ChatGroq` when available, using the ticket details and KnowledgeBase snippets as context.
10. If `ChatGroq` is unavailable, a deterministic local response is returned for demo and grading.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="your_groq_api_key"
```

Optionally choose a Groq model:

```bash
export GROQ_MODEL="llama-3.1-8b-instant"
```

## Run

Streamlit UI:

```bash
streamlit run streamlit_app.py
```

One-shot mode:

```bash
python support_agent.py "I'm having trouble logging in. My ticket is AUTH-1001"
```

Interactive chat mode:

```bash
python support_agent.py
```

Then try:

```text
I'm having trouble logging in
I still cannot login. Ticket AUTH-1001
I was charged twice, ticket BILL-2044
I cannot access my account. Ticket AUTH-9999
```

## Working Prototype Demo

A sample demo transcript is available in `demo/demo_transcript.txt`.

A screenshot-style demo artifact is available at `demo/demo_screenshot.svg`.

Newly created mock Jira tickets are appended to `data/tickets.json`. They are also copied to `data/created_tickets.json` as a small audit log.

The agent scratchpad is written to `data/agent_scratchpad.json`.

## Files

- `support_agent.py`: working agent code
- `streamlit_app.py`: Streamlit chat UI for the support agent
- `data/tickets.json`: mock Jira/System-of-Record ticket data, including newly created tickets
- `data/created_tickets.json`: secondary mock Jira ticket creation audit log
- `data/agent_scratchpad.json`: latest agent scratchpad decisions and observations
- `data/knowledge_base.md`: KnowledgeBase document
- `demo/demo_transcript.txt`: recorded terminal-style demo transcript
- `demo/demo_screenshot.svg`: screenshot-style demo image
- `requirements.txt`: Python dependencies
