/**
 * CommentList Component
 *
 * Renders list of comments in chronological order.
 * See: docs/comments-feature/implementation-spec.md §4.3
 */

import { CommentItem } from './CommentItem';

export function CommentList({ comments, currentUser, onEdit, onDelete }) {
  if (!comments || comments.length === 0) {
    return (
      <div className="comment-list">
        <div className="empty-state">
          <p>No comments yet</p>
          <p className="empty-hint">Be the first to add a comment!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="comment-list">
      {comments.map((comment) => (
        <CommentItem
          key={comment.id}
          comment={comment}
          canModify={comment.author === currentUser}
          onEdit={(text) => onEdit(comment.id, text)}
          onDelete={() => onDelete(comment.id)}
        />
      ))}
    </div>
  );
}
