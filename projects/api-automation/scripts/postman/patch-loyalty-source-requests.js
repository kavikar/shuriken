const fs = require('fs');
const path = require('path');

const srcPath = path.join(process.cwd(), 'postman-collections', 'LOYALTY RESILIENCY.postman_collection.json');
const src = JSON.parse(fs.readFileSync(srcPath, 'utf8'));

function getRaw(urlObj) {
	if (!urlObj) return '';
	if (typeof urlObj === 'string') return urlObj;
	return String(urlObj.raw || '');
}

let patchCount = 0;

function patch(items) {
	for (const item of items || []) {
		const name = String(item.name || '');

		if (item.request) {
			// Fix 1 & 2: calculateDiscount profile — replace old Epsilon body with order wrapper
			if (name.includes('calculateDiscount/profile')) {
				item.request.body = item.request.body || {};
				item.request.body.mode = 'raw';
				item.request.body.raw = JSON.stringify({
					order: {
						subTotal: '5.99',
						items: [{ lineItemId: 1, productId: 'PROD-001', price: '5.99', quantity: 1, posIds: ['12345'] }],
						fulfillment: { locationId: '357492' }
					},
					isLoyaltyEnabled: true,
					digitalId: '{{cardPostingKey}}'
				}, null, 2);
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}

			// Fix 3: calculateDiscount guest — same order wrapper
			if (name.includes('calculateDiscount/guest')) {
				item.request.body = item.request.body || {};
				item.request.body.mode = 'raw';
				item.request.body.raw = JSON.stringify({
					order: {
						subTotal: '5.99',
						items: [{ lineItemId: 1, productId: 'PROD-001', price: '5.99', quantity: 1, posIds: ['12345'] }],
						fulfillment: { locationId: '357492' }
					},
					isLoyaltyEnabled: true,
					digitalId: '{{cardPostingKey}}'
				}, null, 2);
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}

			// Fix 4: redemptions/points — camelCase body with required fields
			if (name.includes('purchaseCertificates/redeemPoints')) {
				item.request.body.raw = JSON.stringify({
					transactionId: '00000000-0000-0000-0000-000000000001',
					description: 'Circuit breaker smoke test',
					points: 100
				}, null, 2);
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}

			// Fix 5: points/confirm — just certificateId
			if (name.includes('confirmRedemption')) {
				item.request.body.raw = JSON.stringify({
					certificateId: '00000000-0000-0000-0000-000000000001'
				}, null, 2);
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}

			// Fix 6: points/adjustments — camelCase
			if (name.includes('addPoints/adjustments')) {
				item.request.body.raw = JSON.stringify({
					adjustmentReasonCode: 'GUESTREL',
					adjustmentComment: 'Circuit breaker smoke test',
					numPoints: '100'
				}, null, 2);
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}

			// Fix 7: guests/rewards → guest/rewards (singular)
			if (name.includes('getGuestRewards')) {
				const urlObj = item.request.url;
				if (typeof urlObj === 'string') {
					item.request.url = urlObj.replace('/guests/rewards', '/guest/rewards');
				} else {
					if (urlObj.raw) urlObj.raw = urlObj.raw.replace('/guests/rewards', '/guest/rewards');
					if (Array.isArray(urlObj.path)) {
						urlObj.path = urlObj.path.map((seg) => (seg === 'guests' ? 'guest' : seg));
					}
				}
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}

			// Fix 8: cancelCertificate DELETE → POST /certificate/return with body + Content-Type header
			if (name.includes('cancelCertificate')) {
				item.request.method = 'POST';
				item.request.url = {
					raw: '{{baseUrl}}/loyalty/v4/brand/{{brand}}/profiles/{{lmsProfileId}}/certificate/return',
					host: ['{{baseUrl}}'],
					path: ['loyalty', 'v4', 'brand', '{{brand}}', 'profiles', '{{lmsProfileId}}', 'certificate', 'return']
				};
				item.request.body = {
					mode: 'raw',
					raw: JSON.stringify({
						certificateNumber: '51213271894624227409',
						location: { id: 306106, deviceDateTime: '2020-08-03T17:00:31Z' }
					}, null, 2)
				};
				// ensure Content-Type is present — generator can strip it on non-JSON requests
				const existingHeaders = Array.isArray(item.request.header) ? item.request.header : [];
				const hasCT = existingHeaders.some((h) => h.key && h.key.toLowerCase() === 'content-type');
				if (!hasCT) {
					existingHeaders.push({ key: 'Content-Type', value: 'application/json' });
				}
				item.request.header = existingHeaders;
				item.name = '12_[OPEN] cancelCertificate -> expect 503';
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}

			// Fix 9: campaign/updatecampaign — add profiles/{lmsProfileId} segment + real body
			if (name.includes('registerOffer')) {
				const urlObj = item.request.url;
				if (typeof urlObj === 'string') {
					item.request.url = urlObj.replace(
						'/brand/{{brand}}/campaign/',
						'/brand/{{brand}}/profiles/{{lmsProfileId}}/campaign/'
					);
				} else {
					if (urlObj.raw) {
						urlObj.raw = urlObj.raw.replace(
							'/brand/{{brand}}/campaign/',
							'/brand/{{brand}}/profiles/{{lmsProfileId}}/campaign/'
						);
					}
					if (Array.isArray(urlObj.path)) {
						const idx = urlObj.path.indexOf('{{brand}}');
						if (idx !== -1 && urlObj.path[idx + 1] === 'campaign') {
							urlObj.path.splice(idx + 1, 0, 'profiles', '{{lmsProfileId}}');
						}
					}
				}
				// use a dummy campaign code — circuit open should 503 before body validation
				item.request.body = item.request.body || {};
				item.request.body.mode = 'raw';
				item.request.body.raw = JSON.stringify({ campaignCode: 'B4_SMOKE_TEST', status: 'A' }, null, 2);
				// remove any pre-request script we added previously
				item.event = (Array.isArray(item.event) ? item.event : []).filter((e) => e.listen !== 'prerequest');
				console.log(`PATCHED: ${name}`);
				patchCount++;
			}
		}

		if (item.item) patch(item.item);
	}
}

patch(src.item);
fs.writeFileSync(srcPath, JSON.stringify(src, null, 2) + '\n', 'utf8');
console.log(`\nDone. ${patchCount} patches applied -> ${srcPath}`);
