import os
from dotenv import load_dotenv
import hashlib
import uuid
import json
from datetime import datetime

# LangChain
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

# RAG
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from openai import OpenAI
from langchain_core.embeddings import Embeddings
import streamlit as st

# ------------------ SETUP ------------------

os.environ["NVIDIA_API_KEY"] = st.secrets["NVIDIA_API_KEY"]

load_dotenv()

MAX_ITERATIONS = 5
MODEL = "meta/llama-3.1-70b-instruct"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key = os.getenv("NVIDIA_API_KEY")
)

def embed_texts(texts):
    response = client.embeddings.create(
        model="nvidia/llama-nemotron-embed-1b-v2",
        input=texts,
        extra_body={"input_type": "passage"}
    )
    return [item.embedding for item in response.data]


def embed_query(query):
    response = client.embeddings.create(
        model="nvidia/llama-nemotron-embed-1b-v2",
        input=[query],
        extra_body={"input_type": "query"}
    )
    return response.data[0].embedding

class NIMEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return embed_texts(texts)  # your existing function

    def embed_query(self, text):
        return embed_query(text)   # your existing function

# ------------------ TICKET STORAGE ------------------

def load_tickets():
    try:
        with open("tickets.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_tickets(tickets):
    with open("tickets.json", "w") as f:
        json.dump(tickets, f, indent=4)

def generate_ticket_id(email: str) -> str:
    normalized_email = email.strip().lower()
    user_hash = hashlib.sha256(normalized_email.encode()).hexdigest()[:6]
    unique_part = uuid.uuid4().hex[:8]
    return f"TKT-{user_hash}-{unique_part}"

# ------------------ RAG SETUP ------------------

def load_policy_docs(md_text: str):
    headers = [("#", "h1"), ("##", "h2"), ("###", "h3")]

    md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)
    docs = md_splitter.split_text(md_text)

    chunker = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )

    docs = chunker.split_documents(docs)

    for d in docs:
        d.metadata["section"] = " > ".join(
            filter(None, [d.metadata.get("h1"), d.metadata.get("h2"), d.metadata.get("h3")])
        )

    return docs

# ------------------ RAG SETUP (SAFE + CACHED) ------------------

EMBEDDING_CACHE_FILE = "policy_embeddings.json"
QUERY_CACHE_FILE = "query_cache.json"


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


# -------- Load + preprocess documents --------

with open("KnowledgeBase.md", "r") as f:
    policy_text = f.read()

docs = load_policy_docs(policy_text)

texts = [doc.page_content for doc in docs]
metadatas = [doc.metadata for doc in docs]


# -------- Persistent embedding cache --------

cache_data = load_json(EMBEDDING_CACHE_FILE)

if cache_data:
    print("⚡ Loading cached policy embeddings")
    texts = cache_data["texts"]
    embeddings = cache_data["embeddings"]
    metadatas = cache_data["metadatas"]

else:
    print("🔄 Generating embeddings (one-time cost)")
    embeddings = embed_texts(texts)

    save_json(EMBEDDING_CACHE_FILE, {
        "texts": texts,
        "embeddings": embeddings,
        "metadatas": metadatas
    })

# -------- Build FAISS (in-memory, safe) --------

embedding_model = NIMEmbeddings()

vectorstore = FAISS.from_embeddings(
    text_embeddings=list(zip(texts, embeddings)),
    embedding=embedding_model,
    metadatas=metadatas
)

# -------- Query embedding cache --------

query_cache = load_json(QUERY_CACHE_FILE) or {}


def embed_query_cached(query):
    if query in query_cache:
        return query_cache[query]

    embedding = embed_query(query)
    query_cache[query] = embedding
    save_json(QUERY_CACHE_FILE, query_cache)

    return embedding


# -------- Retrieval --------

def retrieve_docs(query: str, k: int = 4):
    query_embedding = embed_query_cached(query)
    return vectorstore.similarity_search_by_vector(query_embedding, k=k)

# ------------------ TOOLS ------------------

@tool
def check_knowledge_base(query: str) -> str:
    """Fetch relevant policy clauses from markdown KB."""
    
    docs = retrieve_docs(query)

    if not docs:
        return "No relevant policy found."

    results = []
    for d in docs:
        section = d.metadata.get("section", "Unknown section")
        results.append(f"[{section}] {d.page_content}")

    return "\n\n".join(results)


@tool
def time_elapsed(start_time: str) -> str:
    """Calculate the time elapsed since start_time."""
    return str(datetime.now() - datetime.fromisoformat(start_time))


@tool
def status_check(ticket_id: str, user_email: str) -> str:
    """Check the status of a ticket."""
    tickets = load_tickets()

    user_tickets = tickets.get(user_email, [])

    for t in user_tickets:
        if t["ticket_id"] == ticket_id:
            return f"Ticket {ticket_id} is {t['status']} (created at {t['created_at']})"

    return f"No matching ticket found for {user_email}."


@tool
def create_ticket(issue_description: str, user_email: str) -> str:
    """Create a support ticket, avoiding duplicates."""

    tickets = load_tickets()
    normalized_issue = issue_description.strip().lower()

    user_tickets = tickets.get(user_email, [])

    # 🔍 Step 1: Check for duplicates
    for t in user_tickets:
        existing_issue = t["issue_description"].strip().lower()

        if normalized_issue == existing_issue:
            return (
                f"Duplicate detected. Existing ticket already open:\n"
                f"{t['ticket_id']} (status: {t['status']})"
            )

    # 🆕 Step 2: Create new ticket if no match
    ticket = {
        "ticket_id": generate_ticket_id(user_email),
        "issue_description": issue_description,
        "created_at": datetime.now().isoformat(),
        "status": "Open"
    }

    if user_email not in tickets:
        tickets[user_email] = []

    tickets[user_email].append(ticket)
    save_tickets(tickets)

    return f"Ticket created: {ticket['ticket_id']}"
# ------------------ AGENT ------------------

def support_agent(user_name: str, query: str, user_email: str, ticket_id: str = '') -> str:
    tools_list = [check_knowledge_base, time_elapsed, status_check, create_ticket]

    chat_model = init_chat_model(MODEL, model_provider="nvidia")
    tools_dict = {t.name: t for t in tools_list}
    llm_with_tools = chat_model.bind_tools(tools_list)

    messages = [
        SystemMessage(
            content=(
                "You are a customer support agent.\n"
                f"User name: {user_name}\n"
                f"User email: {user_email}\n"
                f"Ticket ID: {ticket_id}\n"
                "MANDATORY WORKFLOW:\n"
                "1. ALWAYS call status_check first.\n"
                "2. If ticket exists:\n"
                "   - Call time_elapsed\n"
                "   - Then call check_knowledge_base\n"
                "   - Then respond\n"
                "3. If no ticket exists:\n"
                "   - Call check_knowledge_base\n"
                "   - Then create_ticket\n"
                "STRICT:\n"
                f"- ALWAYS address the user with {user_name} while responding"
                "- Never answer without calling tools\n"
                "- Never fabricate policy\n"
                "- Always base decisions on tool outputs\n"
                "- MUST use check_knowledge_base before any decision\n"
                "- Draft a user friendly response based on tool outputs, never directly use tool outputs as response\n"
                "- If you created a new ticket, include its ID in the response\n"
                "- Do not show your working to the user, only the final response\n"
                "- DO NOT mention any tool calls and tool results in the final response, they are for your internal use only\n"
                """- If you are responding in an email style always add this as a by-line
                Best Regards, \n
                Mohit's Customer Service Agent
                """
            )
        ),
        HumanMessage(content=query)
    ]

    for _ in range(MAX_ITERATIONS):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            return response.content

        for tool_call in response.tool_calls:
            if tool_call["name"] not in tools_dict:
                messages.append(
                    ToolMessage(
                        content=f"Error: Tool '{tool_call['name']}' does not exist.",
                        tool_call_id=tool_call["id"]
                    )
                )
                continue
            
            tool = tools_dict[tool_call["name"]]
            result = tool.invoke(tool_call["args"])
            print(f"Tool called: {tool_call['name']} with args {tool_call['args']} -> Result: {result}")

            messages.append(
                ToolMessage(
                    content=result,
                    tool_call_id=tool_call["id"]
                )
            )

    return "Max iterations reached."

if __name__ == "__main__":
    user_query = "What is the status of my ticket? Ticket id is TKT-728c76-5816210d"
    user_email = "mohithemaprasad@gmail.com"
    print(support_agent(user_query, user_email))
