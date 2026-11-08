# FIKRAH — AI and Backend Product Scope

## Purpose

This document records confirmed product requirements for the AI and Backend layers. It is a requirements record, not an implementation plan or API design. Do not treat open questions as settled requirements.

## Confirmed Product Scope

FIKRAH is an AI-powered personal knowledge management application, or second brain. Users capture text notes, voice notes, and PDF documents; AI helps turn that information into structured, interconnected knowledge.

The product experience is:

**Capture → Understand → Organize → Connect → Retrieve → Discover**

Users can manage notes, organize them into projects, improve and structure notes with AI, discover relationships between notes, search by meaning, and ask questions about their knowledge through AI chat.

`General` is the default project. A note is associated with the currently selected project. Users may create another project and switch to/select it to organize notes there.

After a note is saved, AI processing starts automatically. The user can also request that a note be processed again.

## Content Processing Boundary

- The mobile application extracts text locally from voice recordings and PDF documents.
- Original PDF files remain on the device as-is.
- The Backend and AI services receive text only, regardless of whether it was typed directly or extracted locally from audio or a PDF.
- The AI and Backend layers process and store the received text.
- Server-side speech-to-text, PDF text extraction, and OCR are not required.
- Mobile application development and UI implementation are outside this work's responsibility.

## Account and Data Isolation

Every user has an independent account. A user must only have access to their own:

- Notes.
- Projects.
- Embeddings.
- Knowledge connections.
- Conversations.
- Chat history.

The initial sign-in methods are email and password, and Google sign-in.

Authentication, user accounts, authorization, and enforcement of this data isolation are Backend responsibilities.

## AI and Backend Responsibilities

The AI layer is responsible for understanding, refining, organizing, connecting, and retrieving knowledge.

An AI refinement proposal must remain in the same language as the original note.

For AI chat, answers must be grounded in notes from the selected project. If those notes do not contain enough evidence to answer, the assistant must clearly say that it could not find a supported answer there.

The Backend layer is responsible for APIs, authentication, user accounts, data management and persistence, and communication between the mobile application and AI services.

The AI and Backend owner is responsible for requirements discovery, API design and mobile integration contracts, AI capabilities and workflows, Backend functionality, data management, authentication and user isolation, and AI/Backend integration. This role does not include mobile application development or UI implementation.

## Selected Technologies

- Backend framework: FastAPI.
- Data stores: PostgreSQL and Qdrant.
- The exact division of responsibilities between PostgreSQL and Qdrant has not been finalized.

## Existing Integration Context

The repository's `backend-integration.md` describes existing mobile-facing abstractions and behavior. AI note refinement is represented as a proposal, not an automatic replacement; proposals are surfaced only if the user has not edited the note while AI processing is in progress. When the user accepts a proposal, it permanently replaces the note's current text; the previous text is not retained. When the user rejects a proposal, it disappears, and the user may request another wording. The same document specifies project-scoped note context for AI analysis and questions, and connections between notes in the same project. The built-in `General` project and user-selected project model align with this project-scoped context; the mobile application supplies the notes of the selected project to AI operations.

Some details in the existing integration document conflict with confirmed requirements above: it assigns voice/PDF extraction to the AI service and describes an attachment uploader. The confirmed requirements are that extraction happens locally on mobile, original PDFs remain on-device, and Backend and AI services receive and process text only. The old server-side extraction and file-upload descriptions are superseded and need review before implementation.

These existing integration details should be reviewed alongside the source code when it becomes available. The product workflow for editing a proposal before accepting or rejecting it remains unspecified.

## Discovery Still Needed

Confirm these behaviors with the user before treating them as requirements or designing endpoints around them:

- How users edit a proposed refinement before accepting or rejecting it.
- Which languages the application must understand and use for notes, transcriptions, and search.
- Which language chat should use when the user's question and the relevant notes have different languages, or the project contains notes in multiple languages.
- Whether email verification and password recovery are required in the initial release.
- The detailed mobile-to-Backend workflows and endpoint requirements for each capability.
