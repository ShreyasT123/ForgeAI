import {tool} from 'langchain';
import {z} from 'zod';

import {getSettings} from '../utils/config.js';
import {getLogger} from '../utils/logger.js';
import {truncate} from '../utils/security.js';

type SearchResult = {title?: string; url?: string; snippet?: string};

const logger = getLogger('tools.search');

function cfg() {
	return getSettings().tools.search;
}

async function fetchJson(url: string, init: RequestInit, timeoutMs: number) {
	const controller = new AbortController();
	const timer = setTimeout(() => {
		controller.abort();
	}, timeoutMs);
	try {
		const resp = await fetch(url, {...init, signal: controller.signal});
		if (!resp.ok) {
			throw new Error(`HTTP ${resp.status}`);
		}
		return await resp.json();
	} finally {
		clearTimeout(timer);
	}
}

async function tavilySearch(query: string, limit: number): Promise<SearchResult[]> {
	const apiKey = process.env.TAVILY_API_KEY;
	if (!apiKey) {
		throw new Error('TAVILY_API_KEY not set');
	}
	const data = await fetchJson(
		'https://api.tavily.com/v1/search',
		{
			method: 'POST',
			headers: {
				Authorization: `Bearer ${apiKey}`,
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({query, limit}),
		},
		cfg().timeout_seconds * 1000,
	);
	const results = Array.isArray(data?.results) ? data.results : [];
	return results.slice(0, limit).map((r: any) => ({
		title: r?.title,
		url: r?.link,
		snippet: r?.snippet,
	}));
}

async function serpapiSearch(query: string, limit: number): Promise<SearchResult[]> {
	const apiKey = process.env.SERPAPI_KEY;
	if (!apiKey) {
		throw new Error('SERPAPI_KEY not set');
	}
	const url = new URL('https://serpapi.com/search');
	url.searchParams.set('q', query);
	url.searchParams.set('num', String(limit));
	url.searchParams.set('api_key', apiKey);
	const data = await fetchJson(url.toString(), {}, cfg().timeout_seconds * 1000);
	const results = Array.isArray(data?.organic_results) ? data.organic_results : [];
	return results.slice(0, limit).map((r: any) => ({
		title: r?.title,
		url: r?.link,
		snippet: r?.snippet ?? '',
	}));
}

const searchTool = tool(
	async ({
		query,
		engine = 'all',
		limit = 3,
	}: {
		query: string;
		engine?: 'tavily' | 'serpapi' | 'all';
		limit?: number;
	}) => {
		logger.info(`search query="${query}" engine=${engine} limit=${limit}`);
		const engines = engine === 'all' ? ['tavily', 'serpapi'] : [engine];
		const results: Record<string, SearchResult[] | string> = {};

		for (const eng of engines) {
			try {
				if (eng === 'tavily') {
					results.tavily = await tavilySearch(query, limit);
				} else if (eng === 'serpapi') {
					results.serpapi = await serpapiSearch(query, limit);
				} else {
					results[eng] = 'Unsupported engine';
				}
			} catch (err) {
				results[eng] = `Error: ${(err as Error).message}`;
			}
		}

		const lines: string[] = [];
		for (const [eng, items] of Object.entries(results)) {
			lines.push(`\n=== ${eng.toUpperCase()} ===`);
			if (typeof items === 'string') {
				lines.push(items);
				continue;
			}
			for (const r of items) {
				lines.push(`- ${r.title ?? '(no title)'}`);
				if (r.url) {
					lines.push(`  ${r.url}`);
				}
				if (r.snippet) {
					lines.push(`  ${r.snippet}`);
				}
			}
		}

		return truncate(lines.join('\n'), cfg().max_output_length);
	},
	{
		name: 'search',
		description: 'Search the web using Tavily, SerpAPI, or both.',
		schema: z.object({
			query: z.string().describe('Search query'),
			engine: z.enum(['tavily', 'serpapi', 'all']).optional().default('all'),
			limit: z.number().min(1).max(10).optional().default(3),
		}),
	},
);

export const SEARCH_TOOLS = [searchTool];
