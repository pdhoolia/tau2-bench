# Architecture Decision Records (ADR-Lite): Trajectory Comments Feature

**Author:** IRL
**Date:** 2025-01-20
**Status:** Approved

**References:**

- [Intent and Constraints](./intent-and-constraints.md)
- [High-Level Design](./high-level-design.md)

---

## ADR-001: File-Based Storage Over localStorage

### Context

HLD Open Question: How should comments be persisted?

The intent document requires that comments persist across browser sessions and be shareable among team members via git (Intent §5: Constraints - "Team collaboration via git").

### Decision

Store comments as JSON files in the repository file system, organized by user.

### Alternatives Considered

| Option                        | Description           | Pros                                         | Cons                                         |
|-------------------------------|-----------------------|----------------------------------------------|----------------------------------------------|
| **A. localStorage**           | Browser-local storage | Simple, no backend                           | Not shareable, browser-specific              |
| **B. File-based (chosen)**    | JSON files in repo    | Git-mergeable, shareable, version-controlled | Requires API middleware                      |
| **C. External SaaS (giscus)** | GitHub Discussions    | Real-time, no file management                | Enterprise restrictions, external dependency |
| **D. Backend database**       | Dedicated server + DB | Full-featured                                | Over-engineered for local dev use case       |

### Rationale

- **Constraint:** "Team collaboration via git" (Intent §5.3.1) requires persistence beyond browser
- **Constraint:** "Local development context" (Intent §5.1.1) - users run locally, no production backend
- **Constraint:** GitHub Enterprise environment may restrict third-party integrations
- File-based storage provides version control, audit trail, and offline access

### Consequences

- (+) Comments are version-controlled with full git history
- (+) No external service dependencies
- (+) Works offline after initial load
- (-) Requires Vite middleware for file I/O
- (-) Users must manually commit/push to share comments

---

## ADR-002: Per-User File Isolation for Conflict-Free Merging

### Context

HLD Open Question: What is the storage key/file structure?

Multiple users will independently add comments and merge via git (Intent §7: Success Criteria #2).

### Decision

Store each user's comments in a separate file within their own subfolder:

```txt
comments/{git-username}/{trajectory}_{simulation}.json
```

### Alternatives Considered

| Option                            | Description                     | Pros                 | Cons                       |
|-----------------------------------|---------------------------------|----------------------|----------------------------|
| **A. Single file per simulation** | All users' comments in one file | Simple structure     | Merge conflicts guaranteed |
| **B. Per-user folders (chosen)**  | Separate file per user          | Conflict-free merges | More files to aggregate    |
| **C. Per-comment files**          | One file per comment            | Maximum isolation    | Too many small files       |

### Rationale

- **Constraint:** "Git-mergeable" (Intent §5.2.4) - must avoid conflicts when multiple users commit
- **Success Criteria:** "merge without conflicts" (Intent §7.2)
- Different users never modify the same file, eliminating merge conflicts entirely

### Consequences

- (+) Zero merge conflicts when multiple users add comments
- (+) Clear ownership - each user's folder contains only their comments
- (+) Easy to delete all comments by one user (delete their folder)
- (-) API must aggregate comments from multiple folders
- (-) Slightly more complex directory structure

---

## ADR-003: Git Username as Identity Source

### Context

HLD Open Question: How do we identify comment authors without authentication?

The intent document states "git username is sufficient identity" (Intent §3.2 Non-Goals) and identity should be derived from `git config user.name` (Intent §5.1.3).

### Decision

Use `git config user.name` as the default author identity, with ability to override in the UI.

### Alternatives Considered

| Option                        | Description                 | Pros                  | Cons                     |
|-------------------------------|-----------------------------|-----------------------|--------------------------|
| **A. Manual entry each time** | User types name per comment | Flexible              | Tedious, inconsistent    |
| **B. git config (chosen)**    | Auto-detect from git        | Automatic, consistent | Requires git configured  |
| **C. OAuth/login**            | Full authentication         | Verified identity     | Over-engineered, complex |
| **D. Machine identifier**     | Use hostname/MAC            | Automatic             | Not human-readable       |

### Rationale

- **Constraint:** "No complex user authentication" (Intent §3.2)
- **Constraint:** "Git-based identity" (Intent §5.1.3)
- Developers working in a git repo will have `git config user.name` already set
- Provides consistent identity across sessions without login

### Consequences

- (+) Zero friction - works automatically for git users
- (+) Consistent with git commit authorship
- (+) Can override in UI if needed (e.g., shared machine)
- (-) Not cryptographically verified (trust-based)
- (-) User must have git configured

---

## ADR-004: Vite Dev Server Middleware for API

### Context

HLD Open Question: How do we handle file I/O from the browser?

Browsers cannot directly write to the file system. We need a mechanism to persist comments.

### Decision

Implement a Vite plugin that adds middleware to handle `/api/comments/*` endpoints during development.

### Alternatives Considered

| Option                          | Description               | Pros                       | Cons                                      |
|---------------------------------|---------------------------|----------------------------|-------------------------------------------|
| **A. Separate Express server**  | Run API on different port | Clear separation           | Extra process to manage                   |
| **B. Vite middleware (chosen)** | Plugin in vite.config.js  | Single process, integrated | Dev-only by default                       |
| **C. File System Access API**   | Browser native API        | No server needed           | Limited browser support, security prompts |
| **D. Electron wrapper**         | Desktop app               | Full file access           | Complete architecture change              |

### Rationale

- **Constraint:** "Local development context" (Intent §5.1.1) - users already run `npm run dev`
- Vite middleware integrates seamlessly with existing dev workflow
- No additional processes or ports to manage
- Can be extended for production if needed

### Consequences

- (+) Single command (`npm run dev`) runs everything
- (+) Hot reload works naturally
- (+) No CORS issues (same origin)
- (-) Dev-only by default (need separate solution for production hosting)
- (-) Adds complexity to vite.config.js

---

## ADR-005: Floating Button with Slide-Out Panel UI Pattern

### Context

HLD Open Question: How should comments be presented in the UI?

Comments should be "non-intrusive" and not "obscure trajectory content by default" (Intent §4.3).

### Decision

Use a floating action button (FAB) with badge showing comment count. Clicking expands a slide-out panel from the right edge.

### Alternatives Considered

| Option                                  | Description                 | Pros                      | Cons                       |
|-----------------------------------------|-----------------------------|---------------------------|----------------------------|
| **A. Inline per-message**               | Comments below each message | Contextual                | Clutters conversation view |
| **B. Separate tab/page**                | Comments on different view  | Clean separation          | Loses context              |
| **C. Floating button + panel (chosen)** | FAB with slide-out          | Non-intrusive, contextual | Requires panel animation   |
| **D. Modal dialog**                     | Overlay modal               | Focused attention         | Blocks underlying content  |

### Rationale

- **Constraint:** "Non-intrusive" (Intent §4.3) - must not obscure content by default
- **Design Decision:** "Collapsed by default" (Intent §6.4)
- Floating button provides constant access without cluttering the view
- Panel allows viewing comments while still seeing the conversation

### Consequences

- (+) Conversation view remains uncluttered
- (+) Badge provides at-a-glance comment count
- (+) Panel allows simultaneous viewing of comments and conversation
- (-) Requires CSS animation for smooth transitions
- (-) Panel takes screen real estate when open

---

## ADR-006: Owner-Only Edit/Delete Permissions

### Context

HLD Open Question: Who can edit or delete comments?

Without authentication, we need a simple permission model (Intent §6.3).

### Decision

Users can only edit or delete comments where the author matches their current git username.

### Alternatives Considered

| Option                        | Description              | Pros                  | Cons                       |
|-------------------------------|--------------------------|-----------------------|----------------------------|
| **A. Anyone can edit/delete** | No restrictions          | Simple                | Chaotic, no accountability |
| **B. Owner-only (chosen)**    | Match git username       | Clear ownership       | Relies on trust            |
| **C. No edit/delete**         | Append-only              | Simple, immutable     | Frustrating for typos      |
| **D. Admin role**             | Special users can delete | Moderation capability | Requires role system       |

### Rationale

- **Design Decision:** "Users can only edit/delete their own comments" (Intent §6.3)
- Simple to implement - compare comment author with current username
- Aligns with git philosophy - you own your commits
- Trust-based model appropriate for team/research context

### Consequences

- (+) Clear ownership model
- (+) Prevents accidental deletion of others' comments
- (+) Simple to implement
- (-) Not cryptographically enforced (could be bypassed)
- (-) Cannot moderate inappropriate comments by others

---

## ADR-007: Comment Ordering - Chronological (Oldest First)

### Context

HLD Open Question: Should comments be displayed newest first or oldest first?

### Decision

Display comments in chronological order (oldest first), like a conversation thread.

### Alternatives Considered

| Option                       | Description           | Pros                       | Cons                    |
|------------------------------|-----------------------|----------------------------|-------------------------|
| **A. Newest first**          | Reverse chronological | See latest quickly         | Unnatural reading order |
| **B. Oldest first (chosen)** | Chronological         | Natural conversation flow  | Must scroll for latest  |
| **C. Grouped by author**     | Cluster by user       | See each person's thoughts | Loses temporal context  |

### Rationale

- Comments form a conversation/discussion thread
- Reading oldest-to-newest follows natural narrative flow
- Consistent with chat/messaging UI conventions
- New comment form at bottom aligns with adding to end of thread

### Consequences

- (+) Natural reading order
- (+) Consistent with chat conventions
- (-) Must scroll to see newest comments in long threads

---

## ADR-008: Panel Overlay (Not Push)

### Context

HLD Open Question: Should the comment panel push content or overlay it?

### Decision

The panel overlays the content with a slight shadow, not pushing the conversation view.

### Alternatives Considered

| Option                  | Description          | Pros               | Cons                       |
|-------------------------|----------------------|--------------------|----------------------------|
| **A. Push layout**      | Conversation shrinks | Both fully visible | Layout reflow, jarring     |
| **B. Overlay (chosen)** | Panel floats over    | Smooth animation   | Partially obscures content |
| **C. Resizable split**  | Draggable divider    | User control       | Complex implementation     |

### Rationale

- Push layout causes jarring reflow of conversation content
- Overlay is smoother and more common in modern UIs
- User can close panel to see full content when needed
- Simpler CSS implementation

### Consequences

- (+) Smooth open/close animation
- (+) No layout reflow
- (+) Simpler implementation
- (-) Partially obscures conversation when open

---

## ADR-009: Fixed Panel Width (320px)

### Context

HLD Open Question: Fixed width or percentage-based panel width?

### Decision

Use a fixed width of 320px for the comment panel.

### Alternatives Considered

| Option                        | Description                     | Pros                  | Cons                      |
|-------------------------------|---------------------------------|-----------------------|---------------------------|
| **A. Fixed 320px (chosen)**   | Constant width                  | Predictable, readable | May be tight on mobile    |
| **B. Percentage (30%)**       | Proportional                    | Scales with screen    | Too wide on large screens |
| **C. Responsive breakpoints** | Different widths per breakpoint | Optimized per device  | More complex CSS          |

### Rationale

- 320px is wide enough for comfortable reading
- Matches common sidebar/panel widths
- On mobile, can switch to full-width modal (future enhancement)
- Simpler CSS without percentage calculations

### Consequences

- (+) Consistent, predictable width
- (+) Optimal for comment text readability
- (+) Simpler implementation
- (-) May need adjustment for very narrow screens

---

## ADR-010: Username Stored in localStorage for Session Persistence

### Context

HLD Open Question: Should username override be persisted?

Users may override the git-detected username (e.g., on shared machines).

### Decision

Store username override in localStorage so it persists across browser sessions.

### Alternatives Considered

| Option                       | Description         | Pros                  | Cons                   |
|------------------------------|---------------------|-----------------------|------------------------|
| **A. Session only**          | Lost on tab close   | Fresh start each time | Tedious to re-enter    |
| **B. localStorage (chosen)** | Persists in browser | Convenient            | Browser-specific       |
| **C. Config file**           | .tau2-comments.json | Shareable             | Another file to manage |

### Rationale

- Git username detection handles most cases automatically
- Override is edge case (shared machine, different identity)
- localStorage provides convenient persistence without file management
- Can be cleared by user if needed

### Consequences

- (+) Override persists across sessions
- (+) No additional files to manage
- (-) Browser-specific (different browsers have different overrides)
- (-) Mixed storage (files for comments, localStorage for settings)

---

## Summary Table

| ADR     | Decision                             | Resolves HLD Section |
|---------|--------------------------------------|----------------------|
| ADR-001 | File-based storage over localStorage | §4, §5               |
| ADR-002 | Per-user file isolation              | §4.1, §4.4           |
| ADR-003 | Git username as identity             | §3.2, §8.2           |
| ADR-004 | Vite middleware for API              | §5                   |
| ADR-005 | Floating button + slide-out panel    | §7                   |
| ADR-006 | Owner-only edit/delete               | §8.1                 |
| ADR-007 | Chronological ordering               | §12.3                |
| ADR-008 | Panel overlay (not push)             | §12.2                |
| ADR-009 | Fixed 320px panel width              | §12.1                |
| ADR-010 | localStorage for username override   | §12.5                |
