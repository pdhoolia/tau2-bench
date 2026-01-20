/**
 * Comments API - Vite Dev Server Middleware
 *
 * Provides REST API for managing trajectory comments stored as JSON files.
 * See: docs/comments-feature/implementation-spec.md
 */

import { execSync } from 'child_process';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.join(__dirname, '..', 'public');

// Session username override (in-memory, resets on server restart)
let usernameOverride = null;

/**
 * Get git username from system configuration
 */
async function getGitUsername() {
  try {
    const username = execSync('git config user.name', { encoding: 'utf-8' }).trim();
    return username || null;
  } catch {
    return null;
  }
}

/**
 * Get current username (override or git)
 */
async function getCurrentUsername() {
  if (usernameOverride) {
    return { username: usernameOverride, source: 'override' };
  }
  const gitUsername = await getGitUsername();
  if (gitUsername) {
    return { username: gitUsername, source: 'git' };
  }
  return {
    username: null,
    source: 'none',
    message: 'Git username not configured. Please set with: git config user.name "Your Name"'
  };
}

/**
 * Build file path for user's comment file
 */
function buildCommentFilePath(submission, trajectory, simulation, username) {
  return path.join(
    PUBLIC_DIR,
    'submissions',
    submission,
    'trajectories',
    'comments',
    username,
    `${trajectory}_${simulation}.json`
  );
}

/**
 * Build directory path for comments
 */
function buildCommentsDir(submission, trajectory) {
  return path.join(
    PUBLIC_DIR,
    'submissions',
    submission,
    'trajectories',
    'comments'
  );
}

/**
 * Read and parse comment file, returns null if not exists
 */
async function readCommentFile(filePath) {
  try {
    const content = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(content);
  } catch (err) {
    if (err.code === 'ENOENT') {
      return null;
    }
    console.error(`Error reading comment file ${filePath}:`, err);
    return null;
  }
}

/**
 * Write comment file, creating directories as needed
 */
async function writeCommentFile(filePath, data) {
  const dir = path.dirname(filePath);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(filePath, JSON.stringify(data, null, 2), 'utf-8');
}

/**
 * Get all comments for a simulation (aggregated from all users)
 */
async function getComments(submission, trajectory, simulation) {
  const commentsDir = buildCommentsDir(submission, trajectory);
  const comments = [];

  try {
    const userDirs = await fs.readdir(commentsDir);

    for (const username of userDirs) {
      const userDir = path.join(commentsDir, username);
      const stat = await fs.stat(userDir);

      if (!stat.isDirectory()) continue;

      const filePath = path.join(userDir, `${trajectory}_${simulation}.json`);
      const data = await readCommentFile(filePath);

      if (data && data.comments) {
        // Add author to each comment
        for (const comment of data.comments) {
          comments.push({
            ...comment,
            author: data.author || username
          });
        }
      }
    }
  } catch (err) {
    if (err.code !== 'ENOENT') {
      console.error(`Error reading comments directory:`, err);
    }
    // Return empty array if directory doesn't exist
  }

  // Sort by timestamp (oldest first - ADR-007)
  comments.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

  return comments;
}

/**
 * Add a comment to user's file
 */
async function addComment(submission, trajectory, simulation, author, text) {
  const filePath = buildCommentFilePath(submission, trajectory, simulation, author);
  const simulationKey = `${submission}:${trajectory}:${simulation}`;

  let data = await readCommentFile(filePath);

  if (!data) {
    data = {
      version: 1,
      author,
      simulationKey,
      comments: []
    };
  }

  const comment = {
    id: crypto.randomUUID(),
    text,
    timestamp: new Date().toISOString(),
    edited: false
  };

  data.comments.push(comment);
  await writeCommentFile(filePath, data);

  return comment;
}

/**
 * Edit a comment in user's file
 */
async function editComment(submission, trajectory, simulation, commentId, author, text) {
  const filePath = buildCommentFilePath(submission, trajectory, simulation, author);
  const data = await readCommentFile(filePath);

  if (!data) {
    return { error: 'Comment not found', status: 404 };
  }

  const commentIndex = data.comments.findIndex(c => c.id === commentId);

  if (commentIndex === -1) {
    return { error: 'Comment not found', status: 404 };
  }

  data.comments[commentIndex] = {
    ...data.comments[commentIndex],
    text,
    edited: true,
    editedAt: new Date().toISOString()
  };

  await writeCommentFile(filePath, data);

  return { comment: { ...data.comments[commentIndex], author } };
}

/**
 * Delete a comment from user's file
 */
async function deleteComment(submission, trajectory, simulation, commentId, author) {
  const filePath = buildCommentFilePath(submission, trajectory, simulation, author);
  const data = await readCommentFile(filePath);

  if (!data) {
    return { error: 'Comment not found', status: 404 };
  }

  const commentIndex = data.comments.findIndex(c => c.id === commentId);

  if (commentIndex === -1) {
    return { error: 'Comment not found', status: 404 };
  }

  data.comments.splice(commentIndex, 1);

  // If no more comments, optionally delete the file
  if (data.comments.length === 0) {
    try {
      await fs.unlink(filePath);
    } catch {
      // Ignore deletion errors
    }
  } else {
    await writeCommentFile(filePath, data);
  }

  return { success: true };
}

/**
 * Parse request body as JSON
 */
async function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => {
      body += chunk.toString();
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

/**
 * Send JSON response
 */
function sendJson(res, status, data) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(data));
}

/**
 * Main request handler for /api/comments/*
 */
export async function commentsHandler(req, res, next) {
  // When mounted at /api/comments, req.url has the prefix already stripped by connect/express
  const urlPath = req.url.split('?')[0];
  const parts = urlPath.split('/').filter(Boolean);

  // URL decode parts
  const decodedParts = parts.map(p => decodeURIComponent(p));

  try {
    if (req.method === 'GET' && decodedParts.length === 3) {
      // GET /api/comments/:submission/:trajectory/:simulation
      const [submission, trajectory, simulation] = decodedParts;
      const comments = await getComments(submission, trajectory, simulation);
      return sendJson(res, 200, { comments, count: comments.length });
    }

    if (req.method === 'POST' && decodedParts.length === 3) {
      // POST /api/comments/:submission/:trajectory/:simulation
      const [submission, trajectory, simulation] = decodedParts;
      const body = await parseBody(req);

      if (!body.text || !body.text.trim()) {
        return sendJson(res, 400, { error: 'Text is required' });
      }

      if (!body.author) {
        return sendJson(res, 400, { error: 'Author is required' });
      }

      const comment = await addComment(submission, trajectory, simulation, body.author, body.text.trim());
      return sendJson(res, 201, { comment: { ...comment, author: body.author } });
    }

    if (req.method === 'PUT' && decodedParts.length === 4) {
      // PUT /api/comments/:submission/:trajectory/:simulation/:commentId
      const [submission, trajectory, simulation, commentId] = decodedParts;
      const body = await parseBody(req);

      if (!body.text || !body.text.trim()) {
        return sendJson(res, 400, { error: 'Text is required' });
      }

      if (!body.author) {
        return sendJson(res, 400, { error: 'Author is required' });
      }

      const result = await editComment(submission, trajectory, simulation, commentId, body.author, body.text.trim());

      if (result.error) {
        return sendJson(res, result.status, { error: result.error });
      }

      return sendJson(res, 200, result);
    }

    if (req.method === 'DELETE' && decodedParts.length === 4) {
      // DELETE /api/comments/:submission/:trajectory/:simulation/:commentId?author=xxx
      const [submission, trajectory, simulation, commentId] = decodedParts;
      const url = new URL(req.url, `http://${req.headers.host}`);
      const author = url.searchParams.get('author');

      if (!author) {
        return sendJson(res, 400, { error: 'Author query parameter is required' });
      }

      const result = await deleteComment(submission, trajectory, simulation, commentId, author);

      if (result.error) {
        return sendJson(res, result.status, { error: result.error });
      }

      res.statusCode = 204;
      return res.end();
    }

    // Not handled by this middleware
    next();
  } catch (err) {
    console.error('Comments API error:', err);
    sendJson(res, 500, { error: 'Internal server error' });
  }
}

/**
 * Main request handler for /api/username
 */
export async function usernameHandler(req, res, next) {
  // When mounted at /api/username, req.url has the prefix already stripped
  const urlPath = req.url.split('?')[0];

  if (urlPath !== '' && urlPath !== '/') {
    return next();
  }

  try {
    if (req.method === 'GET') {
      const result = await getCurrentUsername();
      return sendJson(res, 200, result);
    }

    if (req.method === 'PUT') {
      const body = await parseBody(req);

      if (!body.username || !body.username.trim()) {
        return sendJson(res, 400, { error: 'Username is required' });
      }

      usernameOverride = body.username.trim();
      return sendJson(res, 200, { username: usernameOverride, source: 'override' });
    }

    next();
  } catch (err) {
    console.error('Username API error:', err);
    sendJson(res, 500, { error: 'Internal server error' });
  }
}
