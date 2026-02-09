import { env, createExecutionContext, waitOnExecutionContext, SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import worker from '../src/index';

// For now, you'll need to do something like this to get a correctly-typed
// `Request` to pass to `worker.fetch()`.
const IncomingRequest = Request<unknown, IncomingRequestCfProperties>;

describe('lifee-api worker', () => {
	it('returns 404 on non-/decision routes', async () => {
		const request = new IncomingRequest('http://example.com/');
		const ctx = createExecutionContext();
		const response = await worker.fetch(request, env, ctx);
		await waitOnExecutionContext(ctx);
		expect(response.status).toBe(404);
		expect(await response.text()).toMatchInlineSnapshot(`"Not Found"`);
	});

	it('returns CORS headers on OPTIONS', async () => {
		const request = new IncomingRequest('http://example.com/decision', { method: 'OPTIONS' });
		const ctx = createExecutionContext();
		const response = await worker.fetch(request, env, ctx);
		await waitOnExecutionContext(ctx);
		expect(response.status).toBe(200);
		expect(response.headers.get('Access-Control-Allow-Origin')).toBe('*');
		expect(response.headers.get('Access-Control-Allow-Methods')).toContain('POST');
	});

	it('returns 500 JSON when GEMINI_API_KEY missing', async () => {
		const request = new IncomingRequest('http://example.com/decision', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ situation: 'test', personas: [{ id: 'serene', name: 'SERENE' }] }),
		});
		const ctx = createExecutionContext();
		// Explicitly override env for this test
		const response = await worker.fetch(request, { GEMINI_API_KEY: '' } as any, ctx);
		await waitOnExecutionContext(ctx);
		expect(response.status).toBe(500);
		expect(await response.json()).toMatchObject({ error: 'Missing GEMINI_API_KEY' });
	});

	it('integration: / is still Not Found', async () => {
		const response = await SELF.fetch('https://example.com/');
		expect(response.status).toBe(404);
		expect(await response.text()).toMatchInlineSnapshot(`"Not Found"`);
	});
});
