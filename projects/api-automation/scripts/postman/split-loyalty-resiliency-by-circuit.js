const fs = require('fs');
const path = require('path');

const root = process.cwd();
const sourcePath = path.join(
	root,
	'postman-collections',
	'LOYALTY RESILIENCY.postman_collection.json'
);
const outDir = path.join(root, 'postman-collections', 'circuits');

const groups = {
	brand4TransactionCircuit: new Set([
		// Money-moving flow bucket per mapping.
		'SEND TRANSACTION'
	]),
	brand4EpsilonCircuit: new Set([
		// Epsilon reads/writes, offers, catalog, certs, tiers, discounts, profile reads.
		'REGISTER OFFER',
		'CERTIFICATES',
		'PROFILE REWARDS',
		'CATALOG',
		'GET PROFILE',
		'TIER UPGRADE',
		'GET MY ACTIVITY',
		'GET TRANSACTION BY ID',
		'CALCULATE DISCOUNT',
		'PROMO CODE',
		'REDEEM POINTS',
		'CANCEL REDEEM POINTS',
		// Contains additional epsilon circuit-open endpoints like getPoints/addPoints/redeemReward/cancelRedeem.
		'CB PREPARED - brand4EPSILONCIRCUIT (FROM EARLIER)'
	]),
	brand4ProfileCircuit: new Set([
		// Profile writes only.
		'CREATE PROFILE',
		'UPDATE PROFILE',
		'DELETE PROFILE'
	]),
	brand4TokenCircuit: new Set([
		// No token request folder exists in this source collection.
	])
};

function clone(obj) {
	return JSON.parse(JSON.stringify(obj));
}

function asArray(value) {
	if (!value) {
		return [];
	}
	return Array.isArray(value) ? value : [value];
}

function getRequestRawUrl(req) {
	if (!req || !req.url) {
		return '';
	}
	if (typeof req.url === 'string') {
		return req.url;
	}
	return req.url.raw || '';
}

function rawUrlIncludes(req, fragment) {
	return getRequestRawUrl(req).toLowerCase().includes(fragment.toLowerCase());
}

function getUrlPathFromRaw(raw) {
	if (!raw) {
		return '';
	}
	try {
		const parsed = new URL(raw.replace('{{baseUrl}}', 'https://placeholder.local'));
		return parsed.pathname || '';
	} catch (_err) {
		const withoutQuery = raw.split('?')[0];
		return withoutQuery.replace(/^https?:\/\/[^/]+/i, '');
	}
}

function toTitleCase(input) {
	return String(input)
		.replace(/[-_]+/g, ' ')
		.trim()
		.split(/\s+/)
		.filter(Boolean)
		.map((s) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase())
		.join(' ');
}

function getNormalizedNameFromPath(method, pathName) {
	const key = `${method.toUpperCase()} ${pathName}`;
	const map = {
		'POST /loyalty/v4/brand/b4/rewards/apply': 'applyPromoCode',
		'POST /loyalty/v4/brand/b4/rewards/remove': 'removePromoCode',
		'GET /loyalty/v4/brand/b4/profiles/{{lmsprofileid}}/points/balancedetails': 'getPoints',
		'POST /loyalty/v4/brand/b4/profiles/{{lmsprofileid}}/redemptions/points/adjustments': 'addPoints',
		'POST /loyalty/v4/brand/b4/profiles/{{lmsprofileid}}/rewards/redeem': 'redeemRewardCertificate',
		'POST /loyalty/v4/brand/b4/profiles/{{lmsprofileid}}/activities/reactivaterewards': 'cancelRedeemCertificate',
		'POST /loyalty/v4/brand/b4/profiles/{{lmsprofileid}}/redemptions/points/confirm': 'confirmRedemption',
		'DELETE /loyalty/v4/brand/{{brand}}/profiles/{{lmsprofileid}}': 'deleteMyAccount',
		'POST /loyalty/v4/brand/{{brand}}/profiles/{{lmsprofileid}}/references': 'editPostingKeys_add',
		'DELETE /loyalty/v4/brand/{{brand}}/profiles/{{lmsprofileid}}/references': 'editPostingKeys_delete'
	};
	const normalizedKey = key.toLowerCase();
	if (map[normalizedKey]) {
		return map[normalizedKey];
	}
	const segments = pathName.split('/').filter(Boolean);
	const tail = segments.slice(-2).join(' ');
	return `${method.toUpperCase()} ${toTitleCase(tail || pathName)}`.trim();
}

function normalizeRequestName(item) {
	if (!item || !item.request) {
		return;
	}
	const originalName = String(item.name || '');
	const cleaned = originalName
		.replace(/→/g, '->')
		.replace(/?/g, '->')
		.replace(/\s+/g, ' ')
		.trim();

	const method = String(item.request.method || 'REQUEST').toUpperCase();
	const raw = getRequestRawUrl(item.request);
	const pathName = getUrlPathFromRaw(raw);
	const looksLikeUrl = /^https?:\/\//i.test(cleaned) || cleaned.startsWith('{{baseUrl}}/');
	const isOpenScenarioName = /^\d+_\[open\]/i.test(cleaned);
	const hasUuidLikeNoise =
		/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(cleaned) ||
		/\b[0-9a-f]{32}\b/i.test(cleaned);

	if (looksLikeUrl && pathName) {
		item.name = getNormalizedNameFromPath(method, pathName);
		return;
	}

	if ((isOpenScenarioName || hasUuidLikeNoise) && pathName) {
		const normalized = getNormalizedNameFromPath(method, pathName);
		item.name = isOpenScenarioName ? `${normalized} (Open Circuit)` : normalized;
		return;
	}

	item.name = cleaned || getNormalizedNameFromPath(method, pathName);
}

function removeInternalControlRequests(items) {
	const controlNames = new Set(['1_forceOpen', '19_reset', '99_reset']);
	const result = [];
	for (const item of items || []) {
		if (item.item) {
			item.item = removeInternalControlRequests(item.item);
			result.push(item);
			continue;
		}
		const name = String(item.name || '');
		if (controlNames.has(name)) {
			continue;
		}
		result.push(item);
	}
	return result;
}

function shouldAssertCircuitBehavior(req) {
	const raw = getRequestRawUrl(req).toLowerCase();
	return raw.includes('/loyalty/v4/brand/');
}

function normalizeLoyaltyUrlToBaseUrl(req) {
	const raw = getRequestRawUrl(req);
	if (!raw || !raw.toLowerCase().includes('/loyalty/')) {
		return;
	}

	let parsed;
	try {
		parsed = new URL(raw);
	} catch (_err) {
		return;
	}

	const pathname = parsed.pathname || '';
	const search = parsed.search || '';
	const pathSegments = pathname.split('/').filter(Boolean);

	req.url = {
		raw: `{{baseUrl}}${pathname}${search}`,
		host: ['{{baseUrl}}'],
		path: pathSegments
	};

	if (parsed.searchParams && [...parsed.searchParams.keys()].length > 0) {
		req.url.query = [];
		for (const [key, value] of parsed.searchParams.entries()) {
			req.url.query.push({ key, value });
		}
	}
}

// guest/rewards has no fallback registered � 500 is the expected open-circuit response
const EXPECT_500_URLS = ['/guest/rewards', '/guests/rewards'];

function getExpectedStatusForItem(item) {
	const raw = getRequestRawUrl(item.request).toLowerCase();
	for (const frag of EXPECT_500_URLS) {
		if (raw.includes(frag)) return 500;
	}
	return 503;
}

function upsertCircuitTestEvent(item) {
	const events = asArray(item.event);
	const filtered = events.filter((ev) => ev.listen !== 'test');
	const raw = getRequestRawUrl(item.request);
	const expectedStatus = getExpectedStatusForItem(item);
	const assert503Payload = expectedStatus === 503;

	const script = [
		`const expectedStatus = ${expectedStatus};`,
		"const code = pm.response.code;",
		"let body = {};",
		"try { body = pm.response.json(); } catch (e) { body = {}; }",
		"if (code >= 200 && code < 300) {",
		`  pm.test('BUG: endpoint must not return 2xx while circuit is open', () => pm.expect.fail('Circuit-open endpoint returned ' + code + ' for ${item.name} (${raw}). Expected ' + expectedStatus + '.'));`,
		"}",
		"if (code >= 400 && code < 500 && code !== expectedStatus) {",
		"  pm.test('PAYLOAD ISSUE: endpoint returned unexpected 4xx', () => pm.expect.fail('Received ' + code + ' for ' + JSON.stringify(pm.info.requestName) + ' (' + pm.request.url.toString() + '). Expected ' + expectedStatus + ' from open circuit.'));",
		"}",
		"if (code >= 500 && code !== expectedStatus) {",
		"  pm.test('BUG: endpoint returned non-expected 5xx', () => pm.expect.fail('Received ' + code + ' for ' + JSON.stringify(pm.info.requestName) + ' (' + pm.request.url.toString() + '). Expected ' + expectedStatus + '.'));",
		"}",
		"pm.test('Expected configured status when circuit is open', () => pm.expect(code).to.eql(expectedStatus));"
	];

	if (assert503Payload) {
		script.push(
			"pm.test('503 body has required error fields', () => {",
			"  pm.expect(body.errorMessage).to.be.a('string').and.not.empty;",
			"  pm.expect(body.errors).to.be.an('array');",
			"});"
		);
	}

	filtered.push({
		listen: 'test',
		script: {
			type: 'text/javascript',
			exec: script
		}
	});

	item.event = filtered;
}

function upsertTransactionHelperCaptureEvent(item, type) {
	const events = asArray(item.event);
	const filtered = events.filter((ev) => ev.listen !== 'test');
	const base = [
		"let body = {};",
		"try { body = pm.response.json(); } catch (e) { body = {}; }"
	];
	if (type === 'tally') {
		base.push(
			"const bagId = body.bagId || body.id || (body.data && (body.data.bagId || body.data.id));",
			"if (bagId) { pm.collectionVariables.set('bagId', bagId); }",
			"pm.test('tally helper executed', () => pm.expect(pm.response.code).to.be.oneOf([200, 201]));"
		);
	}
	if (type === 'init') {
		base.push(
			"let paymentKey = '';",
			"let paymentKeySource = '';",
			"if (body.paymentKeys && body.paymentKeys[0]) { paymentKey = body.paymentKeys[0]; paymentKeySource = 'paymentKeys[0]'; }",
			"else if (body.data && body.data.paymentKeys && body.data.paymentKeys[0]) { paymentKey = body.data.paymentKeys[0]; paymentKeySource = 'data.paymentKeys[0]'; }",
			"else if (body.payment && body.payment.paymentKeys && body.payment.paymentKeys[0]) { paymentKey = body.payment.paymentKeys[0]; paymentKeySource = 'payment.paymentKeys[0]'; }",
			"else if (body.accessToken) { paymentKey = body.accessToken; paymentKeySource = 'accessToken'; }",
			"else if (body.data && body.data.accessToken) { paymentKey = body.data.accessToken; paymentKeySource = 'data.accessToken'; }",
			"if (paymentKey) { pm.collectionVariables.set('paymentKey', paymentKey); }",
			"if (paymentKeySource) { pm.collectionVariables.set('paymentKeySource', paymentKeySource); }",
			"console.log('cc/init helper capture', JSON.stringify({ paymentKeySource, paymentKeyLength: paymentKey ? String(paymentKey).length : 0 }));",
			"pm.test('cc init helper executed', () => pm.expect(pm.response.code).to.be.oneOf([200, 201]));"
		);
	}
	filtered.push({
		listen: 'test',
		script: {
			type: 'text/javascript',
			exec: base
		}
	});
	item.event = filtered;
}

function patchSubmitBodyToUseVariables(item) {
	if (!item.request || !item.request.body || !item.request.body.raw) {
		return;
	}
	let parsed;
	try {
		parsed = JSON.parse(item.request.body.raw);
	} catch (_err) {
		return;
	}
	parsed.bagId = '{{bagId}}';
	if (parsed.fulfillment && typeof parsed.fulfillment === 'object') {
		parsed.fulfillment.asap = true;
		parsed.fulfillment.fulfillmentTime = '{{submitFulfillmentTime}}';
	}
	if (Array.isArray(parsed.payment) && parsed.payment.length > 0) {
		parsed.payment[0].paymentKeys = ['{{paymentKey}}'];
	}
	item.request.body.raw = JSON.stringify(parsed, null, 2);
}

function upsertSubmitPrerequestEvent(item) {
	const events = asArray(item.event);
	const filtered = events.filter((ev) => ev.listen !== 'prerequest');
	filtered.push({
		listen: 'prerequest',
		script: {
			type: 'text/javascript',
			exec: [
				"const dt = new Date(Date.now() + 15 * 60 * 1000).toISOString();",
				"pm.collectionVariables.set('submitFulfillmentTime', dt);",
				"const bagId = pm.collectionVariables.get('bagId') || '';",
				"const paymentKey = pm.collectionVariables.get('paymentKey') || '';",
				"const paymentKeySource = pm.collectionVariables.get('paymentKeySource') || 'unknown';",
				"const unresolved = /\{\{.+\}\}/.test(paymentKey);",
				"console.log('submit prerequest helper state', JSON.stringify({ hasBagId: !!bagId, bagIdLength: String(bagId).length, hasPaymentKey: !!paymentKey, paymentKeyLength: String(paymentKey).length, paymentKeySource, unresolvedPaymentKey: unresolved, submitFulfillmentTime: dt }));"
			]
		}
	});
	item.event = filtered;
}

function patchTransactionRequestBehavior(item) {
	if (!item || !item.request) {
		return;
	}
	if (rawUrlIncludes(item.request, '/orders/tally')) {
		upsertTransactionHelperCaptureEvent(item, 'tally');
		return;
	}
	if (rawUrlIncludes(item.request, '/payments/cc/init')) {
		upsertTransactionHelperCaptureEvent(item, 'init');
		return;
	}
	if (rawUrlIncludes(item.request, '/orders/submit')) {
		patchSubmitBodyToUseVariables(item);
		upsertSubmitPrerequestEvent(item);
	}
}

function walkAndPatchAssertions(items) {
	for (const item of items || []) {
		if (item.request) {
			normalizeRequestName(item);
			patchTransactionRequestBehavior(item);
		}
		if (item.request && shouldAssertCircuitBehavior(item.request)) {
			normalizeLoyaltyUrlToBaseUrl(item.request);
			upsertCircuitTestEvent(item);
		}
		if (item.item) {
			walkAndPatchAssertions(item.item);
		}
	}
}

function createForceOpenRequest(circuitName) {
	return {
		name: '1_forceOpen',
		request: {
			method: 'POST',
			header: [
				{
					key: 'channel-id',
					value: 'WEBOA'
				}
			],
			url: {
				raw: `{{baseUrl}}/loyalty/test/circuit-breaker/${circuitName}/open`,
				host: ['{{baseUrl}}'],
				path: ['loyalty', 'test', 'circuit-breaker', circuitName, 'open']
			}
		},
		event: [
			{
				listen: 'test',
				script: {
					type: 'text/javascript',
					exec: [
						"pm.test('Force open returns 200', () => pm.response.to.have.status(200));"
					]
				}
			}
		]
	};
}

function createResetRequest(circuitName) {
	return {
		name: '99_reset',
		request: {
			method: 'PUT',
			header: [
				{
					key: 'channel-id',
					value: 'WEBOA'
				}
			],
			url: {
				raw: `{{baseUrl}}/loyalty/brand/{{brand}}/resilience/circuitbreaker/${circuitName}/reset`,
				host: ['{{baseUrl}}'],
				path: [
					'loyalty',
					'brand',
					'{{brand}}',
					'resilience',
					'circuitbreaker',
					circuitName,
					'reset'
				]
			}
		},
		event: [
			{
				listen: 'test',
				script: {
					type: 'text/javascript',
					exec: [
						"pm.test('Reset returns 200', () => pm.response.to.have.status(200));"
					]
				}
			}
		]
	};
}

function getExpectedErrorCode(circuitName) {
	if (circuitName === 'brand4TransactionCircuit') {
		return 'L08520';
	}
	if (circuitName === 'brand4EpsilonCircuit') {
		return 'L08521';
	}
	if (circuitName === 'brand4ProfileCircuit') {
		return 'L08522';
	}
	return 'L08523';
}

function buildCollection(base, circuitName, items) {
	const c = clone(base);
	c.info = c.info || {};
	c.info.name = `LOYALTY RESILIENCY - ${circuitName.toUpperCase()} CIRCUIT`;
	const copiedItems = removeInternalControlRequests(clone(items));
	if (circuitName === 'brand4ProfileCircuit') {
		const createFolder = copiedItems.find((i) => i.name === 'CREATE PROFILE');
		const updateFolder = copiedItems.find((i) => i.name === 'UPDATE PROFILE');
		const deleteFolder = copiedItems.find((i) => i.name === 'DELETE PROFILE');
		const ordered = [];
		if (createFolder) ordered.push(createFolder);
		if (updateFolder) ordered.push(updateFolder);
		if (deleteFolder) ordered.push(deleteFolder);
		if (ordered.length) {
			copiedItems.length = 0;
			copiedItems.push(...ordered);
		}
	}
	walkAndPatchAssertions(copiedItems);
	c.item = [
		createForceOpenRequest(circuitName),
		...copiedItems,
		createResetRequest(circuitName)
	];
	c.variable = [
		{
			key: 'baseUrl',
			value: 'https://loyalty-adapter-v0.b4-api.uat.staging.example',
			type: 'string'
		},
		{
			key: 'brand',
			value: 'B4',
			type: 'string'
		},
		{
			key: 'expectedErrorCode',
			value: getExpectedErrorCode(circuitName),
			type: 'string'
		},
		{
			key: 'expectedStatusCode',
			value: '503',
			type: 'string'
		},
		{
			key: 'profileId',
			value: 'ab059ede-c60f-4830-b901-a5c33484afb1',
			type: 'string'
		},
		{
			key: 'lmsProfileId',
			value: 'eba78af2-d472-4b47-ba2c-44abcccedd7d',
			type: 'string'
		},
		{
			key: 'sysOfferId',
			value: '04ec4a79-04ad-bee4-fd5d-7d0cc365dffb',
			type: 'string'
		},
		{
			key: 'storeId',
			value: '357492',
			type: 'string'
		},
		{
			key: 'startDate',
			value: '2026-07-01',
			type: 'string'
		},
		{
			key: 'endDate',
			value: '2026-08-08',
			type: 'string'
		},
		{
			key: 'page',
			value: '0',
			type: 'string'
		},
		{
			key: 'size',
			value: '10',
			type: 'string'
		},
		{
			key: 'externalReferenceType',
			value: 'DDCARDNUMBER',
			type: 'string'
		},
		{
			key: 'externalReferenceValue',
			value: '1010000094182756',
			type: 'string'
		}
	];
	return c;
}

function buildMasterCollection(base, byCircuitItems) {
	const c = clone(base);
	c.info = c.info || {};
	c.info.name = 'LOYALTY RESILIENCY - brand4CircuitMaster';

	const circuits = [
		{ key: 'brand4TransactionCircuit', label: 'TRANSACTION CIRCUIT' },
		{ key: 'brand4EpsilonCircuit', label: 'EPSILON CIRCUIT' },
		{ key: 'brand4ProfileCircuit', label: 'PROFILE CIRCUIT' }
	];

	c.item = circuits.map((entry) => {
		const child = buildCollection(base, entry.key, byCircuitItems[entry.key] || []);
		return {
			name: entry.label,
			item: child.item
		};
	});

	c.variable = [
		{
			key: 'baseUrl',
			value: 'https://loyalty-adapter-v0.b4-api.uat.staging.example',
			type: 'string'
		},
		{
			key: 'brand',
			value: 'B4',
			type: 'string'
		}
	];

	return c;
}

function buildAutoRunCollection(base, byCircuitItems) {
	const c = buildMasterCollection(base, byCircuitItems);
	c.info.name = 'LOYALTY RESILIENCY - brand4UAT-AutoRun';
	return c;
}

// LWL Points endpoints live in the CB Prepared epsilon folder but are guarded by profileCircuit.
const PROFILE_CROSSOVER_URLS = [
	'/redemptions/points',
	'/redemptions/points/confirm',
	'/redemptions/points/cancel'
];

// getProfileByPostingKey is on brand4ProfileCircuit � epsilon-open has zero effect on it
const PROFILE_CROSSOVER_NAMES = new Set(['getProfileByPostingKey']);

function isCrossoverToProfile(item) {
	if (!item.request) return false;
	const raw = getRequestRawUrl(item.request).toLowerCase();
	const name = String(item.name || '');
	return PROFILE_CROSSOVER_URLS.some((f) => raw.includes(f)) || PROFILE_CROSSOVER_NAMES.has(name);
}

function extractCrossoverItems(items) {
	const stay = [];
	const move = [];
	for (const item of items || []) {
		if (item.item) {
			// folder � recurse and split
			const stayChildren = [];
			const moveChildren = [];
			for (const child of item.item) {
				if (child.request && isCrossoverToProfile(child)) {
					moveChildren.push(child);
				} else {
					stayChildren.push(child);
				}
			}
			if (stayChildren.length) {
				const kept = Object.assign({}, item, { item: stayChildren });
				stay.push(kept);
			}
			move.push(...moveChildren);
		} else {
			stay.push(item);
		}
	}
	return { stay, move };
}

function main() {
	if (!fs.existsSync(sourcePath)) {
		throw new Error(`Source collection not found: ${sourcePath}`);
	}

	const src = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
	const topItems = src.item || [];

	const byCircuit = {
		brand4TransactionCircuit: [],
		brand4EpsilonCircuit: [],
		brand4ProfileCircuit: [],
		brand4TokenCircuit: []
	};

	const unassigned = [];
	for (const item of topItems) {
		const name = (item.name || '').trim().toUpperCase();
		let assigned = false;
		for (const [circuitName, allowed] of Object.entries(groups)) {
			if (allowed.has(name)) {
				byCircuit[circuitName].push(item);
				assigned = true;
				break;
			}
		}
		if (!assigned) {
			unassigned.push(item.name || '(unnamed)');
		}
	}

	// Pull LWL Points endpoints out of epsilon and into profile circuit
	const { stay: epsilonOnly, move: lwlPointsItems } = extractCrossoverItems(byCircuit.brand4EpsilonCircuit);
	byCircuit.brand4EpsilonCircuit = epsilonOnly;
	if (lwlPointsItems.length) {
		byCircuit.brand4ProfileCircuit.push({ name: 'LWL POINTS (CROSSOVER)', item: lwlPointsItems });
		console.log(`Moved ${lwlPointsItems.length} LWL Points items to brand4ProfileCircuit`);
	}

	fs.mkdirSync(outDir, { recursive: true });

	for (const circuitName of Object.keys(byCircuit)) {
		const items = byCircuit[circuitName];
		const out = buildCollection(src, circuitName, items);
		const outPath = path.join(
			outDir,
			`LOYALTY RESILIENCY - ${circuitName}.postman_collection.json`
		);
		fs.writeFileSync(outPath, `${JSON.stringify(out, null, 2)}\n`, 'utf8');
		console.log(`${circuitName}: ${items.length} top-level folders -> ${outPath}`);
	}

	const master = buildMasterCollection(src, byCircuit);
	const masterPath = path.join(
		outDir,
		'LOYALTY RESILIENCY - brand4CircuitMaster.postman_collection.json'
	);
	fs.writeFileSync(masterPath, `${JSON.stringify(master, null, 2)}\n`, 'utf8');
	console.log(`master collection -> ${masterPath}`);

	const autoRun = buildAutoRunCollection(src, byCircuit);
	const autoRunPath = path.join(
		outDir,
		'LOYALTY RESILIENCY - brand4UAT-AutoRun.postman_collection.json'
	);
	fs.writeFileSync(autoRunPath, `${JSON.stringify(autoRun, null, 2)}\n`, 'utf8');
	console.log(`autorun collection -> ${autoRunPath}`);

	if (unassigned.length) {
		console.log('Unassigned top-level folders:');
		for (const name of unassigned) {
			console.log(`- ${name}`);
		}
	}
}

main();
