"""Composition root for application services and infrastructure adapters."""

import os

from app.auth.service import AuthService
from app.chat.service import ChatService
from app.infrastructure.email.smtp import send_action_email, send_welcome_email
from app.infrastructure.identity.google import verify_google_id_token
from app.infrastructure.llm.factory import LLMProviderFactory
from app.infrastructure.vector_store.qdrant import search_note_vectors
from app.search.service import SemanticSearchService

auth_service = AuthService(
    send_action_email=send_action_email,
    send_welcome_email=send_welcome_email,
    verify_google_id_token=verify_google_id_token,
    google_client_id=lambda: os.getenv("GOOGLE_CLIENT_ID"),
)
search_service = SemanticSearchService(
    embedding_model_factory=LLMProviderFactory.create_embedding_model,
    vector_search=search_note_vectors,
)
chat_service = ChatService(
    search_service=search_service,
    text_generator_factory=LLMProviderFactory.create_text_generator,
)
