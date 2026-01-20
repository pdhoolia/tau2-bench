/**
 * CommentItem Component
 *
 * Displays a single comment with edit/delete actions.
 * See: docs/comments-feature/implementation-spec.md §4.4
 */

import { useState, useCallback } from 'react';

export function CommentItem({ comment, canModify, onEdit, onDelete }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(comment.text);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  const handleEditStart = useCallback(() => {
    setEditText(comment.text);
    setIsEditing(true);
  }, [comment.text]);

  const handleEditCancel = useCallback(() => {
    setIsEditing(false);
    setEditText(comment.text);
  }, [comment.text]);

  const handleEditSave = useCallback(async () => {
    if (!editText.trim() || isSubmitting) return;

    setIsSubmitting(true);
    await onEdit(editText.trim());
    setIsSubmitting(false);
    setIsEditing(false);
  }, [editText, isSubmitting, onEdit]);

  const handleDeleteConfirm = useCallback(async () => {
    setIsSubmitting(true);
    await onDelete();
    setIsSubmitting(false);
    setShowDeleteConfirm(false);
  }, [onDelete]);

  return (
    <div className={`comment-item ${isEditing ? 'editing' : ''}`}>
      <div className="comment-header">
        <div className="comment-meta">
          <span className="comment-author">{comment.author}</span>
          <span className="comment-timestamp">{formatDate(comment.timestamp)}</span>
          {comment.edited && (
            <span className="edited-indicator">
              (edited{comment.editedAt ? ` ${formatDate(comment.editedAt)}` : ''})
            </span>
          )}
        </div>
        {canModify && !isEditing && !showDeleteConfirm && (
          <div className="comment-actions">
            <button onClick={handleEditStart} title="Edit comment">✏️</button>
            <button onClick={() => setShowDeleteConfirm(true)} title="Delete comment">🗑️</button>
          </div>
        )}
      </div>

      {isEditing ? (
        <div className="comment-edit">
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            disabled={isSubmitting}
            rows={3}
          />
          <div className="edit-actions">
            <button
              onClick={handleEditSave}
              disabled={!editText.trim() || isSubmitting}
              className="save-btn"
            >
              {isSubmitting ? 'Saving...' : 'Save'}
            </button>
            <button onClick={handleEditCancel} disabled={isSubmitting} className="cancel-btn">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="comment-text">{comment.text}</div>
      )}

      {showDeleteConfirm && (
        <div className="delete-confirm">
          <span>Delete this comment?</span>
          <button
            onClick={handleDeleteConfirm}
            disabled={isSubmitting}
            className="confirm-yes"
          >
            {isSubmitting ? 'Deleting...' : 'Delete'}
          </button>
          <button
            onClick={() => setShowDeleteConfirm(false)}
            disabled={isSubmitting}
            className="confirm-no"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
