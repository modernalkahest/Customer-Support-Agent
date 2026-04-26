from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).parent
TICKETS_PATH = BASE_DIR / "data" / "tickets.json"
CREATED_TICKETS_PATH = BASE_DIR / "data" / "created_tickets.json"
SCRATCHPAD_PATH = BASE_DIR / "data" / "agent_scratchpad.json"
KB_PATH = BASE_DIR / "data" / "knowledge_base.md"
TICKET_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "can",
    "customer",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "my",
    "of",
    "or",
    "the",
    "to",
    "was",
    "with",
}


@dataclass(frozen=True)
class Ticket:
    id: str
    status: str
    priority: str
    summary: str
    customer: str
    created: str
    last_updated: str
    product_area: str
    latest_note: str
    recommended_next_step: str


@dataclass(frozen=True)
class KnowledgeSnippet:
    title: str
    content: str
    score: int


@dataclass(frozen=True)
class AgentStep:
    iteration: int
    reason: str
    action: str
    action_input: dict[str, Any]
    observation: str


@dataclass(frozen=True)
class AgentResult:
    answer: str
    ticket_id: str | None
    ticket: Ticket | None
    created_ticket: bool
    updated_knowledge_base: bool
    snippets: list[KnowledgeSnippet]
    steps: list[AgentStep]
    scratchpad: dict[str, Any]


class MockJiraClient:
    def __init__(
        self,
        seed_path: Path = TICKETS_PATH,
        created_path: Path = CREATED_TICKETS_PATH,
    ) -> None:
        self.seed_path = seed_path
        self.created_path = created_path
        records = self._load_seed_records()
        self._tickets = {record["id"]: Ticket(**record) for record in records}
        self._created_count = self._highest_created_ticket_number()

    def get(self, ticket_id: str | None) -> Ticket | None:
        if not ticket_id:
            return None
        return self._tickets.get(ticket_id.upper())

    def create_issue(self, customer_message: str, source_ticket_id: str | None = None) -> Ticket:
        self._created_count += 1
        ticket_id = f"SUP-{5000 + self._created_count}"
        product_area = infer_product_area(customer_message)
        summary = summarize_issue(customer_message, product_area)
        priority = infer_priority(customer_message, product_area)
        today = date.today().isoformat()
        note_parts = ["Created by support agent from customer chat."]
        if source_ticket_id:
            note_parts.append(f"Customer referenced unknown ticket {source_ticket_id}.")

        ticket = Ticket(
            id=ticket_id,
            status="Open",
            priority=priority,
            summary=summary,
            customer="Chat customer",
            created=today,
            last_updated=today,
            product_area=product_area,
            latest_note=" ".join(note_parts),
            recommended_next_step=recommend_next_step(product_area),
        )
        self._tickets[ticket.id] = ticket
        self._append_ticket_to_system_of_record(ticket)
        self._log_created_ticket(ticket)
        return ticket

    def created_tickets(self) -> list[Ticket]:
        return [
            ticket
            for ticket in self._tickets.values()
            if ticket.id.startswith("SUP-")
        ]

    def _load_seed_records(self) -> list[dict[str, Any]]:
        if not self.seed_path.exists():
            return []
        try:
            records = json.loads(self.seed_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return records if isinstance(records, list) else []

    def _load_created_records(self) -> list[dict[str, Any]]:
        if not self.created_path.exists():
            return []
        try:
            records = json.loads(self.created_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return records if isinstance(records, list) else []

    def _append_ticket_to_system_of_record(self, ticket: Ticket) -> None:
        records = self._load_seed_records()
        ticket_record = asdict(ticket)
        for index, record in enumerate(records):
            if record.get("id") == ticket.id:
                records[index] = ticket_record
                break
        else:
            records.append(ticket_record)

        self.seed_path.parent.mkdir(parents=True, exist_ok=True)
        self.seed_path.write_text(
            json.dumps(records, indent=2) + "\n",
            encoding="utf-8",
        )

    def _log_created_ticket(self, ticket: Ticket) -> None:
        records = self._load_created_records()
        records.append(asdict(ticket))
        self.created_path.parent.mkdir(parents=True, exist_ok=True)
        self.created_path.write_text(
            json.dumps(records, indent=2) + "\n",
            encoding="utf-8",
        )

    def _highest_created_ticket_number(self) -> int:
        highest = 5000
        for ticket_id in self._tickets:
            match = re.fullmatch(r"SUP-(\d+)", ticket_id)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest - 5000


class AgentScratchpad:
    def __init__(self, path: Path = SCRATCHPAD_PATH) -> None:
        self.path = path
        self.notes: dict[str, Any] = {}

    def start(self, query: str) -> None:
        self.notes = {
            "customer_message": query,
            "ticket_reference": None,
            "ticket_found": False,
            "ticket_logged": False,
            "knowledge_base_matches": [],
            "knowledge_base_gap": False,
            "knowledge_base_updated": False,
            "decisions": [],
            "observations": [],
        }
        self.persist()

    def observe(self, action: str, observation: str) -> None:
        self.notes.setdefault("observations", []).append(
            {"action": action, "observation": observation}
        )
        self.persist()

    def decide(self, decision: str, value: bool, reason: str) -> None:
        self.notes.setdefault("decisions", []).append(
            {"decision": decision, "value": value, "reason": reason}
        )
        self.notes[decision] = value
        self.persist()

    def set_value(self, key: str, value: Any) -> None:
        self.notes[key] = value
        self.persist()

    def should_log_ticket(self) -> bool:
        return bool(self.notes.get("should_log_ticket"))

    def should_update_knowledge_base(self) -> bool:
        return bool(self.notes.get("should_update_knowledge_base"))

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.notes, indent=2) + "\n", encoding="utf-8")


class KnowledgeBase:
    def __init__(self, path: Path = KB_PATH) -> None:
        self.path = path
        self._sections = self._load_sections(path.read_text(encoding="utf-8"))

    def search(self, query: str, ticket: Ticket | None = None, limit: int = 2) -> list[KnowledgeSnippet]:
        query_terms = set(_tokenize(query))
        if ticket:
            query_terms.update(_tokenize(ticket.summary))
            query_terms.update(_tokenize(ticket.product_area))

        scored: list[KnowledgeSnippet] = []
        for title, content in self._sections:
            section_terms = set(_tokenize(f"{title} {content}"))
            score = len(query_terms & section_terms)
            if score > 0:
                scored.append(KnowledgeSnippet(title=title, content=content.strip(), score=score))

        minimum_score = 2 if ticket else 1
        filtered = [item for item in scored if item.score >= minimum_score]
        return sorted(filtered, key=lambda item: item.score, reverse=True)[:limit]

    def add_article(self, query: str, ticket: Ticket | None = None) -> KnowledgeSnippet:
        product_area = ticket.product_area if ticket else infer_product_area(query)
        title = f"{product_area} generated guidance"
        guidance = recommend_next_step(product_area)
        section = (
            f"\n## {title}\n\n"
            f"When a customer asks about this kind of issue:\n\n"
            f"- Capture the customer's exact symptoms and any ticket reference they provided.\n"
            f"- Confirm product area: {product_area}.\n"
            f"- Recommended next step: {guidance}\n"
            f"- If the issue remains unresolved, keep the Jira ticket open and route it to {product_area} support.\n"
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(section)
        self._sections = self._load_sections(self.path.read_text(encoding="utf-8"))
        return KnowledgeSnippet(title=title, content=section.strip(), score=1)

    @staticmethod
    def _load_sections(markdown: str) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        current_title = "General"
        current_lines: list[str] = []

        for line in markdown.splitlines():
            if line.startswith("## "):
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines)))
                current_title = line.removeprefix("## ").strip()
                current_lines = []
            elif not line.startswith("# "):
                current_lines.append(line)

        if current_lines:
            sections.append((current_title, "\n".join(current_lines)))

        return sections


class SupportAgent:
    def __init__(self) -> None:
        self.jira = MockJiraClient()
        self.ticket_store = self.jira
        self.knowledge_base = KnowledgeBase()
        self.scratchpad = AgentScratchpad()
        self.llm = self._build_llm()

    def answer(self, query: str) -> str:
        return self.run(query).answer

    def run(self, query: str, max_iterations: int = 7) -> AgentResult:
        ticket_id: str | None = None
        ticket: Ticket | None = None
        snippets: list[KnowledgeSnippet] = []
        steps: list[AgentStep] = []
        created_ticket = False
        updated_knowledge_base = False
        ticket_reference_checked = False
        ticket_lookup_done = False
        ticket_creation_done = False
        kb_search_done = False
        kb_update_done = False
        self.scratchpad.start(query)

        for iteration in range(1, max_iterations + 1):
            decision = self._choose_react_action(
                query=query,
                ticket_reference_checked=ticket_reference_checked,
                ticket_id=ticket_id,
                ticket_lookup_done=ticket_lookup_done,
                ticket_found=ticket is not None,
                ticket_creation_done=ticket_creation_done,
                kb_search_done=kb_search_done,
                kb_update_done=kb_update_done,
                scratchpad=self.scratchpad.notes,
                steps=steps,
            )
            action = decision["action"]
            action_input = decision.get("action_input", {})
            reason = decision.get("reason", "Choose the next support action.")

            if action == "extract_ticket_reference":
                ticket_id = extract_ticket_id(query)
                ticket_reference_checked = True
                observation = f"Detected ticket reference {ticket_id}." if ticket_id else "No ticket reference detected."
                self.scratchpad.set_value("ticket_reference", ticket_id)
                if not ticket_id:
                    self.scratchpad.decide(
                        "should_log_ticket",
                        True,
                        "No ticket reference was provided, so a new Jira ticket is needed.",
                    )
                steps.append(
                    AgentStep(
                        iteration=iteration,
                        reason=reason,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                    )
                )
                self.scratchpad.observe(action, observation)
                continue

            if action == "retrieve_ticket":
                ticket = self.ticket_store.get(ticket_id)
                ticket_lookup_done = True
                observation = (
                    f"Retrieved ticket {ticket.id}: {ticket.summary}."
                    if ticket
                    else f"Ticket {ticket_id} was not found in the mock System of Record."
                )
                self.scratchpad.set_value("ticket_found", ticket is not None)
                self.scratchpad.decide(
                    "should_log_ticket",
                    ticket is None,
                    "The referenced ticket was not found." if ticket is None else "An existing ticket was found.",
                )
                steps.append(
                    AgentStep(
                        iteration=iteration,
                        reason=reason,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                    )
                )
                self.scratchpad.observe(action, observation)
                continue

            if action == "create_ticket":
                source_ticket_id = ticket_id if ticket_lookup_done and ticket is None else None
                ticket = self.jira.create_issue(customer_message=query, source_ticket_id=source_ticket_id)
                ticket_id = ticket.id
                created_ticket = True
                ticket_creation_done = True
                ticket_lookup_done = True
                observation = f"Created Jira issue {ticket.id}: {ticket.summary}."
                self.scratchpad.set_value("ticket_reference", ticket.id)
                self.scratchpad.set_value("ticket_logged", True)
                self.scratchpad.set_value("ticket_found", True)
                steps.append(
                    AgentStep(
                        iteration=iteration,
                        reason=reason,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                    )
                )
                self.scratchpad.observe(action, observation)
                continue

            if action == "search_knowledge_base":
                snippets = self.knowledge_base.search(query=query, ticket=ticket)
                kb_search_done = True
                if snippets:
                    titles = ", ".join(snippet.title for snippet in snippets)
                    observation = f"Found relevant KnowledgeBase section(s): {titles}."
                else:
                    observation = "No strongly relevant KnowledgeBase section was found."
                self.scratchpad.set_value("knowledge_base_matches", [snippet.title for snippet in snippets])
                self.scratchpad.set_value("knowledge_base_gap", not bool(snippets))
                self.scratchpad.decide(
                    "should_update_knowledge_base",
                    not bool(snippets),
                    "No relevant KnowledgeBase article matched this query."
                    if not snippets
                    else "KnowledgeBase already contains relevant guidance.",
                )
                steps.append(
                    AgentStep(
                        iteration=iteration,
                        reason=reason,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                    )
                )
                self.scratchpad.observe(action, observation)
                continue

            if action == "update_knowledge_base":
                snippet = self.knowledge_base.add_article(query=query, ticket=ticket)
                snippets = [snippet]
                updated_knowledge_base = True
                kb_update_done = True
                observation = f"Added KnowledgeBase section: {snippet.title}."
                self.scratchpad.set_value("knowledge_base_updated", True)
                steps.append(
                    AgentStep(
                        iteration=iteration,
                        reason=reason,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                    )
                )
                self.scratchpad.observe(action, observation)
                continue

            if action == "final_answer":
                steps.append(
                    AgentStep(
                        iteration=iteration,
                        reason=reason,
                        action=action,
                        action_input=action_input,
                        observation="Final response generated.",
                    )
                )
                self.scratchpad.observe(action, "Final response generated.")
                break

        if not any(step.action == "final_answer" for step in steps):
            steps.append(
                AgentStep(
                    iteration=len(steps) + 1,
                    reason="Reached the iteration limit, so respond with the best available context.",
                    action="final_answer",
                    action_input={},
                    observation="Final response generated.",
                )
            )

        if self.llm:
            answer = self._answer_with_groq(
                query=query,
                ticket_id=ticket_id,
                ticket=ticket,
                created_ticket=created_ticket,
                updated_knowledge_base=updated_knowledge_base,
                snippets=snippets,
            )
        else:
            answer = self._answer_without_llm(
                query=query,
                ticket_id=ticket_id,
                ticket=ticket,
                created_ticket=created_ticket,
                updated_knowledge_base=updated_knowledge_base,
                snippets=snippets,
            )

        return AgentResult(
            answer=answer,
            ticket_id=ticket_id,
            ticket=ticket,
            created_ticket=created_ticket,
            updated_knowledge_base=updated_knowledge_base,
            snippets=snippets,
            steps=steps,
            scratchpad=self.scratchpad.notes,
        )

    def _choose_react_action(
        self,
        query: str,
        ticket_reference_checked: bool,
        ticket_id: str | None,
        ticket_lookup_done: bool,
        ticket_found: bool,
        ticket_creation_done: bool,
        kb_search_done: bool,
        kb_update_done: bool,
        scratchpad: dict[str, Any],
        steps: list[AgentStep],
    ) -> dict[str, Any]:
        if self.llm:
            decision = self._choose_action_with_groq(
                query=query,
                ticket_reference_checked=ticket_reference_checked,
                ticket_id=ticket_id,
                ticket_lookup_done=ticket_lookup_done,
                ticket_found=ticket_found,
                ticket_creation_done=ticket_creation_done,
                kb_search_done=kb_search_done,
                kb_update_done=kb_update_done,
                scratchpad=scratchpad,
                steps=steps,
            )
            if self._is_valid_decision(
                decision=decision,
                ticket_reference_checked=ticket_reference_checked,
                ticket_id=ticket_id,
                ticket_lookup_done=ticket_lookup_done,
                ticket_found=ticket_found,
                ticket_creation_done=ticket_creation_done,
                kb_search_done=kb_search_done,
                kb_update_done=kb_update_done,
                scratchpad=scratchpad,
            ):
                return decision

        return self._choose_action_without_llm(
            query=query,
            ticket_reference_checked=ticket_reference_checked,
            ticket_id=ticket_id,
            ticket_lookup_done=ticket_lookup_done,
            ticket_found=ticket_found,
            ticket_creation_done=ticket_creation_done,
            kb_search_done=kb_search_done,
            kb_update_done=kb_update_done,
            scratchpad=scratchpad,
        )

    def _choose_action_with_groq(
        self,
        query: str,
        ticket_reference_checked: bool,
        ticket_id: str | None,
        ticket_lookup_done: bool,
        ticket_found: bool,
        ticket_creation_done: bool,
        kb_search_done: bool,
        kb_update_done: bool,
        scratchpad: dict[str, Any],
        steps: list[AgentStep],
    ) -> dict[str, Any] | None:
        from langchain_core.messages import HumanMessage, SystemMessage

        step_log = [
            {
                "iteration": step.iteration,
                "action": step.action,
                "action_input": step.action_input,
                "observation": step.observation,
            }
            for step in steps
        ]
        messages = [
            SystemMessage(
                content=(
                    "You are the planner for a ReAct customer support agent. "
                    "Choose exactly one next action. Return only valid JSON with keys "
                    "reason, action, and action_input. Keep reason to one concise sentence. "
                    "Allowed actions: extract_ticket_reference, retrieve_ticket, "
                    "create_ticket, search_knowledge_base, update_knowledge_base, final_answer."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "customer_message": query,
                        "state": {
                            "ticket_reference_checked": ticket_reference_checked,
                            "ticket_id": ticket_id,
                            "ticket_lookup_done": ticket_lookup_done,
                            "ticket_found": ticket_found,
                            "ticket_creation_done": ticket_creation_done,
                            "kb_search_done": kb_search_done,
                            "kb_update_done": kb_update_done,
                            "scratchpad": scratchpad,
                        },
                        "previous_steps": step_log,
                        "policy": [
                            "Extract a ticket reference first.",
                            "Retrieve the ticket if a ticket_id exists and lookup has not been done.",
                            "Create a ticket if no ticket_id exists after extraction.",
                            "Create a ticket if lookup was done and the referenced ticket was not found.",
                            "Search the KnowledgeBase after ticket handling is complete.",
                            "Update the KnowledgeBase if scratchpad says should_update_knowledge_base is true.",
                            "Use final_answer only after KnowledgeBase search is done.",
                        ],
                    },
                    indent=2,
                )
            ),
        ]
        response = self.llm.invoke(messages)
        return _parse_json_object(response.content)

    @staticmethod
    def _choose_action_without_llm(
        query: str,
        ticket_reference_checked: bool,
        ticket_id: str | None,
        ticket_lookup_done: bool,
        ticket_found: bool,
        ticket_creation_done: bool,
        kb_search_done: bool,
        kb_update_done: bool,
        scratchpad: dict[str, Any],
    ) -> dict[str, Any]:
        if not ticket_reference_checked:
            return {
                "reason": "First identify whether the customer supplied a support ticket reference.",
                "action": "extract_ticket_reference",
                "action_input": {"query": query},
            }
        if ticket_id and not ticket_lookup_done:
            return {
                "reason": "A ticket reference is available, so retrieve the System-of-Record details.",
                "action": "retrieve_ticket",
                "action_input": {"ticket_id": ticket_id},
            }
        if not ticket_id and scratchpad.get("should_log_ticket") and not ticket_creation_done:
            return {
                "reason": "No ticket was provided, so create a Jira issue to track the customer's request.",
                "action": "create_ticket",
                "action_input": {"customer_message": query},
            }
        if ticket_id and ticket_lookup_done and scratchpad.get("should_log_ticket") and not ticket_found and not ticket_creation_done:
            return {
                "reason": "The referenced ticket was not found, so create a new Jira issue for this chat.",
                "action": "create_ticket",
                "action_input": {"customer_message": query, "source_ticket_id": ticket_id},
            }
        if not kb_search_done:
            return {
                "reason": "Search the KnowledgeBase using the customer issue and any ticket context.",
                "action": "search_knowledge_base",
                "action_input": {"query": query, "ticket_id": ticket_id},
            }
        if scratchpad.get("should_update_knowledge_base") and not kb_update_done:
            return {
                "reason": "The scratchpad shows a KnowledgeBase gap, so add generated guidance for this query type.",
                "action": "update_knowledge_base",
                "action_input": {"query": query, "ticket_id": ticket_id},
            }
        return {
            "reason": "Ticket and KnowledgeBase context have been gathered, so produce the customer response.",
            "action": "final_answer",
            "action_input": {},
        }

    @staticmethod
    def _is_valid_decision(
        decision: dict[str, Any] | None,
        ticket_reference_checked: bool,
        ticket_id: str | None,
        ticket_lookup_done: bool,
        ticket_found: bool,
        ticket_creation_done: bool,
        kb_search_done: bool,
        kb_update_done: bool,
        scratchpad: dict[str, Any],
    ) -> bool:
        if not decision:
            return False

        action = decision.get("action")
        if action not in {
            "extract_ticket_reference",
            "retrieve_ticket",
            "create_ticket",
            "search_knowledge_base",
            "update_knowledge_base",
            "final_answer",
        }:
            return False

        if action == "extract_ticket_reference":
            return not ticket_reference_checked
        if action == "retrieve_ticket":
            return bool(ticket_id) and not ticket_lookup_done
        if action == "create_ticket":
            return ticket_reference_checked and not ticket_creation_done and (
                scratchpad.get("should_log_ticket")
                and (not ticket_id or (ticket_lookup_done and not ticket_found))
            )
        if action == "search_knowledge_base":
            return (
                ticket_reference_checked
                and (ticket_creation_done or (bool(ticket_id) and ticket_lookup_done and ticket_found))
                and not kb_search_done
            )
        if action == "update_knowledge_base":
            return kb_search_done and scratchpad.get("should_update_knowledge_base") and not kb_update_done
        if action == "final_answer":
            return kb_search_done and (not scratchpad.get("should_update_knowledge_base") or kb_update_done)

        return False

    @staticmethod
    def _build_llm():
        if not os.getenv("GROQ_API_KEY"):
            return None

        try:
            from langchain_groq import ChatGroq
        except ImportError:
            return None

        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0.2,
        )

    def _answer_with_groq(
        self,
        query: str,
        ticket_id: str | None,
        ticket: Ticket | None,
        created_ticket: bool,
        updated_knowledge_base: bool,
        snippets: list[KnowledgeSnippet],
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(
                content=(
                    "You are a careful customer support agent. Use the ticket details and "
                    "KnowledgeBase context provided. Be empathetic, concise, and practical. "
                    "Do not invent ticket details. If no ticket is available, ask for one only "
                    "when it would materially help."
                )
            ),
            HumanMessage(
                content=build_context_prompt(
                    query=query,
                    ticket_id=ticket_id,
                    ticket=ticket,
                    created_ticket=created_ticket,
                    updated_knowledge_base=updated_knowledge_base,
                    snippets=snippets,
                )
            ),
        ]
        response = self.llm.invoke(messages)
        return response.content

    @staticmethod
    def _answer_without_llm(
        query: str,
        ticket_id: str | None,
        ticket: Ticket | None,
        created_ticket: bool,
        updated_knowledge_base: bool,
        snippets: list[KnowledgeSnippet],
    ) -> str:
        lines = ["Thanks for reaching out. I can help with that."]

        if ticket_id and ticket and created_ticket:
            lines.append(
                f"I created a new support ticket for this chat: {ticket.id}. "
                f"It is currently {ticket.status} with {ticket.priority.lower()} priority."
            )
            lines.append(f"Summary: {ticket.summary}")
            lines.append(f"Recommended next step: {ticket.recommended_next_step}")
        elif ticket_id and ticket:
            lines.append(
                f"I found ticket {ticket.id}: {ticket.summary}. "
                f"It is currently {ticket.status} with {ticket.priority.lower()} priority."
            )
            lines.append(f"Latest note: {ticket.latest_note}")
            lines.append(f"Recommended next step: {ticket.recommended_next_step}")
        elif ticket_id:
            lines.append(
                f"I could not find ticket {ticket_id} in the support system. "
                "Please check the reference or share more details about the issue."
            )
        else:
            lines.append(
                "I do not see a ticket reference in your message, so I will start with general troubleshooting."
            )

        if snippets:
            lines.append("Relevant KnowledgeBase guidance:")
            for snippet in snippets:
                first_bullet = next(
                    (line.strip("- ") for line in snippet.content.splitlines() if line.strip().startswith("- ")),
                    snippet.content.splitlines()[0].strip() if snippet.content else "",
                )
                lines.append(f"- {snippet.title}: {first_bullet}")

        if updated_knowledge_base:
            lines.append("I also added a new KnowledgeBase section for this type of question.")

        if not ticket and "log" in query.lower():
            lines.append(
                "Please try an incognito/private window and clear site cookies. "
                "If you recently reset your password, close all app tabs before trying again."
            )

        return "\n".join(lines)


def extract_ticket_id(query: str) -> str | None:
    match = TICKET_PATTERN.search(query)
    return match.group(0) if match else None


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None


def build_context_prompt(
    query: str,
    ticket_id: str | None,
    ticket: Ticket | None,
    created_ticket: bool,
    updated_knowledge_base: bool,
    snippets: Iterable[KnowledgeSnippet],
) -> str:
    ticket_context = "No ticket reference was provided."
    if ticket_id and not ticket:
        ticket_context = f"Customer provided ticket {ticket_id}, but it was not found."
    elif ticket:
        ticket_context = json.dumps(
            {"created_during_chat": created_ticket, **ticket.__dict__},
            indent=2,
        )

    kb_context = "\n\n".join(
        f"Section: {snippet.title}\n{snippet.content}" for snippet in snippets
    ) or "No relevant KnowledgeBase article found."

    return f"""
Customer message:
{query}

Ticket context:
{ticket_context}

KnowledgeBase context:
{kb_context}

KnowledgeBase updated during this chat:
{updated_knowledge_base}

Write the support agent response.
""".strip()


def infer_product_area(message: str) -> str:
    tokens = set(_tokenize(message))
    if tokens & {"login", "password", "mfa", "auth", "authentication", "signin"}:
        return "Authentication"
    if tokens & {"bill", "billing", "charge", "invoice", "refund", "payment"}:
        return "Billing"
    if tokens & {"sync", "import", "integration", "connector", "backfill"}:
        return "Integrations"
    return "General Support"


def infer_priority(message: str, product_area: str) -> str:
    tokens = set(_tokenize(message))
    if product_area == "Authentication" or tokens & {"blocked", "cannot", "locked", "urgent"}:
        return "High"
    if product_area == "Billing":
        return "Medium"
    return "Low"


def summarize_issue(message: str, product_area: str) -> str:
    cleaned = " ".join(message.strip().split())
    if len(cleaned) > 90:
        cleaned = f"{cleaned[:87]}..."
    if product_area == "General Support":
        return f"General support request: {cleaned}"
    return f"{product_area} support request: {cleaned}"


def recommend_next_step(product_area: str) -> str:
    if product_area == "Authentication":
        return "Ask the customer to try incognito mode, clear site cookies, and confirm whether MFA appears."
    if product_area == "Billing":
        return "Check payment status and escalate to Billing Operations if duplicate posted charges are confirmed."
    if product_area == "Integrations":
        return "Check connector status and latest successful sync timestamp before asking the customer to reconnect."
    return "Collect additional details, confirm impact, and route to the appropriate support queue."


def _tokenize(text: str) -> list[str]:
    aliases = {
        "charged": "charge",
        "charges": "charge",
        "imported": "import",
        "logging": "login",
        "logged": "login",
    }
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [aliases.get(token, token) for token in tokens if token not in STOP_WORDS]


def main(argv: list[str]) -> int:
    agent = SupportAgent()

    if len(argv) > 1:
        print(agent.answer(" ".join(argv[1:])))
        return 0

    print("Customer Support Agent. Type 'exit' to quit.")
    while True:
        try:
            query = input("\nCustomer: ").strip()
        except EOFError:
            break

        if query.lower() in {"exit", "quit"}:
            break

        if not query:
            continue

        print(f"\nAgent: {agent.answer(query)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
