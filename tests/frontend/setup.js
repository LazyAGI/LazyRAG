/**
 * Load frontend app script from index.html into jsdom and expose globals for testing.
 * Does not modify any business code - only reads and executes the existing script.
 */
import { JSDOM } from 'jsdom';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const htmlPath = join(__dirname, '../../frontend/index.html');
const html = readFileSync(htmlPath, 'utf-8');

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) throw new Error('No script found in index.html');

const scriptContent = scriptMatch[1];
const dom = new JSDOM('<!DOCTYPE html><html><body><div id="app"></div></body></html>', {
  url: 'http://localhost',
  runScripts: 'dangerously',
  pretendToBeVisual: true,
});

const win = dom.window;
win.localStorage = { _data: {}, getItem(k) { return this._data[k] ?? null; }, setItem(k, v) { this._data[k] = String(v); }, removeItem(k) { delete this._data[k]; } };
win.eval(scriptContent);

export const {
  escapeHtml,
  saveTokens,
  saveRole,
  getRole,
  isAdmin,
  shouldRefresh,
  getHashRoute,
  parseRoute,
  navigate,
  getAdminNavHTML,
} = win;

export { win };
