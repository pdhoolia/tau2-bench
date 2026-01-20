/**
 * CommentForm Component
 *
 * Input form for adding new comments.
 * See: docs/comments-feature/implementation-spec.md §4.5
 */

import { useState, useCallback } from 'react';

export function CommentForm({ onSubmit, isSubmitting, placeholder = 'Add a comment...' }) {
  const [text, setText] = useState('');

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    if (!text.trim() || isSubmitting) return;

    await onSubmit(text.trim());
    setText('');
  }, [text, isSubmitting, onSubmit]);

  const isDisabled = !text.trim() || isSubmitting;

  return (
    <form className="comment-form" onSubmit={handleSubmit}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        disabled={isSubmitting}
        rows={3}
      />
      <button type="submit" disabled={isDisabled}>
        {isSubmitting ? 'Adding...' : 'Add Comment'}
      </button>
    </form>
  );
}
