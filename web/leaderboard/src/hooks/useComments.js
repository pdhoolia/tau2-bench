/**
 * useComments Hook
 *
 * Manages comments for a simulation trajectory.
 * See: docs/comments-feature/implementation-spec.md §5.1
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useUsername } from './useUsername';

export function useComments(simulationKey) {
  const [comments, setComments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const { username: currentUser, isLoading: usernameLoading } = useUsername();

  // Parse simulation key into parts
  const keyParts = useMemo(() => {
    if (!simulationKey) return null;
    const parts = simulationKey.split(':');
    if (parts.length !== 3) return null;
    return {
      submission: parts[0],
      trajectory: parts[1],
      simulation: parts[2]
    };
  }, [simulationKey]);

  // Build API URL
  const buildUrl = useCallback((commentId = null) => {
    if (!keyParts) return null;
    const { submission, trajectory, simulation } = keyParts;
    const base = `/api/comments/${encodeURIComponent(submission)}/${encodeURIComponent(trajectory)}/${encodeURIComponent(simulation)}`;
    return commentId ? `${base}/${encodeURIComponent(commentId)}` : base;
  }, [keyParts]);

  // Load comments
  const loadComments = useCallback(async () => {
    const url = buildUrl();
    if (!url) {
      setComments([]);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(url);
      const data = await response.json();

      if (response.ok) {
        setComments(data.comments || []);
      } else {
        setError(data.error || 'Failed to load comments');
        setComments([]);
      }
    } catch (err) {
      console.error('Failed to load comments:', err);
      setError('Failed to load comments');
      setComments([]);
    } finally {
      setIsLoading(false);
    }
  }, [buildUrl]);

  // Load comments when simulation key changes
  useEffect(() => {
    if (simulationKey) {
      loadComments();
    } else {
      setComments([]);
      setError(null);
    }
  }, [simulationKey, loadComments]);

  // Add a new comment
  const addComment = useCallback(async (text) => {
    const url = buildUrl();
    if (!url || !currentUser) {
      setError('Cannot add comment: missing simulation or username');
      return;
    }

    setError(null);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, author: currentUser })
      });

      const data = await response.json();

      if (response.ok) {
        // Optimistically add to list (sorted by timestamp)
        setComments(prev => {
          const updated = [...prev, data.comment];
          updated.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
          return updated;
        });
      } else {
        setError(data.error || 'Failed to add comment');
      }
    } catch (err) {
      console.error('Failed to add comment:', err);
      setError('Failed to add comment');
    }
  }, [buildUrl, currentUser]);

  // Edit an existing comment
  const editComment = useCallback(async (commentId, text) => {
    const url = buildUrl(commentId);
    if (!url || !currentUser) {
      setError('Cannot edit comment: missing simulation or username');
      return;
    }

    // Find the original comment for rollback
    const originalComment = comments.find(c => c.id === commentId);
    if (!originalComment) {
      setError('Comment not found');
      return;
    }

    // Optimistically update
    setComments(prev => prev.map(c =>
      c.id === commentId
        ? { ...c, text, edited: true, editedAt: new Date().toISOString() }
        : c
    ));
    setError(null);

    try {
      const response = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, author: currentUser })
      });

      const data = await response.json();

      if (!response.ok) {
        // Rollback on error
        setComments(prev => prev.map(c =>
          c.id === commentId ? originalComment : c
        ));
        setError(data.error || 'Failed to edit comment');
      }
    } catch (err) {
      // Rollback on error
      setComments(prev => prev.map(c =>
        c.id === commentId ? originalComment : c
      ));
      console.error('Failed to edit comment:', err);
      setError('Failed to edit comment');
    }
  }, [buildUrl, currentUser, comments]);

  // Delete a comment
  const deleteComment = useCallback(async (commentId) => {
    const url = buildUrl(commentId);
    if (!url || !currentUser) {
      setError('Cannot delete comment: missing simulation or username');
      return;
    }

    // Find the original comment for rollback
    const originalComment = comments.find(c => c.id === commentId);
    if (!originalComment) {
      setError('Comment not found');
      return;
    }

    // Optimistically remove
    setComments(prev => prev.filter(c => c.id !== commentId));
    setError(null);

    try {
      const response = await fetch(`${url}?author=${encodeURIComponent(currentUser)}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        // Rollback on error
        setComments(prev => {
          const updated = [...prev, originalComment];
          updated.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
          return updated;
        });

        const data = await response.json();
        setError(data.error || 'Failed to delete comment');
      }
    } catch (err) {
      // Rollback on error
      setComments(prev => {
        const updated = [...prev, originalComment];
        updated.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        return updated;
      });
      console.error('Failed to delete comment:', err);
      setError('Failed to delete comment');
    }
  }, [buildUrl, currentUser, comments]);

  // Check if current user can edit/delete a comment
  const canEdit = useCallback((comment) => {
    return comment && currentUser && comment.author === currentUser;
  }, [currentUser]);

  // Manual refresh
  const refresh = useCallback(() => {
    return loadComments();
  }, [loadComments]);

  return {
    comments,
    count: comments.length,
    isLoading: isLoading || usernameLoading,
    error,
    currentUser,
    addComment,
    editComment,
    deleteComment,
    canEdit,
    refresh
  };
}
