import type { paths } from '@kiforge/api-types';

import { apiUrl, useSettings } from '@/state/settings';

/**
 * Typed client for the Ki Forge API, using the types generated from FastAPI's OpenAPI schema
 * (`packages/api-types`). Errors arrive as the API's `{"error": {code, message}}` envelope.
 */

type Method = 'get' | 'post' | 'put' | 'patch' | 'delete';
type Op<P extends keyof paths, M extends Method> = NonNullable<paths[P][M]>;
type Json<T> = T extends { content: { 'application/json': infer B } } ? B : undefined;
type Success<R> = R extends { 200: infer A } ? A : R extends { 201: infer A } ? A : R extends { 202: infer A } ? A : never;

export type ResponseOf<P extends keyof paths, M extends Method> =
  Op<P, M> extends { responses: infer R } ? Json<Success<R>> : never;
export type BodyOf<P extends keyof paths, M extends Method> =
  Op<P, M> extends { requestBody?: infer B } ? Json<NonNullable<B>> : never;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }

  /** Network failure (offline, API not running) rather than an answer from the API. */
  get offline(): boolean {
    return this.status === 0;
  }
}

type Options = {
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  signal?: AbortSignal;
};

async function request<T>(method: Method, path: string, opts: Options = {}): Promise<T> {
  const url = new URL(apiUrl() + path);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined) url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = { Accept: 'application/json' };
  const email = useSettings.getState().devEmail;
  if (email) headers['X-Dev-User'] = email;
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method: method.toUpperCase(),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    throw new ApiError(0, 'network_error', e instanceof Error ? e.message : 'network error');
  }
  if (res.status === 204 || res.status === 304) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? 'error', err.message ?? `HTTP ${res.status}`);
  }
  return data as T;
}

export const api = {
  get: <P extends keyof paths>(path: P, opts?: Omit<Options, 'body'>) =>
    request<ResponseOf<P, 'get'>>('get', path as string, opts),
  post: <P extends keyof paths>(path: P, body: BodyOf<P, 'post'>, opts?: Omit<Options, 'body'>) =>
    request<ResponseOf<P, 'post'>>('post', path as string, { ...opts, body }),
  put: <P extends keyof paths>(path: P, body: BodyOf<P, 'put'>, opts?: Omit<Options, 'body'>) =>
    request<ResponseOf<P, 'put'>>('put', path as string, { ...opts, body }),
  patch: <P extends keyof paths>(path: P, body: BodyOf<P, 'patch'>, opts?: Omit<Options, 'body'>) =>
    request<ResponseOf<P, 'patch'>>('patch', path as string, { ...opts, body }),
  /** For paths with parameters, e.g. `/v1/enrollments/{enrollment_id}`: pass the filled-in path. */
  raw: request,
};

export type Me = ResponseOf<'/v1/me', 'get'>;
export type Program = ResponseOf<'/v1/program', 'get'>;
export type Week = ResponseOf<'/v1/week', 'get'>;
export type SyncResponse = ResponseOf<'/v1/sync', 'post'>;
export type SyncRequest = BodyOf<'/v1/sync', 'post'>;
