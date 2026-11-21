"""Composition root for application services and infrastructure adapters."""

from app.core.config import get_settings
from app.infrastructure.email.cipher import protect_email_token, reveal_email_token
from app.infrastructure.email.smtp import send_action_email, send_welcome_email
from app.infrastructure.identity.google import verify_google_id_token
from app.infrastructure.rate_limits import RedisBudgetStore
from app.llm.factory import LLMProviderFactory
from app.rag.embeddings import create_embedding_model
from app.rag.vector_store import search_note_vectors
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.connections_service import KnowledgeConnectionService
from app.services.notes_service import NoteService
from app.services.projects_service import ProjectService
from app.services.request_budgets import RequestBudgets
from app.services.search_service import SemanticSearchService
from app.services.transcription_service import TranscriptionService

request_budgets = RequestBudgets(
    RedisBudgetStore(lambda: get_settings().redis_url),
    login_limit=lambda: get_settings().fikrah_login_limit_per_minute,
    llm_limit=lambda: get_settings().fikrah_llm_limit_per_minute,
)

auth_service = AuthService(
    send_action_email=send_action_email,
    protect_email_token=protect_email_token,
    reveal_email_token=reveal_email_token,
    send_welcome_email=send_welcome_email,
    verify_google_id_token=verify_google_id_token,
    google_client_id=lambda: get_settings().google_client_id,
    login_budget=request_budgets.login,
)
search_service = SemanticSearchService(
    embedding_model_factory=create_embedding_model,
    vector_search=search_note_vectors,
)
chat_service = ChatService(
    search_service=search_service,
    text_generator_factory=LLMProviderFactory.create_text_generator,
)
note_service = NoteService()
project_service = ProjectService()
knowledge_connection_service = KnowledgeConnectionService()
transcription_service = TranscriptionService(
    transcriber_factory=LLMProviderFactory.create_audio_transcriber,
    max_audio_bytes=lambda: get_settings().fikrah_transcription_max_bytes,
)
