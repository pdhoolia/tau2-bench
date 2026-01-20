/**
 * CommentFloatingButton Component
 *
 * Floating action button with comment count badge.
 * See: docs/comments-feature/implementation-spec.md §4.1
 */

export function CommentFloatingButton({ count, isOpen, onClick, isLoading }) {
  return (
    <button
      className={`comment-floating-button ${isOpen ? 'open' : ''} ${isLoading ? 'loading' : ''}`}
      onClick={onClick}
      title={isOpen ? 'Close comments' : `View comments (${count})`}
      aria-label={isOpen ? 'Close comments panel' : `Open comments panel, ${count} comments`}
    >
      <span className="button-icon">💬</span>
      {count > 0 && (
        <span className={`badge ${isOpen ? 'hidden' : ''}`}>
          {count > 99 ? '99+' : count}
        </span>
      )}
    </button>
  );
}
