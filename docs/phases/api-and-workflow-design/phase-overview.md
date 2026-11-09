# Phase: API and Workflow Design

## Goal

Define the mobile-to-Backend API surface for confirmed FIKRAH workflows, keeping unresolved product behavior out of implementation.

## Scope

- Map authentication, account, project, note, AI processing, refinement, connections, search, chat, and graph workflows to a proposed API surface.
- State the purpose, caller workflow, request information, and response information for each proposed endpoint.
- Authentication and project routes are implemented. The user has approved the initial note CRUD and processing routes.
- Keep confirmed product requirements separate from remaining proposals and open decisions.
- Use text-only note content. PDF files remain on the mobile device; the Backend does not accept uploaded files or perform PDF/audio extraction.

## Not Included Yet

- Final paths and request/response schemas for note processing, refinement, connections, search, graph, and chat.
- Mobile polling interval/backoff and worker delivery settings.
- Product models, migrations, or implementation for features whose behavior or API contract remains open.
- AI provider, prompt, embedding, or retrieval implementation details.

## Completion Criteria

- Each mobile capability has a proposed endpoint map with its purpose, call timing, request, and response.
- Unresolved product and architecture decisions are listed for review instead of silently assumed.
- The accepted API contract is documented before endpoint implementation begins.
