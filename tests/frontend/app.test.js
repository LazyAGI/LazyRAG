/**
 * Unit tests for frontend app logic (from frontend/index.html).
 * Uses setup.js to load the script without modifying business code.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  escapeHtml,
  saveTokens,
  saveRole,
  getRole,
  isAdmin,
  shouldRefresh,
  getHashRoute,
  parseRoute,
  getAdminNavHTML,
  win,
} from './setup.js';

describe('escapeHtml', () => {
  it('escapes < and >', () => {
    expect(escapeHtml('<script>')).toBe('&lt;script&gt;');
  });
  it('escapes & and quotes', () => {
    expect(escapeHtml('a & b "c" \'d\'')).toBe('a &amp; b &quot;c&quot; &#39;d&#39;');
  });
  it('returns empty string for null', () => {
    expect(escapeHtml(null)).toBe('');
  });
  it('handles undefined', () => {
    expect(escapeHtml(undefined)).toBe('');
  });
});

describe('saveTokens / getRole / saveRole', () => {
  beforeEach(() => {
    win.localStorage.removeItem('access_token');
    win.localStorage.removeItem('refresh_token');
    win.localStorage.removeItem('access_expires_at');
    win.localStorage.removeItem('user_role');
  });

  it('saveTokens stores access token', () => {
    saveTokens('abc', 'xyz', 3600);
    expect(win.localStorage.getItem('access_token')).toBe('abc');
    expect(win.localStorage.getItem('refresh_token')).toBe('xyz');
  });

  it('saveTokens with empty clears storage', () => {
    saveTokens('a', 'b', 60);
    saveTokens('', '', 0);
    expect(win.localStorage.getItem('access_token')).toBeNull();
  });

  it('saveRole and getRole', () => {
    saveRole('admin');
    expect(getRole()).toBe('admin');
    saveRole(null);
    expect(getRole()).toBe('');
  });
});

describe('isAdmin', () => {
  beforeEach(() => {
    win.localStorage.removeItem('user_role');
  });

  it('returns true for admin role', () => {
    saveRole('admin');
    expect(isAdmin()).toBe(true);
  });
  it('returns true for ADMIN (case insensitive)', () => {
    saveRole('ADMIN');
    expect(isAdmin()).toBe(true);
  });
  it('returns false for user role', () => {
    saveRole('user');
    expect(isAdmin()).toBe(false);
  });
});

describe('shouldRefresh', () => {
  beforeEach(() => {
    win.localStorage.removeItem('access_token');
    win.localStorage.removeItem('access_expires_at');
  });

  it('returns false when no token', () => {
    expect(shouldRefresh()).toBe(false);
  });

  it('returns false when expires_at is far future', () => {
    saveTokens('t', 'r', 3600);
    expect(shouldRefresh()).toBe(false);
  });
});

describe('parseRoute', () => {
  it('parses login', () => {
    expect(parseRoute('/login')).toEqual({ page: 'login' });
  });
  it('parses register', () => {
    expect(parseRoute('/register')).toEqual({ page: 'register' });
  });
  it('parses home', () => {
    expect(parseRoute('/')).toEqual({ page: 'home' });
    expect(parseRoute('/home')).toEqual({ page: 'home' });
  });
  it('parses users', () => {
    expect(parseRoute('/users')).toEqual({ page: 'users' });
  });
  it('parses roles', () => {
    expect(parseRoute('/roles')).toEqual({ page: 'roles' });
  });
  it('parses role-permissions with id', () => {
    expect(parseRoute('/roles/1')).toEqual({ page: 'role-permissions', id: '1' });
    expect(parseRoute('/roles/2/permissions')).toEqual({ page: 'role-permissions', id: '2' });
  });
});

describe('getHashRoute', () => {
  it('returns path from hash', () => {
    win.location.hash = '#/login';
    expect(getHashRoute()).toBe('/login');
  });
  it('returns / for empty hash', () => {
    win.location.hash = '';
    expect(getHashRoute()).toBe('/');
  });
});

describe('getAdminNavHTML', () => {
  it('returns nav with expected links', () => {
    const html = getAdminNavHTML();
    expect(html).toContain('#/');
    expect(html).toContain('#/users');
    expect(html).toContain('#/roles');
    expect(html).toContain('#/login');
  });
});
