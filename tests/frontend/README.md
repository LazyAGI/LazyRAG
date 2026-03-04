# Frontend Unit Tests

Tests for the vanilla JS SPA in `frontend/index.html`.

## Setup

```bash
npm install
```

## Run

```bash
npm test
```

## Strategy

- **No business code changes**: Script is loaded from `index.html` via `setup.js`, extracted and executed in jsdom.
- **Pure functions**: `escapeHtml`, `parseRoute`, `saveTokens`, `getRole`, `isAdmin`, `shouldRefresh` are tested.
- **Mock**: `localStorage` is provided by jsdom; `fetch` is not mocked (async API tests would require `vi.stubGlobal`).
