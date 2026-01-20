# Intent and Constraints: Trajectory Comments Feature

**Author:** IRL
**Date:** 2025-01-20
**Status:** Approved
**Version:** 1.1

---

## 1. Problem Statement

The τ²-bench Leaderboard UI displays conversation trajectories showing AI agent interactions with users across airline, retail, and telecom domains. Currently, researchers and reviewers can only passively view these trajectories without any way to annotate, comment on, or discuss specific turns or tasks.

**The Gap:** There is no mechanism for users to:

- Add observations about specific agent responses or user turns
- Document issues, insights, or patterns observed in conversations
- Collaborate with team members on trajectory analysis
- Track review status or flag conversations for follow-up

---

## 2. Goals

### Primary Goals

1. **Enable simulation-level commenting:** Allow users to add comments to a simulated trajectory, with free-form text that can reference specific turns, task context, or results
2. **Support comment lifecycle:** Provide ability to view, edit, and delete existing comments
3. **Preserve browsing experience:** Comments should enhance, not obstruct, the trajectory viewing experience

### Secondary Goals

1. Provide visual indicator (badge) showing comment count for each simulation
2. Allow collapsing/expanding comment panel to manage visual clutter
3. Maintain responsiveness on mobile devices

### Non-Goals (Out of Scope)

1. Real-time collaboration (live updates when multiple users comment simultaneously)
2. Complex user authentication (git username is sufficient identity)
3. Comment notifications or alerts
4. Rich text formatting in comments (markdown, images, etc.)
5. Comment threading/replies (keep flat structure initially)
6. Comment search or filtering

---

## 3. Functional Requirements

### FR-1: Add Comment

- User can add a new comment to any simulation trajectory
- Comments have a text field (required)
- Author is automatically set from git username (configurable in UI settings)
- User can reference specific turns, task context, or results within the comment text
- Timestamp is automatically recorded when comment is saved

### FR-2: View Comments

- Floating comment button shows badge with total comment count (all users)
- Clicking button expands/collapses comment panel
- Comments display: author (git username), timestamp, and text content
- Comments from all users are visible and aggregated in the panel
- Comments panel is collapsed by default

### FR-3: Edit Comment

- User can edit the text of their own comments (same git username)
- Edit action preserves original timestamp, adds "edited" indicator

### FR-4: Delete Comment

- User can delete their own comments (same git username)
- Confirmation prompt before permanent deletion

### FR-5: Comment Persistence (File-Based, Git-Mergeable)

- Comments are stored as JSON files in the repository alongside trajectories
- Storage structure enables git-based collaboration:

  ```text
  submissions/{submission-dir}/trajectories/comments/
    └── {git-username}/
        └── {trajectory-file-stem}_{simulation-id}.json
  ```

- Each user's comments are in separate files → easy git merge (no conflicts)
- Users commit their comments to the repo and push/pull to share
- UI loads and aggregates comments from all user folders

---

## 4. Non-Functional Requirements

### NFR-1: Performance

- Comment operations (add/edit/delete) should complete in < 500ms
- Loading comments should not block trajectory rendering
- UI should remain responsive with up to 100 comments per trajectory

### NFR-2: Storage

- Comments stored as JSON files in the repository (not localStorage)
- File format designed for easy git merging (one file per user per simulation)
- Graceful handling if comment files don't exist (empty state)

### NFR-3: User Experience

- Comment UI should match existing tau2-bench visual design
- Mobile-responsive layout
- Non-intrusive: comments should not obscure trajectory content by default

### NFR-4: Data Integrity

- Comments are version-controlled via git (full history, rollback capability)
- Comment data structure supports future extensibility (threading, reactions, etc.)
- JSON format is human-readable for manual inspection/editing if needed

---

## 5. Constraints

### Technical Constraints

1. **Local development context:** Users run the webapp locally via `npm run dev` (Vite dev server)
2. **File-based persistence:** Comments saved to local filesystem, committed via git
3. **Git-based identity:** User identity derived from git config (`git config user.name`)
4. **Existing architecture:** Must integrate with current React component structure and state patterns

### Design Constraints

1. **Consistency:** Must follow existing visual patterns from Leaderboard and TrajectoryVisualizer components
2. **Non-breaking:** Cannot change existing trajectory JSON data format
3. **Hash-based routing:** Must work with current `#trajectory-visualizer` navigation
4. **Git-mergeable:** File structure must avoid merge conflicts when multiple users commit

### Scope Constraints

1. **Team collaboration via git:** Multiple users share comments by committing and pulling from shared repo
2. **Per-user file isolation:** Each user's comments in separate files to enable conflict-free merging

---

## 6. Design Decisions (Resolved)

The following questions were resolved during requirements review:

1. **Comment indicator placement:** Floating comment button positioned at right edge (top, middle, or bottom) of the conversation view

2. **Storage structure:** File-based, git-mergeable structure:
   - One file per user per simulation (avoids merge conflicts)
   - Path: `submissions/{submission}/trajectories/comments/{git-username}/{trajectory}_{simulation}.json`
   - UI aggregates comments from all user folders

3. **Edit/delete permissions:** Users can only edit/delete their own comments (matched by git username)

4. **Comment expansion default:** Collapsed by default, showing a badge with comment count

5. **Simplified comment model:** One comment stream per simulated trajectory (not per-turn). Users establish linkage to specific turns, task context, or simulation results within the comment text itself

---

## 7. Success Criteria

The feature is successful if:

1. Users can add comments to any simulation trajectory and find them on subsequent app restarts
2. Multiple users can independently add comments, commit to git, and merge without conflicts
3. After git pull, users see comments from all team members aggregated in the UI
4. Edit and delete operations work correctly for user's own comments
5. The trajectory browsing experience remains smooth and uncluttered
6. Comment UI is visually consistent with existing components

---

## 8. References

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Leaderboard UI architecture design document
- [TrajectoryVisualizer.jsx](../../src/components/TrajectoryVisualizer.jsx) - Current implementation
- Screenshot: Trajectory conversation view showing message structure
