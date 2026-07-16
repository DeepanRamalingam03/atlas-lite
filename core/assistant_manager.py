from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clients.base_client import BaseClient
from core.intent_router import Intent, IntentRouter, RouteDecision
from core.memory_store import PersistentMemoryStore
from services.code_validator import PythonCodeValidator
from services.constitution_loader import ConstitutionLoader
from services.review_parser import ReviewParser
from services.project.project_scanner import ProjectScanner
from services.project.project_context_builder import ProjectContextBuilder
from services.project.project_knowledge_service import ProjectKnowledgeService
from services.project.relevant_file_context_service import RelevantFileContextService


@dataclass(slots=True)
class AtlasManagerResponse:
    answer: str
    route: RouteDecision
    iterations: int
    manager_review: str


class AtlasAssistantManager:
    """
    Central Atlas manager.

    Every request is governed by the Atlas Constitution.

    Coding flow:
    1. Load and enforce the Constitution.
    2. Gemini worker generates the answer.
    3. Local Python validator checks syntax.
    4. OpenAI manager reviews correctness and completeness.
    5. Rejected answers return to Gemini with fix instructions.
    6. Only manager-approved output reaches the user.
    """

    CODING_INTENTS = {
        Intent.CODING,
        Intent.TESTING,
    }

    def __init__(
        self,
        clients: dict[str, BaseClient],
        router: IntentRouter,
        memory: PersistentMemoryStore,
        code_validator: PythonCodeValidator | None = None,
        constitution_loader: ConstitutionLoader | None = None,
        project_scanner: ProjectScanner | None = None,
        project_context_builder: ProjectContextBuilder | None = None,
        project_knowledge_service: ProjectKnowledgeService | None = None,
        relevant_file_context_service: RelevantFileContextService | None = None,
        project_root: str | Path = ".",
        max_code_retries: int = 2,
    ) -> None:
        if "openai" not in clients:
            raise ValueError(
                "OpenAI manager client must be configured."
            )

        if "gemini" not in clients:
            raise ValueError(
                "Gemini worker client must be configured."
            )

        if max_code_retries < 0:
            raise ValueError(
                "max_code_retries cannot be negative."
            )

        self.clients = clients
        self.router = router
        self.memory = memory
        self.code_validator = (
            code_validator or PythonCodeValidator()
        )
        self.constitution_loader = (
            constitution_loader or ConstitutionLoader()
        )
        self.review_parser = ReviewParser()
        self.project_scanner = project_scanner or ProjectScanner()
        self.project_root = Path(project_root).resolve()
        self.project_context_builder = (
            project_context_builder
            or ProjectContextBuilder(
                constitution_loader=self.constitution_loader,
                scanner=self.project_scanner,
            )
        )
        self.project_knowledge_service = (
            project_knowledge_service
            or ProjectKnowledgeService(
                context_builder=self.project_context_builder,
            )
        )
        self.relevant_file_context_service = (
            relevant_file_context_service
            or RelevantFileContextService(
                project_root=self.project_root,
            )
        )
        self.max_code_retries = max_code_retries

        self.project_context = self.project_scanner.scan(
            self.project_root
        ).strip()

        if not self.project_context:
            raise RuntimeError(
                "Atlas project context is empty or unavailable."
            )

        self.constitution = (
            self.constitution_loader.load_all().strip()
        )

        if not self.constitution:
            raise RuntimeError(
                "Atlas Constitution is empty or unavailable."
            )

        self.project_knowledge = ""
        self.project_knowledge_fingerprint = ""
        self.project_knowledge_changed = False

        self.relevant_file_context = (
            "No relevant project files were selected "
            "for this request."
        )
        self.relevant_file_paths: tuple[str, ...] = ()

        self._refresh_project_knowledge()

    def ask(
        self,
        user_id: int,
        request: str,
    ) -> AtlasManagerResponse:
        cleaned_request = request.strip()

        if not cleaned_request:
            raise ValueError("Request cannot be empty.")

        self._refresh_project_knowledge()
        self._refresh_relevant_file_context(
            cleaned_request
        )

        route = self.router.route(cleaned_request)
        history = self.memory.get_history(user_id)

        if route.intent in self.CODING_INTENTS:
            result = self._execute_worker_review_cycle(
                request=cleaned_request,
                route=route,
                history=history,
            )
        else:
            result = self._execute_manager_request(
                request=cleaned_request,
                route=route,
                history=history,
            )

        self.memory.append_exchange(
            user_id=user_id,
            user_message=cleaned_request,
            assistant_message=result.answer,
        )

        return result

    def _execute_manager_request(
        self,
        request: str,
        route: RouteDecision,
        history: list[Any],
    ) -> AtlasManagerResponse:
        manager = self.clients["openai"]

        prompt = self._build_manager_prompt(
            request=request,
            route=route,
            history=history,
        )

        answer = manager.generate(prompt).strip()

        if not answer:
            raise RuntimeError(
                "OpenAI manager returned an empty response."
            )

        return AtlasManagerResponse(
            answer=answer,
            route=route,
            iterations=1,
            manager_review=(
                "Direct OpenAI manager response governed "
                "by the Atlas Constitution."
            ),
        )

    def _execute_worker_review_cycle(
        self,
        request: str,
        route: RouteDecision,
        history: list[Any],
    ) -> AtlasManagerResponse:
        worker = self.clients["gemini"]
        manager = self.clients["openai"]

        worker_prompt = self._build_worker_prompt(
            request=request,
            route=route,
            history=history,
        )

        total_attempts = self.max_code_retries + 1
        last_review = ""
        last_error = ""

        for iteration in range(1, total_attempts + 1):
            worker_answer = worker.generate(
                worker_prompt
            ).strip()

            if not worker_answer:
                last_error = (
                    "Gemini worker returned an empty response."
                )

                worker_prompt = self._build_worker_retry_prompt(
                    original_request=request,
                    previous_answer="No response.",
                    validation_error=last_error,
                    manager_review=last_review,
                )
                continue

            validation = (
                self.code_validator.validate_response(
                    worker_answer
                )
            )

            if not validation.valid:
                last_error = (
                    validation.error
                    or "Python validation failed."
                )

                worker_prompt = self._build_worker_retry_prompt(
                    original_request=request,
                    previous_answer=worker_answer,
                    validation_error=last_error,
                    manager_review=last_review,
                )
                continue

            review_prompt = self._build_review_prompt(
                request=request,
                worker_answer=worker_answer,
                validation_result=(
                    "Local Python syntax validation passed."
                ),
            )

            raw_review = manager.generate(
                review_prompt
            ).strip()

            if not raw_review:
                last_error = (
                    "OpenAI manager returned an empty review."
                )

                worker_prompt = self._build_worker_retry_prompt(
                    original_request=request,
                    previous_answer=worker_answer,
                    validation_error=last_error,
                    manager_review=(
                        "No manager review received."
                    ),
                )
                continue

            last_review = raw_review

            try:
                parsed_review = self.review_parser.parse(
                    raw_review
                )
            except ValueError as exc:
                last_error = (
                    "OpenAI manager returned an invalid review "
                    f"format: {exc}"
                )

                worker_prompt = self._build_worker_retry_prompt(
                    original_request=request,
                    previous_answer=worker_answer,
                    validation_error=last_error,
                    manager_review=raw_review,
                )
                continue

            if parsed_review.approved:
                return AtlasManagerResponse(
                    answer=worker_answer,
                    route=route,
                    iterations=iteration,
                    manager_review=raw_review,
                )

            last_error = (
                parsed_review.fix_instruction
                or parsed_review.reason
                or (
                    "OpenAI manager rejected the worker "
                    "response."
                )
            )

            worker_prompt = self._build_worker_retry_prompt(
                original_request=request,
                previous_answer=worker_answer,
                validation_error=(
                    "Local syntax validation passed, but "
                    "the OpenAI manager rejected the response."
                ),
                manager_review=raw_review,
            )

        raise RuntimeError(
            "Atlas could not produce manager-approved code after "
            f"{total_attempts} attempts. Last issue: {last_error}"
        )


    def _refresh_project_knowledge(self) -> None:
        result = self.project_knowledge_service.refresh(
            self.project_root
        )

        cleaned_context = result.context.strip()

        if not cleaned_context:
            raise RuntimeError(
                "Atlas project knowledge service returned "
                "empty context."
            )

        self.project_knowledge = cleaned_context
        self.project_knowledge_fingerprint = (
            result.fingerprint
        )
        self.project_knowledge_changed = result.changed


    def _refresh_relevant_file_context(
        self,
        request: str,
    ) -> None:
        result = self.relevant_file_context_service.build(
            request
        )

        cleaned_context = result.rendered_context.strip()

        if not cleaned_context:
            cleaned_context = (
                "No relevant project files were selected "
                "for this request."
            )

        self.relevant_file_context = cleaned_context
        self.relevant_file_paths = tuple(
            selected_file.path
            for selected_file in result.selected_files
        )

    def clear_memory(self, user_id: int) -> None:
        self.memory.clear(user_id)

    def history_size(self, user_id: int) -> int:
        return self.memory.history_size(user_id)

    @staticmethod
    def _history_text(history: list[Any]) -> str:
        if not history:
            return "No previous conversation."

        return "\n".join(
            f"{turn.role}: {turn.content}"
            for turn in history
        )

    def _constitution_section(self) -> str:
        return (
            "ATLAS CONSTITUTION — AUTHORITATIVE\n"
            "==================================\n"
            "The following repository Constitution is the "
            "authoritative source of truth.\n"
            "You must obey it.\n"
            "Do not silently change the vision, architecture, "
            "roles, constraints, or approved direction.\n"
            "When the user explicitly requests a constitutional "
            "or architecture change, explain that approval and "
            "documentation are required.\n\n"
            f"{self.constitution}"
        )


    def _project_context_section(self) -> str:
        return (
            "ATLAS PROJECT FILE INDEX\n"
            "========================\n"
            "This is the current repository file index.\n"
            "Use it to understand the existing project structure.\n"
            "Do not claim that file contents were inspected when only "
            "the file index is available.\n\n"
            f"{self.project_context}"
        )


    def _project_knowledge_section(self) -> str:
        return (
            "ATLAS PROJECT KNOWLEDGE — AUTHORITATIVE\n"
            "=======================================\n"
            "This context contains the Constitution, repository "
            "file structure, and statically extracted Python "
            "symbols and imports.\n"
            "Use it to understand the existing project before "
            "planning, implementing, or reviewing changes.\n"
            "Do not claim full file contents were inspected when "
            "only structural index information is available.\n"
            f"Knowledge fingerprint: "
            f"{self.project_knowledge_fingerprint}\n"
            f"Knowledge changed during last refresh: "
            f"{self.project_knowledge_changed}\n\n"
            f"{self.project_knowledge}"
        )


    def _relevant_file_context_section(self) -> str:
        selected_paths = (
            ", ".join(self.relevant_file_paths)
            if self.relevant_file_paths
            else "None"
        )

        return (
            "REQUEST-SPECIFIC PROJECT FILES\n"
            "==============================\n"
            "The following files were selected deterministically "
            "for the current user request and safely read from "
            "the repository.\n"
            "Treat these file contents as more specific than the "
            "structural project index.\n"
            "Do not invent contents for files that are not shown.\n"
            f"Selected paths: {selected_paths}\n\n"
            f"{self.relevant_file_context}"
        )

    def _build_manager_prompt(
        self,
        request: str,
        route: RouteDecision,
        history: list[Any],
    ) -> str:
        return (
            f"{self._project_knowledge_section()}\n\n"
            f"{self._relevant_file_context_section()}\n\n"
            "ACTIVE ROLE\n"
            "===========\n"
            "You are the OpenAI Manager of Atlas Lite.\n"
            "You protect the approved Atlas architecture and "
            "product direction.\n"
            "Answer the user directly with accurate technical "
            "judgment.\n"
            "Never claim execution unless an Atlas tool actually "
            "executed the action.\n\n"
            "ROUTE\n"
            "=====\n"
            f"Intent: {route.intent.value}\n"
            f"Provider: {route.provider}\n"
            f"Reason: {route.reason}\n\n"
            "MEMORY\n"
            "======\n"
            f"{self._history_text(history)}\n\n"
            "USER REQUEST\n"
            "============\n"
            f"{request}\n"
        )

    def _build_worker_prompt(
        self,
        request: str,
        route: RouteDecision,
        history: list[Any],
    ) -> str:
        return (
            f"{self._project_knowledge_section()}\n\n"
            f"{self._relevant_file_context_section()}\n\n"
            "ACTIVE ROLE\n"
            "===========\n"
            "You are the Gemini Coding Worker of Atlas Lite.\n"
            "You are not authorized to independently change the "
            "product vision or architecture.\n"
            "Follow the approved request and Constitution exactly.\n"
            "Generate a complete, runnable, syntax-correct answer.\n"
            "Verify every line before responding.\n"
            "Do not include broken examples, placeholders, or "
            "malformed syntax.\n"
            "For Python, use correct operators, signatures, "
            "indentation, imports, and __name__ guards.\n\n"
            "ROUTE\n"
            "=====\n"
            f"Intent: {route.intent.value}\n"
            f"Reason: {route.reason}\n\n"
            "MEMORY\n"
            "======\n"
            f"{self._history_text(history)}\n\n"
            "USER REQUEST\n"
            "============\n"
            f"{request}\n\n"
            "Return the complete final implementation."
        )

    def _build_review_prompt(
        self,
        request: str,
        worker_answer: str,
        validation_result: str,
    ) -> str:
        return (
            f"{self._project_knowledge_section()}\n\n"
            f"{self._relevant_file_context_section()}\n\n"
            "ACTIVE ROLE\n"
            "===========\n"
            "You are the strict OpenAI Manager reviewing a "
            "Gemini worker response for Atlas Lite.\n"
            "Never approve partially correct work.\n"
            "Reject the response if any syntax, runtime, logic, "
            "formatting, completeness, safety, or constitutional "
            "problem exists.\n\n"
            "MANDATORY REVIEW CHECKS\n"
            "=======================\n"
            "- Syntax correctness\n"
            "- Runtime correctness\n"
            "- Mathematical and logical correctness\n"
            "- Correct imports and operators\n"
            "- Correct indentation\n"
            "- Valid example usage\n"
            "- Complete fulfillment of the request\n"
            "- No placeholders or malformed code\n"
            "- No contradiction with the Atlas Constitution\n"
            "- No unauthorized architecture change\n\n"
            "Return exactly this structure:\n\n"
            "DECISION: APPROVED or REJECTED\n\n"
            "REASON:\n"
            "<clear and specific reason>\n\n"
            "FIX_INSTRUCTION:\n"
            "<exact correction, or NONE when approved>\n\n"
            "ORIGINAL USER REQUEST\n"
            "=====================\n"
            f"{request}\n\n"
            "LOCAL VALIDATION\n"
            "================\n"
            f"{validation_result}\n\n"
            "WORKER RESPONSE\n"
            "===============\n"
            f"{worker_answer}\n"
        )

    def _build_worker_retry_prompt(
        self,
        original_request: str,
        previous_answer: str,
        validation_error: str,
        manager_review: str,
    ) -> str:
        return (
            f"{self._project_knowledge_section()}\n\n"
            f"{self._relevant_file_context_section()}\n\n"
            "ACTIVE ROLE\n"
            "===========\n"
            "You are the Gemini Coding Worker of Atlas Lite.\n"
            "Your previous answer was rejected.\n"
            "Generate the complete answer again from scratch.\n"
            "Fix every reported issue.\n"
            "Do not repeat the rejected implementation.\n"
            "Verify syntax, runtime logic, examples, and "
            "constitutional compliance before responding.\n\n"
            "ORIGINAL REQUEST\n"
            "================\n"
            f"{original_request}\n\n"
            "PREVIOUS ANSWER\n"
            "===============\n"
            f"{previous_answer}\n\n"
            "LOCAL VALIDATION RESULT\n"
            "=======================\n"
            f"{validation_error}\n\n"
            "OPENAI MANAGER REVIEW\n"
            "=====================\n"
            f"{manager_review or 'No manager review yet.'}\n\n"
            "Return only the corrected, complete final response."
        )
