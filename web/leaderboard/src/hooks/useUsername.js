/**
 * useUsername Hook
 *
 * Manages current user identity for comments.
 * See: docs/comments-feature/implementation-spec.md §5.2
 */

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'tau2-comments-username-override';

export function useUsername() {
  const [username, setUsernameState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load username on mount
  useEffect(() => {
    async function loadUsername() {
      setIsLoading(true);
      setError(null);

      try {
        // Check localStorage for override first
        const override = localStorage.getItem(STORAGE_KEY);
        if (override) {
          setUsernameState(override);
          setIsLoading(false);
          return;
        }

        // Fetch from API (git config)
        const response = await fetch('/api/username');
        const data = await response.json();

        if (data.username) {
          setUsernameState(data.username);
        } else {
          setError(data.message || 'Username not configured');
        }
      } catch (err) {
        console.error('Failed to load username:', err);
        setError('Failed to load username');
      } finally {
        setIsLoading(false);
      }
    }

    loadUsername();
  }, []);

  // Set username override
  const setUsername = useCallback((name) => {
    if (name && name.trim()) {
      const trimmed = name.trim();
      localStorage.setItem(STORAGE_KEY, trimmed);
      setUsernameState(trimmed);
      setError(null);
    }
  }, []);

  // Clear override (revert to git username)
  const clearOverride = useCallback(async () => {
    localStorage.removeItem(STORAGE_KEY);

    try {
      const response = await fetch('/api/username');
      const data = await response.json();

      if (data.username) {
        setUsernameState(data.username);
        setError(null);
      } else {
        setUsernameState(null);
        setError(data.message || 'Username not configured');
      }
    } catch (err) {
      console.error('Failed to reload username:', err);
      setError('Failed to reload username');
    }
  }, []);

  return {
    username,
    isLoading,
    error,
    setUsername,
    clearOverride
  };
}
