import streamlit as st
import json
import os
from support_agent import support_agent

st.set_page_config(page_title="Customer Support Agent", layout="wide")

# ------------------ HELPERS ------------------

def load_tickets():
    if not os.path.exists("tickets.json"):
        return {}
    with open("tickets.json", "r") as f:
        return json.load(f)

# ------------------ SESSION ------------------

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "user_email" not in st.session_state:
    st.session_state.user_email = ""

if "user_name" not in st.session_state:
    st.session_state.user_name = ""

if "selected_ticket" not in st.session_state:
    st.session_state.selected_ticket = ""

# ------------------ HEADER ------------------

st.title("🛠️ AI Customer Support Agent")

# ------------------ NAME + EMAIL GATE ------------------

if not st.session_state.user_email:
    st.subheader("🔒 Enter your details to continue")

    name_input = st.text_input("Name", placeholder="John Doe")
    email_input = st.text_input("Email", placeholder="customer@example.com")

    if st.button("Start Session"):
        if name_input.strip() and email_input.strip():
            st.session_state.user_name = name_input.strip()
            st.session_state.user_email = email_input.strip().lower()

            # Reset session state
            st.session_state.chat_history = []
            st.session_state.selected_ticket = ""

            st.rerun()
        else:
            st.warning("Both name and email are required.")

    st.stop()

# ------------------ SIDEBAR ------------------

with st.sidebar:
    st.header("👤 User")
    st.write(f"**Name:** {st.session_state.user_name}")
    st.write(f"**Email:** {st.session_state.user_email}")

    st.markdown("---")

    # ------------------ LIVE TICKETS ------------------

    st.subheader("🎫 Your Tickets")

    tickets = load_tickets()
    user_tickets = tickets.get(st.session_state.user_email, [])

    if not user_tickets:
        st.info("No tickets yet.")
        st.session_state.selected_ticket = ""
    else:
        options = ["➕ Create New Ticket"]
        ticket_map = {}

        for t in reversed(user_tickets):
            label = f"{t['ticket_id']} | {t['status']}"
            options.append(label)
            ticket_map[label] = t

        selected_option = st.radio("Select context", options)

        if selected_option == "➕ Create New Ticket":
            st.session_state.selected_ticket = ""
        else:
            selected_ticket = ticket_map[selected_option]
            st.session_state.selected_ticket = selected_ticket["ticket_id"]

            # Show context
            st.markdown("### 📄 Ticket Details")
            st.markdown(f"""
            **Issue:** {selected_ticket['issue_description']}  
            **Status:** `{selected_ticket['status']}`  
            **Created:** {selected_ticket['created_at']}
            """)

    # ------------------ LOGOUT ------------------

    st.markdown("---")

    if st.button("🚪 Logout"):
        st.session_state.user_email = ""
        st.session_state.user_name = ""
        st.session_state.chat_history = []
        st.session_state.selected_ticket = ""
        st.rerun()

# ------------------ CHAT HEADER ------------------

col1, col2 = st.columns([6, 1])

with col1:
    st.subheader(f"💬 Chat — {st.session_state.user_name}")

with col2:
    if st.button("🧹 Clear"):
        st.session_state.chat_history = []
        st.rerun()

# ------------------ CONTEXT BANNER ------------------

if st.session_state.selected_ticket:
    st.info(f"Continuing Ticket: {st.session_state.selected_ticket}")
else:
    st.info("Creating a new ticket")

# ------------------ CHAT DISPLAY ------------------

for chat in st.session_state.chat_history:
    with st.chat_message(chat["role"]):
        st.markdown(chat["content"])

# ------------------ INPUT ------------------

user_query = st.chat_input("Describe your issue...")

if user_query:
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_query
    })

    with st.chat_message("user"):
        st.markdown(user_query)

    # ------------------ AGENT CALL ------------------

    with st.chat_message("assistant"):
        with st.spinner("Processing..."):
            try:
                response = support_agent(
                    user_name = st.session_state.user_name,
                    query=user_query,
                    user_email=st.session_state.user_email,
                    ticket_id=st.session_state.selected_ticket
                )
            except Exception as e:
                response = f"Error: {str(e)}"

        st.markdown(response)

    st.session_state.chat_history.append({
        "role": "assistant",
        "content": response
    })

    st.rerun()
