# Project Knowledge Chat

## Goal

Let an authenticated user ask questions against notes in one selected project, retain conversation history, and return answer citations that the mobile client can open.

## API

All routes require authentication. The backend scopes each conversation to its owner and project. Mobile clients never submit an owner ID.

### `GET /v1/projects/{project_id}/conversations`

Lists the authenticated user's conversations for the selected project, ordered by most recently updated. The initial API has no pagination.

### `POST /v1/projects/{project_id}/conversations`

Creates an empty conversation. The request may include a user-provided title. When no title is provided, the first user question becomes the title, truncated to 120 characters. A newly created conversation has a `null` title until its first message is sent.

### `GET /v1/conversations/{conversation_id}`

Returns conversation metadata and the full ordered message history. Assistant messages contain `supported` and `sources`; user messages have `supported: null` and no sources. Source items include a note ID and current note title. The initial API has no pagination.

### `POST /v1/conversations/{conversation_id}/messages`

Accepts a non-blank question up to 4,000 characters and returns a complete response in one request. The response includes the persisted user message, assistant message, and updated conversation. Assistant source items contain a note ID and title.

If the project notes do not support an answer, the assistant message has `supported: false` and an empty `sources` array. The answer clearly states that the project notes did not support an answer. Responses use the same language as the question.

### `DELETE /v1/conversations/{conversation_id}`

Deletes the conversation, all of its messages, and citation records. Deleting a project also deletes its conversations and message history. Deleting a cited note removes its citation records from chat history; the saved message text remains.

## Retrieval and privacy

- The backend embeds the question with the configured Gemini embedding model and queries Qdrant within the selected user and project.
- Up to eight semantically relevant note vectors are considered. PostgreSQL must confirm that each note belongs to the authenticated user and selected project, is completed, and has the same revision as the indexed vector before the note content is sent to the text model.
- The text model receives the current question, the latest 12 conversation messages, and authorized note content. Conversation history can clarify a follow-up question but is not evidence for factual claims.
- Returned source IDs are checked against the authorized retrieval set. Invalid or out-of-scope IDs are never returned as citations.
- The configured OpenRouter, DeepSeek, or Gemini text adapter generates the answer. The response is returned as one complete message, without token streaming.
- LLM or retrieval service failures return `503`; the question and assistant response are persisted together only after a complete LLM response is available.

## Persistence

`chat_conversations`, `chat_messages`, and `chat_message_sources` store ownership, conversation history, support status, and citations. Cascading foreign keys and explicit deletion paths remove conversations with their project and remove citations when a note is deleted. Migration `20261109_05` creates the tables and indexes.

HTTP request and response models stay in `app/chat/schemas.py`. Routes map validated requests to framework-independent commands in `app/chat/contracts.py`, and map application results back to the API response models. `ChatService` does not depend on Pydantic schemas.

## Verification

Tests cover conversation persistence, automatic titles, project/user isolation, authorized citations, unsupported answers, and citation/conversation cleanup on deletion.
