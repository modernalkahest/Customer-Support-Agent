from __future__ import annotations

import json
import os

import streamlit as st

from support_agent import SupportAgent


st.set_page_config(
    page_title="Customer Support Agent",
    layout="wide",
)


@st.cache_resource
def get_agent() -> SupportAgent:
    return SupportAgent()


def reset_chat() -> None:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hi, I can help troubleshoot your issue. "
                "Share what happened, and include a ticket reference if you have one."
            ),
        }
    ]
    st.session_state.last_query = ""
    st.session_state.last_result = None


def add_example_prompt(prompt: str) -> None:
    st.session_state.pending_prompt = prompt


if "messages" not in st.session_state:
    reset_chat()

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

agent = get_agent()

st.title("Customer Support Agent")
st.caption("Retrieves mock ticket details, searches the KnowledgeBase, and answers customer questions.")

with st.sidebar:
    st.header("Agent Status")
    if agent.llm:
        st.success("ChatGroq is active")
        st.caption(f"Model: {os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant')}")
    else:
        st.warning("Demo mode")
        st.caption("Set GROQ_API_KEY to enable LangChain ChatGroq responses.")

    st.divider()
    st.subheader("Try a Scenario")
    st.button(
        "Login issue",
        on_click=add_example_prompt,
        args=("I'm having trouble logging in",),
        use_container_width=True,
    )
    st.button(
        "Login with ticket",
        on_click=add_example_prompt,
        args=("I still cannot login. My ticket is AUTH-1001",),
        use_container_width=True,
    )
    st.button(
        "Billing with ticket",
        on_click=add_example_prompt,
        args=("I was charged twice, ticket BILL-2044",),
        use_container_width=True,
    )
    st.button(
        "Create new ticket",
        on_click=add_example_prompt,
        args=("I'm having trouble logging in and need help",),
        use_container_width=True,
    )
    st.button(
        "Unknown ticket",
        on_click=add_example_prompt,
        args=("I cannot access my account. Ticket AUTH-9999",),
        use_container_width=True,
    )
    st.button("Reset chat", on_click=reset_chat, use_container_width=True)

    st.divider()
    st.subheader("ReAct Loop")
    last_result = st.session_state.get("last_result")
    if last_result:
        for step in last_result.steps:
            with st.expander(f"{step.iteration}. {step.action}"):
                st.write(step.reason)
                st.code(json.dumps(step.action_input, indent=2), language="json")
                st.caption(step.observation)
    else:
        st.caption("Send a message to see the ReAct tool loop.")

    st.divider()
    st.subheader("Scratchpad")
    if last_result:
        st.json(last_result.scratchpad)
    else:
        st.caption("The scratchpad will appear after the agent handles a message.")

    st.divider()
    st.subheader("Last Retrieval")
    if last_result:
        ticket_id = last_result.ticket_id
        ticket = last_result.ticket
        snippets = last_result.snippets

        st.write("Ticket reference")
        st.code(ticket_id or "None detected", language="text")

        if ticket:
            st.write("Ticket details")
            if last_result.created_ticket:
                st.success("Created during this chat")
            st.json(
                {
                    "id": ticket.id,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "summary": ticket.summary,
                    "product_area": ticket.product_area,
                    "last_updated": ticket.last_updated,
                }
            )
        elif ticket_id:
            st.info("Ticket reference was detected, but no mock ticket matched it.")

        st.write("KnowledgeBase matches")
        if snippets:
            for snippet in snippets:
                with st.expander(f"{snippet.title} (score {snippet.score})"):
                    st.markdown(snippet.content)
        else:
            st.caption("No KnowledgeBase sections matched the latest message.")
    else:
        st.caption("Send a message to see retrieved context.")

    st.divider()
    st.subheader("Logged Jira Tickets")
    created_tickets = agent.jira.created_tickets()
    if created_tickets:
        for created in created_tickets[-5:]:
            with st.expander(created.id):
                st.json(
                    {
                        "id": created.id,
                        "status": created.status,
                        "priority": created.priority,
                        "summary": created.summary,
                        "product_area": created.product_area,
                        "created": created.created,
                    }
                )
    else:
        st.caption("No new mock Jira tickets have been logged yet.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.session_state.pending_prompt or st.chat_input("Describe the issue or include a ticket like AUTH-1001")
if st.session_state.pending_prompt:
    st.session_state.pending_prompt = None

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.last_query = prompt

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Checking ticket details and KnowledgeBase..."):
            result = agent.run(prompt)
            response = result.answer
        st.markdown(response)

    st.session_state.last_result = result
    st.session_state.messages.append({"role": "assistant", "content": response})
    st.rerun()
