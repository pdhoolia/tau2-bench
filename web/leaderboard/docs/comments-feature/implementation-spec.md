# Executable Implementation Specification: Trajectory Comments Feature

**Author:** IRL
**Date:** 2025-01-20
**Status:** Approved

**References:**

- [Intent and Constraints](./intent-and-constraints.md)
- [High-Level Design](./high-level-design.md)
- [ADR-Lite](./adr-lite.md)

---

## 1. Overview

This document provides the detailed implementation specification for the Trajectory Comments feature. It defines API contracts, data schemas, component interfaces, and file layouts with sufficient detail for code generation.

---

## 2. API Contracts

### 2.1 Comments API

Base path: `/api/comments`

#### 2.1.1 GET /api/comments/:submission/:trajectory/:simulation

Retrieves all comments for a simulation, aggregated from all users.

**Request:**

```http
GET /api/comments/claude-3-7-sonnet_anthropic_2024-06-20/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials/task42_trial0
```

**Response (200 OK):**

```json
{
  "comments": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "author": "pdhoolia",
      "text": "Turn 2: Agent should have asked for email first.",
      "timestamp": "2025-01-20T10:30:00.000Z",
      "edited": false
    },
    {
      "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "author": "jsmith",
      "text": "Great handling of the edge case!",
      "timestamp": "2025-01-20T11:15:00.000Z",
      "edited": true,
      "editedAt": "2025-01-20T11:20:00.000Z"
    }
  ],
  "count": 2
}
```

**Response (404 Not Found):** No comments exist (returns empty array)

```json
{
  "comments": [],
  "count": 0
}
```

#### 2.1.2 POST /api/comments/:submission/:trajectory/:simulation

Adds a new comment for the current user.

**Request:**

```http
POST /api/comments/claude-3-7-sonnet_anthropic_2024-06-20/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials/task42_trial0
Content-Type: application/json

{
  "text": "Turn 5: This response was excellent.",
  "author": "pdhoolia"
}
```

**Response (201 Created):**

```json
{
  "comment": {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "author": "pdhoolia",
    "text": "Turn 5: This response was excellent.",
    "timestamp": "2025-01-20T14:30:00.000Z",
    "edited": false
  }
}
```

**Response (400 Bad Request):**

```json
{
  "error": "Text is required"
}
```

#### 2.1.3 PUT /api/comments/:submission/:trajectory/:simulation/:commentId

Edits an existing comment (must be owned by current user).

**Request:**

```http
PUT /api/comments/claude-3-7-sonnet_anthropic_2024-06-20/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials/task42_trial0/550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "text": "Turn 2: Agent should have verified identity first.",
  "author": "pdhoolia"
}
```

**Response (200 OK):**

```json
{
  "comment": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "author": "pdhoolia",
    "text": "Turn 2: Agent should have verified identity first.",
    "timestamp": "2025-01-20T10:30:00.000Z",
    "edited": true,
    "editedAt": "2025-01-20T15:00:00.000Z"
  }
}
```

**Response (403 Forbidden):**

```json
{
  "error": "Cannot edit comment owned by another user"
}
```

**Response (404 Not Found):**

```json
{
  "error": "Comment not found"
}
```

#### 2.1.4 DELETE /api/comments/:submission/:trajectory/:simulation/:commentId

Deletes a comment (must be owned by current user).

**Request:**

```http
DELETE /api/comments/claude-3-7-sonnet_anthropic_2024-06-20/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials/task42_trial0/550e8400-e29b-41d4-a716-446655440000?author=pdhoolia
```

**Response (204 No Content):** Success, no body

**Response (403 Forbidden):**

```json
{
  "error": "Cannot delete comment owned by another user"
}
```

**Response (404 Not Found):**

```json
{
  "error": "Comment not found"
}
```

### 2.2 Username API

Base path: `/api/username`

#### 2.2.1 GET /api/username

Gets the current git username.

**Response (200 OK):**

```json
{
  "username": "pdhoolia",
  "source": "git"
}
```

**Response (200 OK - not configured):**

```json
{
  "username": null,
  "source": "none",
  "message": "Git username not configured. Please set with: git config user.name \"Your Name\""
}
```

#### 2.2.2 PUT /api/username

Overrides the username for the current session.

**Request:**

```http
PUT /api/username
Content-Type: application/json

{
  "username": "custom-user"
}
```

**Response (200 OK):**

```json
{
  "username": "custom-user",
  "source": "override"
}
```

---

## 3. Data Schemas

### 3.1 Comment File Schema

**File path pattern:**

```text
public/submissions/{submission}/trajectories/comments/{username}/{trajectory}_{simulation}.json
```

**Schema:**

```typescript
interface CommentFile {
  /** Schema version for migrations */
  version: 1;

  /** Git username of file owner */
  author: string;

  /** Reference key: "{submission}:{trajectory}:{simulation}" */
  simulationKey: string;

  /** Array of comments */
  comments: Comment[];
}

interface Comment {
  /** UUID v4 identifier */
  id: string;

  /** Comment text content */
  text: string;

  /** ISO 8601 creation timestamp */
  timestamp: string;

  /** True if comment was edited after creation */
  edited: boolean;

  /** ISO 8601 edit timestamp (present only if edited=true) */
  editedAt?: string;
}
```

**Example file content:**

```json
{
  "version": 1,
  "author": "pdhoolia",
  "simulationKey": "claude-3-7-sonnet_anthropic_2024-06-20:claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials:task42_trial0",
  "comments": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "text": "Turn 2: Agent should have asked for email first.",
      "timestamp": "2025-01-20T10:30:00.000Z",
      "edited": false
    }
  ]
}
```

### 3.2 Aggregated Comment (API Response)

When comments are loaded via API, they include the author from the file:

```typescript
interface AggregatedComment extends Comment {
  /** Author from parent CommentFile */
  author: string;
}
```

---

## 4. Component Specifications

### 4.1 CommentFloatingButton

**File:** `src/components/comments/CommentFloatingButton.jsx`

**Props:**

```typescript
interface CommentFloatingButtonProps {
  /** Total comment count to display in badge */
  count: number;

  /** Whether the panel is currently open */
  isOpen: boolean;

  /** Callback when button is clicked */
  onClick: () => void;

  /** Loading state */
  isLoading?: boolean;
}
```

**Behavior:**

- Renders a circular button with chat icon
- Shows badge with count when count > 0
- Badge hidden when count is 0
- Pulses briefly when count changes
- Fixed position: bottom-right of conversation view

**CSS Classes:**

```css
.comment-floating-button { }
.comment-floating-button.open { }
.comment-floating-button .badge { }
.comment-floating-button .badge.hidden { }
.comment-floating-button.loading { }
```

### 4.2 CommentPanel

**File:** `src/components/comments/CommentPanel.jsx`

**Props:**

```typescript
interface CommentPanelProps {
  /** Whether panel is visible */
  isOpen: boolean;

  /** Callback to close panel */
  onClose: () => void;

  /** Current simulation key */
  simulationKey: string;

  /** Current username */
  username: string;

  /** Comments array */
  comments: AggregatedComment[];

  /** Loading state */
  isLoading: boolean;

  /** Error message if any */
  error: string | null;

  /** Callback to add comment */
  onAddComment: (text: string) => Promise<void>;

  /** Callback to edit comment */
  onEditComment: (id: string, text: string) => Promise<void>;

  /** Callback to delete comment */
  onDeleteComment: (id: string) => Promise<void>;

  /** Callback to refresh comments */
  onRefresh: () => Promise<void>;
}
```

**Behavior:**

- Slides in from right edge with CSS transition
- Fixed width: 320px (ADR-009)
- Overlays content, does not push (ADR-008)
- Header shows "Comments (N)" and close button
- Shows current username with edit option
- Contains CommentList and CommentForm

**CSS Classes:**

```css
.comment-panel { }
.comment-panel.open { }
.comment-panel .panel-header { }
.comment-panel .panel-body { }
.comment-panel .username-display { }
```

### 4.3 CommentList

**File:** `src/components/comments/CommentList.jsx`

**Props:**

```typescript
interface CommentListProps {
  /** Array of comments to display */
  comments: AggregatedComment[];

  /** Current username for edit/delete permissions */
  currentUser: string;

  /** Callback when edit is requested */
  onEdit: (id: string, text: string) => Promise<void>;

  /** Callback when delete is requested */
  onDelete: (id: string) => Promise<void>;
}
```

**Behavior:**

- Renders comments in chronological order (oldest first, ADR-007)
- Scrollable container
- Shows empty state when no comments

**CSS Classes:**

```css
.comment-list { }
.comment-list .empty-state { }
```

### 4.4 CommentItem

**File:** `src/components/comments/CommentItem.jsx`

**Props:**

```typescript
interface CommentItemProps {
  /** Comment data */
  comment: AggregatedComment;

  /** Whether current user can edit/delete */
  canModify: boolean;

  /** Callback when edit is saved */
  onEdit: (text: string) => Promise<void>;

  /** Callback when delete is confirmed */
  onDelete: () => Promise<void>;
}
```

**Behavior:**

- Displays author, timestamp, and text
- Shows "edited" indicator if comment.edited is true
- Edit/delete buttons visible only if canModify is true
- Edit mode: inline textarea replaces text
- Delete: shows confirmation before executing

**CSS Classes:**

```css
.comment-item { }
.comment-item .comment-header { }
.comment-item .comment-author { }
.comment-item .comment-timestamp { }
.comment-item .comment-text { }
.comment-item .comment-actions { }
.comment-item .edited-indicator { }
.comment-item.editing { }
```

### 4.5 CommentForm

**File:** `src/components/comments/CommentForm.jsx`

**Props:**

```typescript
interface CommentFormProps {
  /** Callback when comment is submitted */
  onSubmit: (text: string) => Promise<void>;

  /** Whether form is submitting */
  isSubmitting: boolean;

  /** Placeholder text */
  placeholder?: string;
}
```

**Behavior:**

- Textarea for comment input
- Submit button (disabled when empty or submitting)
- Clears after successful submit
- Shows loading state during submit

**CSS Classes:**

```css
.comment-form { }
.comment-form textarea { }
.comment-form button { }
.comment-form button:disabled { }
.comment-form.submitting { }
```

---

## 5. Hook Specifications

### 5.1 useComments

**File:** `src/hooks/useComments.js`

**Signature:**

```typescript
function useComments(simulationKey: string | null): UseCommentsReturn;

interface UseCommentsReturn {
  /** All comments from all users */
  comments: AggregatedComment[];

  /** Total comment count */
  count: number;

  /** True while loading */
  isLoading: boolean;

  /** Error message if load/operation failed */
  error: string | null;

  /** Current username */
  currentUser: string;

  /** Add a new comment */
  addComment: (text: string) => Promise<void>;

  /** Edit an existing comment */
  editComment: (id: string, text: string) => Promise<void>;

  /** Delete a comment */
  deleteComment: (id: string) => Promise<void>;

  /** Check if user can modify a comment */
  canEdit: (comment: AggregatedComment) => boolean;

  /** Manually refresh comments */
  refresh: () => Promise<void>;
}
```

**Implementation details:**

1. Fetches comments when simulationKey changes
2. Returns empty state when simulationKey is null
3. Manages loading/error states
4. Optimistically updates UI on mutations
5. Reverts on error
6. canEdit returns `comment.author === currentUser`

### 5.2 useUsername

**File:** `src/hooks/useUsername.js`

**Signature:**

```typescript
function useUsername(): UseUsernameReturn;

interface UseUsernameReturn {
  /** Current username (from git or override) */
  username: string | null;

  /** True while loading */
  isLoading: boolean;

  /** Error message if failed */
  error: string | null;

  /** Override username for session */
  setUsername: (name: string) => void;
}
```

**Implementation details:**

1. On mount, checks localStorage for override
2. If no override, fetches from `/api/username`
3. setUsername stores in localStorage and updates state
4. localStorage key: `tau2-comments-username-override`

---

## 6. Server Middleware Specification

### 6.1 Comments Handler

**File:** `server/commentsApi.js`

**Functions:**

```typescript
/**
 * Main request handler for /api/comments/*
 */
function commentsHandler(req: Request, res: Response, next: Function): void;

/**
 * Get all comments for a simulation (aggregated)
 */
async function getComments(
  submission: string,
  trajectory: string,
  simulation: string
): Promise<AggregatedComment[]>;

/**
 * Add a comment to user's file
 */
async function addComment(
  submission: string,
  trajectory: string,
  simulation: string,
  author: string,
  text: string
): Promise<Comment>;

/**
 * Edit a comment in user's file
 */
async function editComment(
  submission: string,
  trajectory: string,
  simulation: string,
  commentId: string,
  author: string,
  text: string
): Promise<Comment>;

/**
 * Delete a comment from user's file
 */
async function deleteComment(
  submission: string,
  trajectory: string,
  simulation: string,
  commentId: string,
  author: string
): Promise<void>;

/**
 * Build file path for user's comment file
 */
function buildCommentFilePath(
  submission: string,
  trajectory: string,
  simulation: string,
  username: string
): string;

/**
 * Read and parse comment file, returns null if not exists
 */
async function readCommentFile(filePath: string): Promise<CommentFile | null>;

/**
 * Write comment file, creating directories as needed
 */
async function writeCommentFile(filePath: string, data: CommentFile): Promise<void>;
```

### 6.2 Username Handler

**File:** `server/commentsApi.js` (same file)

**Functions:**

```typescript
/**
 * Main request handler for /api/username
 */
function usernameHandler(req: Request, res: Response, next: Function): void;

/**
 * Get git username from system
 */
async function getGitUsername(): Promise<string | null>;
```

**Implementation:**

```javascript
const { execSync } = require('child_process');

async function getGitUsername() {
  try {
    const username = execSync('git config user.name', { encoding: 'utf-8' }).trim();
    return username || null;
  } catch {
    return null;
  }
}
```

---

## 7. Vite Configuration

### 7.1 Plugin Setup

**File:** `vite.config.js`

**Changes:**

```javascript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { commentsHandler, usernameHandler } from './server/commentsApi.js';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'comments-api',
      configureServer(server) {
        // Parse JSON body for POST/PUT
        server.middlewares.use(express.json());

        // Mount API handlers
        server.middlewares.use('/api/comments', commentsHandler);
        server.middlewares.use('/api/username', usernameHandler);
      }
    }
  ],
  // ... existing config
});
```

---

## 8. File Layout

### 8.1 New Files to Create

```text
web/leaderboard/
├── src/
│   ├── components/
│   │   └── comments/
│   │       ├── CommentFloatingButton.jsx
│   │       ├── CommentPanel.jsx
│   │       ├── CommentList.jsx
│   │       ├── CommentItem.jsx
│   │       ├── CommentForm.jsx
│   │       ├── Comments.css
│   │       └── index.js              # Re-exports
│   └── hooks/
│       ├── useComments.js
│       └── useUsername.js
├── server/
│   └── commentsApi.js
└── public/submissions/
    └── .gitkeep                      # Ensure comments dirs can be created
```

### 8.2 Files to Modify

```text
web/leaderboard/
├── src/
│   └── components/
│       ├── TrajectoryVisualizer.jsx  # Import and render comment components
│       └── TrajectoryVisualizer.css  # Add styles for comment integration
└── vite.config.js                    # Add comments-api plugin
```

---

## 9. CSS Specifications

### 9.1 Comments.css

**File:** `src/components/comments/Comments.css`

```css
/* Floating Button */
.comment-floating-button {
  position: fixed;
  bottom: 100px;
  right: 24px;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #2e7d32;
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s, background 0.2s;
  z-index: 1000;
}

.comment-floating-button:hover {
  transform: scale(1.1);
  background: #1b5e20;
}

.comment-floating-button.open {
  background: #1b5e20;
}

.comment-floating-button .badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #d32f2f;
  color: white;
  font-size: 12px;
  font-weight: bold;
  min-width: 20px;
  height: 20px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
}

.comment-floating-button .badge.hidden {
  display: none;
}

/* Panel */
.comment-panel {
  position: fixed;
  top: 0;
  right: -320px;
  width: 320px;
  height: 100vh;
  background: white;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  transition: right 0.3s ease;
  z-index: 1001;
}

.comment-panel.open {
  right: 0;
}

.comment-panel .panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
  background: #f5f5f5;
}

.comment-panel .panel-header h3 {
  margin: 0;
  font-size: 16px;
}

.comment-panel .close-button {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #666;
}

.comment-panel .username-display {
  padding: 8px 16px;
  background: #e8f5e9;
  font-size: 13px;
  color: #2e7d32;
  border-bottom: 1px solid #e0e0e0;
}

.comment-panel .panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* Comment List */
.comment-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.comment-list .empty-state {
  text-align: center;
  color: #999;
  padding: 32px 16px;
}

/* Comment Item */
.comment-item {
  background: #f9f9f9;
  border-radius: 8px;
  padding: 12px;
}

.comment-item .comment-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.comment-item .comment-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.comment-item .comment-author {
  font-weight: 600;
  font-size: 13px;
  color: #333;
}

.comment-item .comment-timestamp {
  font-size: 11px;
  color: #999;
}

.comment-item .edited-indicator {
  font-size: 11px;
  color: #999;
  font-style: italic;
}

.comment-item .comment-text {
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  white-space: pre-wrap;
}

.comment-item .comment-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.comment-item .comment-actions button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  padding: 4px;
}

.comment-item .comment-actions button:hover {
  color: #333;
}

/* Comment Form */
.comment-form {
  padding: 16px;
  border-top: 1px solid #e0e0e0;
  background: #fafafa;
}

.comment-form textarea {
  width: 100%;
  min-height: 80px;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  resize: vertical;
  font-family: inherit;
  font-size: 14px;
}

.comment-form textarea:focus {
  outline: none;
  border-color: #2e7d32;
}

.comment-form button {
  margin-top: 8px;
  width: 100%;
  padding: 10px;
  background: #2e7d32;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.comment-form button:hover:not(:disabled) {
  background: #1b5e20;
}

.comment-form button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* Delete Confirmation */
.delete-confirm {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.delete-confirm button {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

.delete-confirm .confirm-yes {
  background: #d32f2f;
  color: white;
  border: none;
}

.delete-confirm .confirm-no {
  background: white;
  border: 1px solid #ddd;
}
```

---

## 10. Integration with TrajectoryVisualizer

### 10.1 State Additions

```javascript
// In TrajectoryVisualizer.jsx

// Add to imports
import { CommentFloatingButton, CommentPanel } from './comments';
import { useComments } from '../hooks/useComments';
import { useUsername } from '../hooks/useUsername';

// Add state for comment panel
const [showComments, setShowComments] = useState(false);

// Build simulation key when task is selected
const simulationKey = useMemo(() => {
  if (!selectedSubmission || !selectedTrajectory || !selectedTask) return null;
  const submission = selectedSubmission.directory;
  const trajectory = selectedTrajectory.file.replace('.json', '');
  const simulation = `task${selectedTask.task_index}_trial${selectedTask.trial || 0}`;
  return `${submission}:${trajectory}:${simulation}`;
}, [selectedSubmission, selectedTrajectory, selectedTask]);

// Use hooks
const { username } = useUsername();
const {
  comments,
  count,
  isLoading,
  error,
  addComment,
  editComment,
  deleteComment,
  canEdit,
  refresh
} = useComments(simulationKey);
```

### 10.2 Render Additions

```jsx
// In the conversation view section, add:

{selectedTask && (
  <>
    <CommentFloatingButton
      count={count}
      isOpen={showComments}
      onClick={() => setShowComments(!showComments)}
      isLoading={isLoading}
    />

    <CommentPanel
      isOpen={showComments}
      onClose={() => setShowComments(false)}
      simulationKey={simulationKey}
      username={username}
      comments={comments}
      isLoading={isLoading}
      error={error}
      onAddComment={addComment}
      onEditComment={editComment}
      onDeleteComment={deleteComment}
      onRefresh={refresh}
    />
  </>
)}
```

---

## 11. Error Handling Matrix

| Operation      | Error Type     | User Message                                  | Recovery              |
|----------------|----------------|-----------------------------------------------|-----------------------|
| Load comments  | Network error  | "Failed to load comments. Click to retry."    | Show retry button     |
| Load comments  | Parse error    | "Some comments could not be loaded."          | Show partial results  |
| Add comment    | Network error  | "Failed to save comment. Please try again."   | Keep text in form     |
| Add comment    | Empty text     | "Comment cannot be empty."                    | Disable submit button |
| Edit comment   | Network error  | "Failed to save changes. Please try again."   | Revert to original    |
| Edit comment   | 403 Forbidden  | "You can only edit your own comments."        | Cancel edit mode      |
| Delete comment | Network error  | "Failed to delete comment. Please try again." | Keep comment          |
| Delete comment | 403 Forbidden  | "You can only delete your own comments."      | Hide delete option    |
| Get username   | Not configured | "Set your username to add comments."          | Show input field      |

---

## 12. Testing Checklist

### 12.1 Unit Tests

- [ ] useComments hook: load, add, edit, delete operations
- [ ] useUsername hook: get from git, override, persist
- [ ] CommentItem: render, edit mode, delete confirmation
- [ ] CommentForm: validation, submit, loading state
- [ ] CommentList: empty state, ordering, scroll

### 12.2 Integration Tests

- [ ] API: GET comments aggregates from multiple users
- [ ] API: POST creates file if not exists
- [ ] API: PUT updates correct comment
- [ ] API: DELETE removes comment, deletes empty file
- [ ] API: 403 on edit/delete of other user's comment

### 12.3 E2E Tests

- [ ] Add comment flow: type, submit, see in list
- [ ] Edit comment flow: click edit, modify, save
- [ ] Delete comment flow: click delete, confirm, removed
- [ ] Panel open/close animation
- [ ] Badge count updates

---

## 13. Implementation Order

Recommended implementation sequence:

1. **Server middleware** (`server/commentsApi.js`)
   - Username handler
   - Comments CRUD handlers
   - File read/write utilities

2. **Vite configuration** (`vite.config.js`)
   - Add middleware plugin

3. **Hooks** (`src/hooks/`)
   - useUsername
   - useComments

4. **Components** (`src/components/comments/`)
   - CommentForm (simplest)
   - CommentItem
   - CommentList
   - CommentPanel
   - CommentFloatingButton

5. **Styles** (`Comments.css`)
   - All component styles

6. **Integration** (`TrajectoryVisualizer.jsx`)
   - Import and wire up components

7. **Testing**
   - Unit tests
   - Integration tests
   - Manual E2E testing
