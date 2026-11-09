# FIKRAH — Product Vision

## Product Name and Positioning

**FIKRAH** is an AI-powered personal knowledge management application.

**Tagline:** Your thoughts, connected.

FIKRAH transforms scattered thoughts, quick notes, voice recordings, and PDF documents into structured, interconnected knowledge. Text is extracted from voice recordings and PDFs locally on the mobile device, then sent to the AI and Backend layers for processing and storage. The original PDF remains on the device. FIKRAH is intended to be more than a note-taking app: it is a personal second brain that continuously organizes, connects, and makes a user's knowledge accessible.

## Product Vision

Users capture thoughts in the form that is convenient to them. AI then understands the content, refines and structures it, identifies relevant topics, and connects new ideas with knowledge already stored by the user. This reduces the need for users to organize notes manually.

Through semantic search, intelligent knowledge linking, and Retrieval-Augmented Generation (RAG), users can explore relationships between ideas, rediscover information they have forgotten, and interact with their personal knowledge through an AI-powered conversational interface.

## Core Features

### Effortless Capture

Users can quickly save thoughts as text, voice recordings, or PDFs. The mobile application extracts text from voice and PDF files locally; the original PDF stays on the device.

### AI-Powered Refinement

AI transforms raw, unstructured input into clear, organized notes while preserving the original meaning.

### Intelligent Organization

The application automatically categorizes notes, extracts key information, and organizes knowledge into projects and topics.

### Knowledge Graph

Users can discover and visualize meaningful connections between notes and ideas.

### Semantic Search

Users can find information based on meaning and context, rather than relying only on keyword matches.

### Chat with Your Knowledge

Users can ask questions and receive contextual answers grounded in their notes and text extracted locally from their voice recordings and PDFs.

## Core Experience

**Capture → Understand → Organize → Connect → Retrieve → Discover**

## Product Principles Captured So Far

- Capturing a thought should be easy and support text, voice recordings, and PDF documents.
- AI should reduce the manual effort of organizing knowledge.
- Refinement should preserve the meaning of the user's original input.
- Stored knowledge should become interconnected and discoverable, rather than remain a collection of isolated notes.
- Answers in the conversational experience should be grounded in the user's own notes and documents.
- AI-refined text is a proposal for the user, rather than an automatic replacement. Accepting permanently replaces the current note text and starts processing again; rejecting removes the proposal and leaves the note unchanged. Results for an older note revision are discarded.

## Open Product Questions

The implementation scope and remaining product decisions are tracked in [ai-backend-scope.md](ai-backend-scope.md). The backend API and module boundaries are documented in [the layered modular architecture](../architecture/layered-modular-architecture.md).
