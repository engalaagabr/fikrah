# Phase: API and Workflow Design

**Status: Complete for the initial mobile API.** Implemented contracts are recorded in [`docs/features/api-contract-design/api-surface-proposal.md`](../../features/api-contract-design/api-surface-proposal.md); unresolved product decisions remain explicitly listed in the product scope.

## Goal

Define the mobile-to-Backend API surface for confirmed FIKRAH workflows, keeping unresolved product behavior out of implementation.

## Scope

- Map authentication, account, project, note, LLM processing, refinement, connections, search, chat, and graph workflows to a proposed API surface.
- State the purpose, caller workflow, request information, and response information for each proposed endpoint.
- Authentication and project routes are implemented. The user has approved the initial note CRUD and processing routes.
- Keep confirmed product requirements separate from remaining product decisions.
- Use text-only note content. PDF files remain on the mobile device; the Backend does not accept uploaded files or perform PDF/audio extraction.

## Deferred Product Decisions

- Supported languages for notes, transcription text, refinement, and search; mixed-language chat behavior.
- Mobile polling interval/backoff guidance and production worker capacity.
- Pagination for larger note, conversation, and graph collections.

## Completion Criteria

- Each initial mobile capability has an implemented endpoint contract with its purpose, call timing, request, and response.
- Remaining product decisions are listed separately instead of silently assumed.
- The implemented API contract is documented alongside its feature modules.
