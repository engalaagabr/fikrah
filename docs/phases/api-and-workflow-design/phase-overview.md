# Phase: API and Workflow Design

## Goal

Define the mobile-to-Backend API surface for confirmed FIKRAH workflows before implementing product endpoints or persistence models that depend on unresolved behavior.

## Scope

- Map authentication, account, project, note, AI processing, refinement, connections, search, chat, and graph workflows to a proposed API surface.
- State the purpose, caller workflow, request information, and response information for each proposed endpoint.
- Keep confirmed product requirements separate from proposals and open decisions.
- Use text-only note content. PDF files remain on the mobile device; the Backend does not accept uploaded files or perform PDF/audio extraction.

## Not Included Yet

- Final endpoint paths and request/response schemas.
- Authentication token strategy and Google sign-in exchange details.
- Exact processing-state values and the polling interval/backoff policy.
- Product models, migrations, or implementation of the proposed routes.
- AI provider, prompt, embedding, or retrieval implementation details.

## Completion Criteria

- Each mobile capability has a proposed endpoint map with its purpose, call timing, request, and response.
- Unresolved product and architecture decisions are listed for review instead of silently assumed.
- The accepted API contract is documented before endpoint implementation begins.
