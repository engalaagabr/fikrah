from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.contracts import ChatAnswer
from app.auth.security import create_access_token
from app.database import get_db_session
from app.main import app as fastapi_app
from app.models import ChatConversation, ChatMessage, ChatMessageSource, Note, Project, User
from app.models.base import Base


@pytest_asyncio.fixture
async def chat_api(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[
    tuple[
        AsyncClient,
        async_sessionmaker[AsyncSession],
        UUID,
        UUID,
        UUID,
        UUID,
        UUID,
        str,
        str,
    ]
]:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "chat-test-secret-that-is-at-least-32-characters")
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        now = datetime.now(timezone.utc)
        owner = User(email="chat-owner@example.com", email_verified_at=now)
        other = User(email="chat-other@example.com", email_verified_at=now)
        session.add_all([owner, other])
        await session.flush()
        project = Project(user_id=owner.id, name="Research")
        other_project = Project(user_id=other.id, name="Private")
        session.add_all([project, other_project])
        await session.flush()
        note = Note(
            user_id=owner.id,
            project_id=project.id,
            title="Current note",
            content="The project has a reliable source note.",
            revision=2,
            processing_status="completed",
        )
        private_note = Note(
            user_id=other.id,
            project_id=other_project.id,
            title="Private note",
            content="This belongs to another user.",
            revision=1,
            processing_status="completed",
        )
        session.add_all([note, private_note])
        await session.commit()
        owner_id, project_id, other_project_id = owner.id, project.id, other_project.id
        note_id, private_note_id = note.id, private_note.id

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    fastapi_app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        yield (
            client,
            sessions,
            owner_id,
            project_id,
            other_project_id,
            note_id,
            private_note_id,
            create_access_token(owner_id),
            create_access_token(other.id),
        )
    fastapi_app.dependency_overrides.clear()
    await engine.dispose()


class FakeEmbeddingModel:
    def embed_query(self, query: str) -> list[float]:
        return [0.1, 0.2]


@pytest.mark.asyncio
async def test_chat_persists_messages_and_only_authorized_citations(
    chat_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.chat import routes

    client, sessions, _, project_id, _, note_id, private_note_id, token, _ = chat_api

    class Factory:
        @staticmethod
        def create_embedding_model() -> FakeEmbeddingModel:
            return FakeEmbeddingModel()

        @staticmethod
        def create_text_model():
            class FakeTextModel:
                def answer_question(self, question, notes, history) -> ChatAnswer:
                    assert question == "What did I save?"
                    assert [item.note_id for item in notes] == [str(note_id)]
                    assert history == []
                    return ChatAnswer(
                        answer="You saved a reliable source note.",
                        supported=True,
                        source_note_ids=[str(note_id), "00000000-0000-0000-0000-000000000001"],
                    )

            return FakeTextModel()

    from app.chat import service as chat_service_module
    from app.search import service as search_service_module

    monkeypatch.setattr(chat_service_module, "AIProviderFactory", Factory)
    monkeypatch.setattr(search_service_module, "AIProviderFactory", Factory)
    monkeypatch.setattr(
        search_service_module,
        "search_note_vectors",
        lambda *_args: [(note_id, 2, 0.92), (private_note_id, 1, 0.89)],
    )

    create = await client.post(
        f"/v1/projects/{project_id}/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert create.status_code == 201
    conversation_id = create.json()["id"]
    assert create.json()["title"] is None

    response = await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "  What did I save?  "},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["conversation"]["title"] == "What did I save?"
    assert result["user_message"]["content"] == "What did I save?"
    assert result["assistant_message"]["supported"] is True
    assert result["assistant_message"]["sources"] == [
        {"note_id": str(note_id), "title": "Current note"}
    ]

    detail = await client.get(
        f"/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["messages"][1]["sources"][0]["note_id"] == str(note_id)
    async with sessions() as session:
        assert await session.scalar(select(ChatConversation.title)) == "What did I save?"
        assert len(list(await session.scalars(select(ChatMessageSource)))) == 1


@pytest.mark.asyncio
async def test_chat_returns_clear_unsupported_answer_when_no_notes_match(
    chat_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.chat import routes

    client, _, _, project_id, _, _, _, token, _ = chat_api

    class Factory:
        @staticmethod
        def create_embedding_model() -> FakeEmbeddingModel:
            return FakeEmbeddingModel()

        @staticmethod
        def create_text_model():
            class FakeTextModel:
                def answer_question(self, question, notes, history) -> ChatAnswer:
                    assert notes == []
                    return ChatAnswer(
                        answer="I couldn't find an answer supported by your project notes.",
                        supported=False,
                        source_note_ids=[],
                    )

            return FakeTextModel()

    from app.chat import service as chat_service_module
    from app.search import service as search_service_module

    monkeypatch.setattr(chat_service_module, "AIProviderFactory", Factory)
    monkeypatch.setattr(search_service_module, "AIProviderFactory", Factory)
    monkeypatch.setattr(search_service_module, "search_note_vectors", lambda *_args: [])
    created = await client.post(
        f"/v1/projects/{project_id}/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    response = await client.post(
        f"/v1/conversations/{created.json()['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "What is outside my notes?"},
    )
    assert response.status_code == 200
    assistant = response.json()["assistant_message"]
    assert assistant["supported"] is False
    assert assistant["sources"] == []
    assert "couldn't find an answer supported" in assistant["content"]


@pytest.mark.asyncio
async def test_chat_rejects_a_reply_when_the_conversation_changes_during_generation(
    chat_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.chat import routes

    client, sessions, _, project_id, _, _, _, token, _ = chat_api
    created = await client.post(
        f"/v1/projects/{project_id}/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    conversation_id = UUID(created.json()["id"])
    answer_call_seen = False

    class Factory:
        @staticmethod
        def create_embedding_model() -> FakeEmbeddingModel:
            return FakeEmbeddingModel()

        @staticmethod
        def create_text_model():
            class FakeTextModel:
                def answer_question(self, question, notes, history) -> ChatAnswer:
                    return ChatAnswer(
                        answer="I couldn't find an answer supported by your project notes.",
                        supported=False,
                        source_note_ids=[],
                    )

            return FakeTextModel()

    from app.chat import service as chat_service_module
    from app.search import service as search_service_module

    original_to_thread = chat_service_module.asyncio.to_thread

    async def run_in_thread(function, *args, **kwargs):
        nonlocal answer_call_seen
        if getattr(function, "__name__", "") == "answer_question":
            answer_call_seen = True
            async with sessions() as session:
                session.add(
                    ChatMessage(
                        conversation_id=conversation_id,
                        role="user",
                        content="A concurrent message",
                    )
                )
                await session.commit()
        return await original_to_thread(function, *args, **kwargs)

    monkeypatch.setattr(chat_service_module, "AIProviderFactory", Factory)
    monkeypatch.setattr(search_service_module, "AIProviderFactory", Factory)
    monkeypatch.setattr(search_service_module, "search_note_vectors", lambda *_args: [])
    monkeypatch.setattr(chat_service_module.asyncio, "to_thread", run_in_thread)
    response = await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "A competing question"},
    )
    assert answer_call_seen
    assert response.status_code == 409
    async with sessions() as session:
        messages = list(
            await session.scalars(
                select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
            )
        )
    assert [message.content for message in messages] == ["A concurrent message"]


@pytest.mark.asyncio
async def test_chat_conversations_are_isolated_by_user_and_project(chat_api) -> None:
    client, sessions, owner_id, project_id, other_project_id, _, _, token, other_token = chat_api
    async with sessions() as session:
        conversation = ChatConversation(user_id=owner_id, project_id=project_id, title="Private")
        session.add(conversation)
        await session.commit()
        conversation_id = conversation.id

    hidden = await client.get(
        f"/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert hidden.status_code == 404
    wrong_project = await client.get(
        f"/v1/projects/{other_project_id}/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert wrong_project.status_code == 404
    hidden_delete = await client.delete(
        f"/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert hidden_delete.status_code == 404


@pytest.mark.asyncio
async def test_deleting_note_removes_chat_citations(chat_api) -> None:
    client, sessions, owner_id, project_id, _, note_id, _, token, _ = chat_api
    from app.models import ChatMessage

    async with sessions() as session:
        conversation = ChatConversation(user_id=owner_id, project_id=project_id, title="Sources")
        session.add(conversation)
        await session.flush()
        assistant = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="A cited answer.",
            supported=True,
        )
        session.add(assistant)
        await session.flush()
        session.add(ChatMessageSource(message_id=assistant.id, note_id=note_id))
        await session.commit()
        conversation_id = conversation.id

    response = await client.delete(
        f"/v1/notes/{note_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204
    detail = await client.get(
        f"/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["sources"] == []


@pytest.mark.asyncio
async def test_deleting_project_removes_its_conversations(chat_api) -> None:
    client, sessions, owner_id, project_id, _, _, _, token, _ = chat_api
    async with sessions() as session:
        conversation = ChatConversation(user_id=owner_id, project_id=project_id, title="Project chat")
        session.add(conversation)
        await session.commit()
        conversation_id = conversation.id

    response = await client.delete(
        f"/v1/projects/{project_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204
    detail = await client.get(
        f"/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 404
