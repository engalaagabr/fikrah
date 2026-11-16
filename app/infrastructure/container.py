"""Composition root for application services and infrastructure adapters."""

from app.core.config import get_settings
from app.infrastructure.email.smtp import send_action_email, send_welcome_email
from app.infrastructure.identity.google import verify_google_id_token
from app.llm.factory import LLMProviderFactory
from app.rag.embeddings import create_embedding_model
from app.rag.vector_store import search_note_vectors
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.connections_service import KnowledgeConnectionService
from app.services.notes_service import NoteService
from app.services.projects_service import ProjectService
from app.services.search_service import SemanticSearchService

auth_service = AuthService(
    send_action_email=send_action_email,
    send_welcome_email=send_welcome_email,
    verify_google_id_token=verify_google_id_token,
    google_client_id=lambda: get_settings().google_client_id,
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
