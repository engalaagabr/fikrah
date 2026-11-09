"""Composition root for application services and infrastructure adapters."""

from app.chat.service import ChatService
from app.infrastructure.ai.factory import AIProviderFactory
from app.infrastructure.vector_store.qdrant import search_note_vectors
from app.search.service import SemanticSearchService

search_service = SemanticSearchService(
    embedding_model_factory=AIProviderFactory.create_embedding_model,
    vector_search=search_note_vectors,
)
chat_service = ChatService(
    search_service=search_service,
    text_model_factory=AIProviderFactory.create_text_model,
)
