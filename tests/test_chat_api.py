import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.infrastructure import container as service_container
from app.llm.contracts import ChatAnswer
from app.main import app as fastapi_app
from app.models import (
    ChatConversation,
    ChatMessage,
    ChatMessageSource,
    Note,
    Project,
    User,
)
from tests.auth_helpers import seed_access_token


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
    monkeypatch.setenv(
        "FIKRAH_JWT_SECRET", "chat-test-secret-that-is-at-least-32-characters"
    )
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
            await seed_access_token(sessions, owner_id),
            await seed_access_token(sessions, other.id),
        )
    fastapi_app.dependency_overrides.clear()
    await engine.dispose()


class FakeEmbeddingModel:
    def close(self) -> None:
        pass

    def embed_query(self, query: str) -> list[float]:
        return [0.1, 0.2]


@pytest.mark.asyncio
async def test_chat_persists_messages_and_only_authorized_citations(
    chat_api, monkeypatch: pytest.MonkeyPatch
) -> None:

    client, sessions, _, project_id, _, note_id, private_note_id, token, _ = chat_api

    class Factory:
        @staticmethod
        def create_embedding_model() -> FakeEmbeddingModel:
            return FakeEmbeddingModel()

        @staticmethod
        def create_text_generator():
            class FakeStructuredTextGenerator:
                def close(self) -> None:
                    pass

                def generate_structured(
                    self, *, system_instruction, user_content, response_model
                ) -> ChatAnswer:
                    request = json.loads(user_content)
                    assert request["question"] == "What did I save?"
                    assert [note["note_id"] for note in request["project_notes"]] == [
                        str(note_id)
                    ]
                    assert request["conversation_history"] == []
                    assert response_model is ChatAnswer
                    return ChatAnswer(
                        answer="You saved a reliable source note.",
                        supported=True,
                        source_note_ids=[
                            str(note_id),
                            "00000000-0000-0000-0000-000000000001",
                        ],
                    )

            return FakeStructuredTextGenerator()


    monkeypatch.setattr(
        service_container.chat_service,
        "_text_generator_factory",
        Factory.create_text_generator,
    )
    monkeypatch.setattr(
        service_container.search_service,
        "_embedding_model_factory",
        Factory.create_embedding_model,
    )
    monkeypatch.setattr(
        service_container.search_service,
        "_vector_search",
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
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
    ]
    assert detail.json()["messages"][1]["sources"][0]["note_id"] == str(note_id)
    async with sessions() as session:
        assert (
            await session.scalar(select(ChatConversation.title)) == "What did I save?"
        )
        assert len(list(await session.scalars(select(ChatMessageSource)))) == 1


@pytest.mark.asyncio
async def test_chat_returns_clear_unsupported_answer_when_no_notes_match(
    chat_api, monkeypatch: pytest.MonkeyPatch
) -> None:

    client, _, _, project_id, _, _, _, token, _ = chat_api

    class Factory:
        @staticmethod
        def create_embedding_model() -> FakeEmbeddingModel:
            return FakeEmbeddingModel()

        @staticmethod
        def create_text_generator():
            class FakeStructuredTextGenerator:
                def close(self) -> None:
                    pass

                def generate_structured(
                    self, *, system_instruction, user_content, response_model
                ) -> ChatAnswer:
                    assert json.loads(user_content)["project_notes"] == []
                    assert response_model is ChatAnswer
                    return ChatAnswer(
                        answer="I couldn't find an answer supported by your project notes.",
                        supported=False,
                        source_note_ids=[],
                    )

            return FakeStructuredTextGenerator()


    monkeypatch.setattr(
        service_container.chat_service,
        "_text_generator_factory",
        Factory.create_text_generator,
    )
    monkeypatch.setattr(
        service_container.search_service,
        "_embedding_model_factory",
        Factory.create_embedding_model,
    )
    monkeypatch.setattr(
        service_container.search_service, "_vector_search", lambda *_args: []
    )
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
async def test_chat_uses_latest_twelve_messages_in_chronological_order(
    chat_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sessions, _, project_id, _, _, _, token, _ = chat_api
    created = await client.post(
        f"/v1/projects/{project_id}/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    conversation_id = UUID(created.json()["id"])
    start = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with sessions() as session:
        session.add_all(
            ChatMessage(
                conversation_id=conversation_id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"history-{index}",
                created_at=start + timedelta(microseconds=index),
            )
            for index in range(14)
        )
        await session.commit()

    captured_history: list[dict[str, str]] = []

    class Factory:
        @staticmethod
        def create_embedding_model() -> FakeEmbeddingModel:
            return FakeEmbeddingModel()

        @staticmethod
        def create_text_generator():
            class FakeStructuredTextGenerator:
                def close(self) -> None:
                    pass

                def generate_structured(
                    self, *, system_instruction, user_content, response_model
                ) -> ChatAnswer:
                    request = json.loads(user_content)
                    captured_history.extend(request["conversation_history"])
                    return ChatAnswer(
                        answer="I couldn't find an answer supported by your project notes.",
                        supported=False,
                        source_note_ids=[],
                    )

            return FakeStructuredTextGenerator()


    monkeypatch.setattr(
        service_container.chat_service,
        "_text_generator_factory",
        Factory.create_text_generator,
    )
    monkeypatch.setattr(
        service_container.search_service,
        "_embedding_model_factory",
        Factory.create_embedding_model,
    )
    monkeypatch.setattr(service_container.search_service, "_vector_search", lambda *_args: [])

    response = await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "Summarize the conversation"},
    )
    assert response.status_code == 200
    assert captured_history == [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"history-{index}",
        }
        for index in range(2, 14)
    ]


@pytest.mark.asyncio
async def test_chat_rejects_a_reply_when_the_conversation_changes_during_generation(
    chat_api, monkeypatch: pytest.MonkeyPatch
) -> None:

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
        def create_text_generator():
            class FakeStructuredTextGenerator:
                def close(self) -> None:
                    pass

                def generate_structured(
                    self, *, system_instruction, user_content, response_model
                ) -> ChatAnswer:
                    assert response_model is ChatAnswer
                    return ChatAnswer(
                        answer="I couldn't find an answer supported by your project notes.",
                        supported=False,
                        source_note_ids=[],
                    )

            return FakeStructuredTextGenerator()

    from app.services import chat_service as chat_service_module

    original_to_thread = chat_service_module.asyncio.to_thread

    async def run_in_thread(function, *args, **kwargs):
        nonlocal answer_call_seen
        if (
            function is chat_service_module.run_with_provider
            and args[0] is Factory.create_text_generator
        ):
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

    monkeypatch.setattr(
        service_container.chat_service,
        "_text_generator_factory",
        Factory.create_text_generator,
    )
    monkeypatch.setattr(
        service_container.search_service,
        "_embedding_model_factory",
        Factory.create_embedding_model,
    )
    monkeypatch.setattr(
        service_container.search_service, "_vector_search", lambda *_args: []
    )
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
                select(ChatMessage).where(
                    ChatMessage.conversation_id == conversation_id
                )
            )
        )
    assert [message.content for message in messages] == ["A concurrent message"]


@pytest.mark.asyncio
async def test_chat_conversations_are_isolated_by_user_and_project(chat_api) -> None:
    (
        client,
        sessions,
        owner_id,
        project_id,
        other_project_id,
        _,
        _,
        token,
        other_token,
    ) = chat_api
    async with sessions() as session:
        conversation = ChatConversation(
            user_id=owner_id, project_id=project_id, title="Private"
        )
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
async def test_deleting_conversation_removes_messages_and_citations(chat_api) -> None:
    client, sessions, _, project_id, _, note_id, _, token, _ = chat_api
    created = await client.post(
        f"/v1/projects/{project_id}/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    conversation_id = UUID(created.json()["id"])

    async with sessions() as session:
        conversation = await session.get(ChatConversation, conversation_id)
        assert conversation is not None
        user_message = ChatMessage(
            conversation_id=conversation_id, role="user", content="Question"
        )
        assistant_message = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content="Answer",
            supported=True,
        )
        session.add_all([user_message, assistant_message])
        await session.flush()
        session.add(
            ChatMessageSource(message_id=assistant_message.id, note_id=note_id)
        )
        await session.commit()

    deleted = await client.delete(
        f"/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204

    async with sessions() as session:
        assert await session.get(ChatConversation, conversation_id) is None
        assert list(await session.scalars(select(ChatMessage))) == []
        assert list(await session.scalars(select(ChatMessageSource))) == []


@pytest.mark.asyncio
async def test_deleting_note_removes_chat_citations(chat_api) -> None:
    client, sessions, owner_id, project_id, _, note_id, _, token, _ = chat_api
    from app.models import ChatMessage

    async with sessions() as session:
        conversation = ChatConversation(
            user_id=owner_id, project_id=project_id, title="Sources"
        )
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
        conversation = ChatConversation(
            user_id=owner_id, project_id=project_id, title="Project chat"
        )
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


@pytest.mark.asyncio
async def test_chat_rejects_answer_when_only_some_cited_notes_are_still_current(
    chat_api, monkeypatch
):
    from types import SimpleNamespace
    from uuid import uuid4

    client, _, _, project_id, _, note_id, _, token, _ = chat_api
    removed_id = uuid4()
    async def retrieve(*_):
        return [
            SimpleNamespace(note_id=note_id, title="Valid", content="A", revision=2),
            SimpleNamespace(note_id=removed_id, title="Removed", content="B", revision=1),
        ]

    async def validate(*_):
        return [SimpleNamespace(id=note_id, revision=2)]

    calls = []
    class Generator:
        def close(self) -> None:
            pass

        def generate_structured(self, **kwargs):
            notes = json.loads(kwargs["user_content"])["project_notes"]
            calls.append(notes)
            if notes:
                return ChatAnswer(answer="A and removed B", supported=True, source_note_ids=[str(note_id), str(removed_id)])
            return ChatAnswer(answer="No current evidence supports this answer.", supported=False)

    monkeypatch.setattr(service_container.search_service, "retrieve", retrieve)
    monkeypatch.setattr(service_container.chat_service._repository, "find_completed_notes_for_citations", validate)
    monkeypatch.setattr(service_container.chat_service, "_text_generator_factory", Generator)
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post(f"/v1/projects/{project_id}/conversations", headers=headers, json={})
    response = await client.post(f"/v1/conversations/{created.json()['id']}/messages", headers=headers, json={"content": "What is A and B?"})
    assert response.status_code == 200
    assistant = response.json()["assistant_message"]
    assert assistant["supported"] is False
    assert assistant["sources"] == []
    assert "removed B" not in assistant["content"]
    assert len(calls) == 2
    assert calls[1] == []


@pytest.mark.asyncio
async def test_new_message_updates_named_conversation_activity(chat_api, monkeypatch):
    from datetime import datetime

    client, sessions, _, project_id, _, _, _, token, _ = chat_api
    async def no_matches(*_):
        return []

    class Generator:
        def close(self) -> None:
            pass

        def generate_structured(self, **kwargs):
            return ChatAnswer(answer="No supported answer.", supported=False)

    monkeypatch.setattr(service_container.search_service, "retrieve", no_matches)
    monkeypatch.setattr(service_container.chat_service, "_text_generator_factory", Generator)
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post(f"/v1/projects/{project_id}/conversations", headers=headers, json={"title": "Named conversation"})
    conversation_id = UUID(created.json()["id"])
    async with sessions() as db:
        conversation = await db.get(ChatConversation, conversation_id)
        conversation.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        await db.commit()
    response = await client.post(f"/v1/conversations/{conversation_id}/messages", headers=headers, json={"content": "A new question"})
    assert response.status_code == 200
    assert response.json()["conversation"]["updated_at"] > "2020-01-01"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    ["answer", "generation_failure", "factory_failure", "conflict", "refusal"],
)
async def test_chat_closes_owned_generators_before_validation(
    chat_api, monkeypatch, scenario
):
    from threading import get_ident
    from uuid import uuid4

    client, _, _, project_id, _, _, _, token, _ = chat_api
    service = service_container.chat_service
    clients = []
    threads = []

    async def no_matches(*_):
        return []

    class Generator:
        def __init__(self):
            threads.append(get_ident())
            if scenario == "factory_failure":
                raise RuntimeError("controlled client creation failure")
            self.closed = False
            clients.append(self)

        def generate_structured(self, **kwargs):
            threads.append(get_ident())
            assert not self.closed
            if scenario == "generation_failure":
                raise ValueError("controlled generation failure")
            if scenario == "refusal" and len(clients) == 1:
                return ChatAnswer(answer="Unusable uncited answer", supported=True)
            return ChatAnswer(answer="No supported answer.", supported=False)

        def close(self):
            threads.append(get_ident())
            assert not self.closed
            self.closed = True

    original_latest = service._repository.latest_message_id

    async def latest(db, conversation_id):
        assert clients and all(provider.closed for provider in clients)
        if scenario == "conflict":
            return uuid4()
        return await original_latest(db, conversation_id)

    monkeypatch.setattr(service_container.search_service, "retrieve", no_matches)
    monkeypatch.setattr(service, "_text_generator_factory", Generator)
    monkeypatch.setattr(service._repository, "latest_message_id", latest)
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post(
        f"/v1/projects/{project_id}/conversations", headers=headers, json={}
    )
    main_thread = get_ident()
    response = await client.post(
        f"/v1/conversations/{created.json()['id']}/messages",
        headers=headers,
        json={"content": "What did I save?"},
    )
    expected_status = {
        "generation_failure": 503,
        "factory_failure": 503,
        "conflict": 409,
    }.get(scenario, 200)
    assert response.status_code == expected_status
    assert all(provider.closed for provider in clients)
    expected_count = (
        0 if scenario == "factory_failure" else (2 if scenario == "refusal" else 1)
    )
    assert len(clients) == expected_count
    assert threads and main_thread not in threads
    for start in range(0, len(threads), 3):
        assert len(set(threads[start : start + 3])) == 1
    if expected_status == 200:
        assert response.json()["assistant_message"]["supported"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_fails", [False, True])
async def test_cancelled_chat_closes_provider_after_request_finishes(
    chat_api, monkeypatch, provider_fails
):
    import asyncio
    from threading import Event

    client, sessions, _, project_id, _, _, _, token, _ = chat_api
    started, release, closed = Event(), Event(), Event()

    async def no_matches(*_):
        return []

    class Generator:
        def generate_structured(self, **kwargs):
            started.set()
            assert release.wait(5)
            assert not closed.is_set()
            if provider_fails:
                raise ValueError("provider failed after cancellation")
            return ChatAnswer(answer="No supported answer.", supported=False)

        def close(self):
            assert not closed.is_set()
            closed.set()

    monkeypatch.setattr(service_container.search_service, "retrieve", no_matches)
    monkeypatch.setattr(
        service_container.chat_service, "_text_generator_factory", Generator
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post(
        f"/v1/projects/{project_id}/conversations", headers=headers, json={}
    )
    conversation_id = created.json()["id"]
    task = asyncio.create_task(
        client.post(
            f"/v1/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "Cancelled question"},
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not closed.is_set()
    finally:
        release.set()
        assert await asyncio.to_thread(closed.wait, 3)
    async with sessions() as db:
        messages = list(
            await db.scalars(
                select(ChatMessage).where(
                    ChatMessage.conversation_id == UUID(conversation_id)
                )
            )
        )
        assert messages == []
