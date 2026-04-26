# Customer Support Agent Submission

## What Was Built

This submission contains a working customer support agent prototype with:

- a Streamlit chat UI,
- a LangChain `ChatGroq`-backed support agent,
- an explicit ReAct loop with reason, action, action input, and observation,
- ticket extraction from customer messages,
- mock Jira/System-of-Record ticket lookup,
- mock Jira ticket creation when no usable ticket exists,
- an agent scratchpad used for ticket logging and KnowledgeBase update decisions,
- KnowledgeBase retrieval,
- deterministic fallback mode for demos without a Groq API key.

## Assumptions

- Ticket references follow a format such as `AUTH-1001`, `BILL-2044`, or `SYNC-3120`.
- Jira or a similar System of Record is represented by `data/tickets.json` and `MockJiraClient`; new tickets are appended to `data/tickets.json`.
- The support KnowledgeBase is represented by `data/knowledge_base.md`.
- `ChatGroq` is used when `GROQ_API_KEY` is available.
- Without `GROQ_API_KEY`, the app still works in demo mode using the same ReAct loop contract and deterministic planning.

## How To Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional, for Groq-powered responses:

```bash
export GROQ_API_KEY="your_groq_api_key"
export GROQ_MODEL="llama-3.1-8b-instant"
```

Start the Streamlit UI:

```bash
streamlit run streamlit_app.py
```

Run from the command line:

```bash
python support_agent.py "I still cannot login. My ticket is AUTH-1001"
```

## Recommended Demo Prompts

```text
I'm having trouble logging in
I still cannot login. My ticket is AUTH-1001
I was charged twice, ticket BILL-2044
The import is delayed, ticket SYNC-3120
```

## How The Problem Was Solved

The system uses a retrieval-augmented ReAct loop:

1. Receive the customer chat message.
2. Run `extract_ticket_reference`.
3. Write scratchpad notes that decide whether a new ticket should be logged.
4. Run `retrieve_ticket` when a ticket reference is available.
5. Run `create_ticket` when the scratchpad says a new ticket should be logged.
6. Run `search_knowledge_base`.
7. Run `update_knowledge_base` when the scratchpad says the KB has no matching guidance.
8. Run `final_answer`.
9. Generate the final support response using LangChain `ChatGroq`, or local fallback mode when credentials are unavailable.

The Streamlit sidebar shows the loop trace, including reason, action, action input, and observation for each step.
It also shows the scratchpad decisions and observations.

## Deliverables

- `streamlit_app.py`: Streamlit UI.
- `support_agent.py`: core support agent implementation.
- `data/tickets.json`: mock ticket data, including tickets created by the mock Jira client.
- `data/created_tickets.json`: secondary audit log for created tickets.
- `data/agent_scratchpad.json`: latest scratchpad state for agent decisions.
- `data/knowledge_base.md`: KnowledgeBase document.
- `docs/SOLUTION.md`: supporting design notes.
- `demo/demo_transcript.txt`: recorded demo transcript.
- `demo/demo_screenshot.svg`: screenshot-style demo artifact.
- `README.md`: setup and usage instructions.
- `requirements.txt`: dependencies.

## Verification Completed

- Python syntax compilation passed for `support_agent.py` and `streamlit_app.py`.
- CLI demo flows were run successfully in local deterministic mode.
- Agent loop traces were verified for found-ticket, no-ticket, and unknown-ticket scenarios.
- New ticket creation was verified by inspecting `data/tickets.json` after creation.
- KnowledgeBase update was verified for a query with no relevant KB match.
- Streamlit is listed in `requirements.txt`; install dependencies before launching the UI.
