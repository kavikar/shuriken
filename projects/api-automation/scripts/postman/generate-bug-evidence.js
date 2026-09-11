const fs = require('fs');

const runDir = 'reports/brand4/loyalty-adapter/final-run-20260809-204736';
const run = JSON.parse(fs.readFileSync(runDir + '/epsilon.newman.json', 'utf8'));

const skipNames = new Set(['1_forceOpen', '99_reset', '19_reset']);
const isGuest = (n) => n.toLowerCase().includes('guest') && n.toLowerCase().includes('reward');
const isCampaign = (n) => n.toLowerCase().includes('campaign');

const fails = run.run.executions.filter((e) => {
	const n = String(e.item.name);
	const code = Number(e.response.code);
	const expected = isGuest(n) ? 500 : 503;
	return !skipNames.has(n) && !isCampaign(n) && code !== expected;
});

let md = '# Brand Four Loyalty Adapter — Epsilon Circuit Open Bug Evidence\n\n';
md += '**Environment:** UAT  \n';
md += '**Circuit:** brand4EpsilonCircuit  \n';
md += '**Run date:** 2026-08-09  \n';
md += '**Expected:** All guarded endpoints return 503 when circuit is open.  \n';
md += '**Actual:** 5 endpoints return 200 — circuit breaker is not applied on backend.\n\n---\n\n';

fails.forEach((e, i) => {
	const n = String(e.item.name);
	const code = Number(e.response.code);
	const method = String(e.request.method);
	const urlObj = e.request.url;
	let url = (urlObj && typeof urlObj === 'object' && urlObj.raw) ? String(urlObj.raw) : String(urlObj || '');
	url = url
		.replace('{{baseUrl}}', 'https://loyalty-adapter-v0.b4-api.uat.staging.example')
		.replace('{{brand}}', 'B4')
		.replace(/\{\{lmsProfileId\}\}/g, '3ed48d62-9f50-4ea3-a974-a192d53c4f0e');

	let respBody = '';
	if (e.response.stream && e.response.stream.data) {
		const d = e.response.stream.data;
		respBody = Array.isArray(d) ? Buffer.from(d).toString('utf8') : String(d);
	}
	let respJson = {};
	try { respJson = JSON.parse(respBody); } catch (_) {}
	const respDisplay = JSON.stringify(respJson, null, 2).substring(0, 600);

	md += '## Bug ' + (i + 1) + ': ' + n + '\n\n';
	md += '| Field | Value |\n|---|---|\n';
	md += '| Endpoint | `' + method + ' ' + url + '` |\n';
	md += '| Expected | 503 |\n';
	md += '| Actual | ' + code + ' |\n';
	md += '| Circuit | brand4EpsilonCircuit |\n';
	md += '| Root cause | Endpoint not guarded by `@CircuitBreaker(name = "brand4EpsilonCircuit")` on backend Feign client |\n\n';
	md += '**Request:**\n```\n' + method + ' ' + url + '\nchannel-id: WEBOA\n```\n\n';
	md += '**Response (' + code + '):**\n```json\n' + respDisplay + '\n```\n\n---\n\n';
});

const outPath = runDir + '/epsilon-circuit-bug-evidence.md';
fs.writeFileSync(outPath, md, 'utf8');
console.log('Written:', outPath);
console.log('Bugs:', fails.length);
fails.forEach((e) => console.log(' -', e.item.name, '->', e.response.code));
