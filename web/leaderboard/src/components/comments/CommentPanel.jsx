/**
 * CommentPanel Component
 *
 * Slide-out panel containing comments list and form.
 * See: docs/comments-feature/implementation-spec.md §4.2
 */

import { useState, useCallback } from 'react';
import { CommentList } from './CommentList';
import { CommentForm } from './CommentForm';

export function CommentPanel({
  isOpen,
  onClose,
  username,
  comments,
  isLoading,
  error,
  onAddComment,
  onEditComment,
  onDeleteComment,
  onRefresh,
  onSetUsername
}) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showUsernameInput, setShowUsernameInput] = useState(false);
  const [newUsername, setNewUsername] = useState('');

  const handleAddComment = useCallback(async (text) => {
    setIsSubmitting(true);
    await onAddComment(text);
    setIsSubmitting(false);
  }, [onAddComment]);

  const handleUsernameSubmit = useCallback((e) => {
    e.preventDefault();
    if (newUsername.trim()) {
      onSetUsername(newUsername.trim());
      setShowUsernameInput(false);
      setNewUsername('');
    }
  }, [newUsername, onSetUsername]);

  return (
    <div className={`comment-panel ${isOpen ? 'open' : ''}`}>
      <div className="panel-header">
        <h3>💬 Comments ({comments.length})</h3>
        <div className="header-actions">
          <button onClick={onRefresh} className="refresh-btn" title="Refresh comments">
            🔄
          </button>
          <button onClick={onClose} className="close-button" title="Close panel">
            ✕
          </button>
        </div>
      </div>

      <div className="username-display">
        {showUsernameInput ? (
          <form onSubmit={handleUsernameSubmit} className="username-form">
            <input
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="Enter username"
              autoFocus
            />
            <button type="submit" disabled={!newUsername.trim()}>Save</button>
            <button type="button" onClick={() => setShowUsernameInput(false)}>Cancel</button>
          </form>
        ) : (
          <>
            <span>Commenting as: <strong>{username || 'Not set'}</strong></span>
            <button
              onClick={() => {
                setNewUsername(username || '');
                setShowUsernameInput(true);
              }}
              className="edit-username-btn"
              title="Change username"
            >
              ✏️
            </button>
          </>
        )}
      </div>

      {error && (
        <div className="error-message">
          {error}
          <button onClick={onRefresh}>Retry</button>
        </div>
      )}

      <div className="panel-body">
        {isLoading && comments.length === 0 ? (
          <div className="loading-state">Loading comments...</div>
        ) : (
          <CommentList
            comments={comments}
            currentUser={username}
            onEdit={onEditComment}
            onDelete={onDeleteComment}
          />
        )}
      </div>

      {username ? (
        <CommentForm
          onSubmit={handleAddComment}
          isSubmitting={isSubmitting}
          placeholder="Add a comment... (reference turns like 'Turn 3: ...')"
        />
      ) : (
        <div className="username-required">
          Set your username above to add comments
        </div>
      )}
    </div>
  );
}
