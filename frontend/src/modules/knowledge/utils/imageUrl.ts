import { AgentAppsAuth } from '@/components/auth';
import { BASE_URL } from '@/components/request';
import { normalizeProxyableUrl } from '@/modules/knowledge/utils/request';

const IMAGE_MD_RE = /!\[(.*?)\]\((.*?)\)/g;
const UPLOAD_ROOT_MARKER = '/var/lib/lazyrag/uploads/';
const signCache = new Map<string, string>();
const signInflight = new Map<string, Promise<string>>();

export function basenameFromPath(path: string): string {
  const withoutQuery = path.split('?')[0] || path;
  const parts = withoutQuery.split('/');
  return parts[parts.length - 1] || withoutQuery;
}

function extractUploadPath(raw: string): string {
  const trimmed = (raw || '').trim();
  if (!trimmed) {
    return '';
  }
  if (trimmed.startsWith('/static-files/')) {
    return trimmed;
  }
  const markerIndex = trimmed.indexOf(UPLOAD_ROOT_MARKER);
  if (markerIndex >= 0) {
    return trimmed.slice(markerIndex);
  }
  if (trimmed.startsWith(UPLOAD_ROOT_MARKER)) {
    return trimmed;
  }
  return trimmed;
}

export function resolveCoreAssetUrl(path?: string): string {
  const normalized = extractUploadPath(path || '');
  if (!normalized) {
    return '';
  }

  if (/^https?:\/\//i.test(normalized)) {
    return normalizeProxyableUrl(normalized);
  }

  if (normalized.startsWith('/api/core/')) {
    const origin =
      typeof window !== 'undefined' ? window.location.origin : '';
    return normalizeProxyableUrl(`${origin}${normalized}`);
  }

  if (normalized.startsWith('/static-files/')) {
    const origin =
      typeof window !== 'undefined' ? window.location.origin : '';
    return normalizeProxyableUrl(`${origin}/api/core${normalized}`);
  }

  return normalized;
}

async function signUploadPaths(paths: string[]): Promise<Record<string, string>> {
  const pending = paths.filter((path) => path && !signCache.has(path));
  if (!pending.length) {
    return Object.fromEntries(paths.map((path) => [path, signCache.get(path) || '']));
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...AgentAppsAuth.getAuthHeaders(),
  };

  const response = await fetch(`${BASE_URL}/api/core/static-files:sign`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ paths: pending }),
  });

  if (!response.ok) {
    throw new Error(`sign static files failed: ${response.status}`);
  }

  const data = (await response.json()) as { urls?: Record<string, string> };
  const urls = data.urls || {};
  Object.entries(urls).forEach(([path, signed]) => {
    if (signed) {
      signCache.set(path, signed);
    }
  });
  return urls;
}

export async function resolveMarkdownImageUrlAsync(
  url: string,
): Promise<string> {
  const trimmed = (url || '').trim();
  if (!trimmed || trimmed.startsWith('data:')) {
    return trimmed;
  }

  if (trimmed.startsWith('/static-files/')) {
    return resolveCoreAssetUrl(trimmed);
  }

  if (/^https?:\/\//i.test(trimmed) && !trimmed.includes(UPLOAD_ROOT_MARKER)) {
    return normalizeProxyableUrl(trimmed);
  }

  const uploadPath = extractUploadPath(trimmed);
  if (!uploadPath) {
    return trimmed;
  }

  if (signCache.has(uploadPath)) {
    return resolveCoreAssetUrl(signCache.get(uploadPath));
  }

  if (!signInflight.has(uploadPath)) {
    signInflight.set(
      uploadPath,
      signUploadPaths([uploadPath])
        .then((urls) => urls[uploadPath] || '')
        .finally(() => {
          signInflight.delete(uploadPath);
        }),
    );
  }

  const signed = await signInflight.get(uploadPath);
  if (signed) {
    return resolveCoreAssetUrl(signed);
  }
  return trimmed;
}

function findMatchingImageKey(
  url: string,
  keys: string[],
): string | undefined {
  if (!keys.length) {
    return undefined;
  }
  const urlBase = basenameFromPath(url);

  for (const key of keys) {
    if (!key) {
      continue;
    }
    if (url === key || url.includes(key) || key.includes(url)) {
      return key;
    }
    if (basenameFromPath(key) === urlBase) {
      return key;
    }
  }
  return undefined;
}

export function resolveMarkdownImageUrl(
  url: string,
  imageKeys: string[] = [],
): string {
  const trimmed = (url || '').trim();
  if (!trimmed || trimmed.startsWith('data:')) {
    return trimmed;
  }

  if (trimmed.startsWith('/static-files/')) {
    return resolveCoreAssetUrl(trimmed);
  }

  const matchedKey = findMatchingImageKey(trimmed, imageKeys);
  if (matchedKey) {
    return resolveCoreAssetUrl(matchedKey);
  }

  if (/^https?:\/\//i.test(trimmed) && trimmed.includes(UPLOAD_ROOT_MARKER)) {
    return resolveCoreAssetUrl(trimmed);
  }

  return trimmed;
}

export function expandImagesInMarkdown(
  srcText: string,
  imageKeys: string[] = [],
): string {
  if (typeof srcText !== 'string' || !srcText) {
    return srcText;
  }

  return srcText.replace(IMAGE_MD_RE, (match, alt, url) => {
    const resolved = resolveMarkdownImageUrl(url, imageKeys);
    if (!resolved || resolved === url) {
      return match;
    }
    return `![${alt}](${resolved})`;
  });
}

export function collapseImagesToKeys(srcText: string, keys: string[]): string {
  if (typeof srcText !== 'string' || !Array.isArray(keys)) {
    return srcText;
  }

  return srcText.replace(IMAGE_MD_RE, (match, alt, url) => {
    const found = keys.find((k) => {
      if (!k) {
        return false;
      }
      const keyBase = basenameFromPath(k);
      return (
        url.indexOf(k) !== -1 ||
        url.indexOf(keyBase) !== -1 ||
        basenameFromPath(url) === keyBase
      );
    });
    if (found) {
      const storageKey = basenameFromPath(found) || found.split('?')[0];
      return `![${alt}](${storageKey})`;
    }
    return match;
  });
}
