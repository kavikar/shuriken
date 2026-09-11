/**
 * Comet Batch Prompt Generator
 *
 * Generates optimized Comet-ready batch prompts for the Brand Three Desktop Web tests.
 *
 * Key design decisions:
 *   - Groups 3–7 tests per batch by execution flow similarity
 *   - Uses Comet's recommended template (Role, Environment, Cards, Execution Rules, etc.)
 *   - Avoids redundant store/login instructions within a batch
 *   - Each batch produces ONE complete prompt ready to paste into Comet
 *
 * Usage:
 *   npx ts-node src/generators/comet-batch-generator.ts                     # Preview all batches
 *   npx ts-node src/generators/comet-batch-generator.ts --batch 3           # Generate only batch 3
 *   npx ts-node src/generators/comet-batch-generator.ts --save              # Save all to files
 *   npx ts-node src/generators/comet-batch-generator.ts --keys TE-10075,TE-10059  # Ad-hoc batch
 */

import fs from 'fs';
import path from 'path';
import {
  getConfig,
  getXrayConfig,
  getIssuesByKeys,
  readGherkinDefinition,
  type XrayTestIssue,
} from '../client/xray-client';
import { WEB_TEST_KEYS } from '../registry/web-test-cases';

// ── Constants ──────────────────────────────────────────────────────

const EMAIL = 'user@example.com';
const PASSWORD = 'replace_me';
const UAT_URL = 'https://ignite-brand3.uat.staging.example/';
const STORE_MICROS = '1000 1 Example St';
const STORE_INFOR = '1001 3805 Example Ave';
const ZIP_MICROS = '00000';
const ZIP_INFOR = '00000';

// ── Batch Definitions ──────────────────────────────────────────────
// Each batch groups tests that share similar flows so Comet can
// execute them sequentially without context-switching.

export interface TestBatch {
  id: number;
  name: string;
  description: string;
  /** Which account state: 'signed-in' | 'guest' | 'mixed' */
  authMode: 'signed-in' | 'guest' | 'mixed';
  /** Primary store needed */
  store: 'micros' | 'infor' | 'both' | 'none';
  /** Does this batch place orders (needs payment)? */
  placesOrders: boolean;
  keys: string[];
}

export const EXECUTION_BATCHES: TestBatch[] = [
  // ── Batch 1: Auth & Account Management (no orders, no store needed) ──
  {
    id: 1,
    name: 'Auth & Account',
    description: 'Login, logout, signup, Facebook login, password change — account management flows that do not require a store or order placement.',
    authMode: 'mixed',
    store: 'none',
    placesOrders: false,
    keys: [
      'TE-10076', // Login and Logout
      'TE-10070', // Customer Signup
      'TE-10052', // Facebook Login
      'TE-10064', // Change Password
    ],
  },
  // ── Batch 2: Profile & Payment Management (signed-in, no orders) ──
  {
    id: 2,
    name: 'Profile & Payment Methods',
    description: 'Profile updates, phone OTP, MFA, credit card add/edit — account settings that require sign-in but no order placement.',
    authMode: 'signed-in',
    store: 'none',
    placesOrders: false,
    keys: [
      'TE-10067', // Profile - Update Phone, First Name, Last Name
      'TE-10018', // Profile - Phone OTP Verified
      'TE-10036', // Profile - MFA, Profile Updates, Account Deletion
      'TE-10079', // Payment - New Credit Card Addition
      'TE-10060', // Payment - Credit Card Editing
    ],
  },
  // ── Batch 3: Location, Favorites & Menu Browse (signed-in, store needed, no orders) ──
  {
    id: 3,
    name: 'Location, Favorites & Menu Browse',
    description: 'Store search, map pins, favorite items/locations, guest favorites check, nutrition info — browsing flows without order placement.',
    authMode: 'mixed',
    store: 'micros',
    placesOrders: false,
    keys: [
      'TE-10077', // Location - Map Pin Highlighting
      'TE-10009', // Location - Temporarily Unavailable Status
      'TE-10051', // Favorites - Favorite Items
      'TE-10056', // Favorites - Favorite Location
      'TE-10057', // Favorites - Guest No Favorites
      'TE-10063', // Menu - Nutrition Info
    ],
  },
  // ── Batch 4: Menu, Bag & Modifiers (signed-in, Micros store, no orders) ──
  {
    id: 4,
    name: 'Menu, Bag & Modifiers',
    description: 'Menu item modifications, intensity modifiers in bag, max quantity, temp unavailable — product and bag validation without checkout.',
    authMode: 'signed-in',
    store: 'micros',
    placesOrders: false,
    keys: [
      'TE-10075', // Bag - Max Quantity
      'TE-10053', // Bag - Item Modifiable in Bag
      'TE-10059', // Bag - Modifiers with Intensity in Bag Modal
      'TE-10055', // Menu - Modifiers with Intensity Full Flow (Bag → Checkout → Email)
      'TE-10011', // Menu - Temporarily Unavailable on PLP/PDP
    ],
  },
  // ── Batch 5: Rewards & Offers (signed-in, Micros store) ──
  {
    id: 5,
    name: 'Rewards & Complex Discounts',
    description: 'Reward redemption, no-qualifying alert, size-based pricing, complex discount stacking — reward and offer validation.',
    authMode: 'signed-in',
    store: 'micros',
    placesOrders: false,
    keys: [
      'TE-10016', // Rewards - Coke Your Way Green Apple Size Price
      'TE-10065', // Rewards - Reward Applied to Qualifying Item
      'TE-10078', // Rewards - No Qualifying Items Modal Alert
      'TE-10035', // Discounts - Complex Discount and Offer Stacking
      'TE-10061', // Discounts - Auto-Discount + Promo on Different Products
    ],
  },
  // ── Batch 6: Guest Orders (guest, places orders) ──
  {
    id: 6,
    name: 'Guest Order Flows',
    description: 'Guest checkout flows — pickup and delivery orders with credit card and Apple/Google Pay.',
    authMode: 'guest',
    store: 'both',
    placesOrders: true,
    keys: [
      'TE-10054', // Guest Future Pickup CC (Micros)
      'TE-10066', // Guest ASAP Delivery CC (Micros)
      'TE-10073', // Guest ASAP Pickup Apple/Google Pay (Micros)
    ],
  },
  // ── Batch 7: Auth Orders — Micros Store (signed-in, places orders) ──
  {
    id: 7,
    name: 'Authenticated Orders — Micros',
    description: 'Signed-in order flows on Micros store — delivery with CC, combos with rewards, confirmation email.',
    authMode: 'signed-in',
    store: 'micros',
    placesOrders: true,
    keys: [
      'TE-10058', // Auth Future Delivery CC
      'TE-10074', // Auth Future Delivery Combos + Auto Discount + Reward
      'TE-10017', // Payment Tender Logo on Confirmation
      'TE-10068', // Confirmation Email After Payment
    ],
  },
  // ── Batch 8: Order History & Reorder (signed-in, places orders) ──
  {
    id: 8,
    name: 'Reorder & Signup Order',
    description: 'Order history reorder flows and new signup + order placement.',
    authMode: 'signed-in',
    store: 'micros',
    placesOrders: true,
    keys: [
      'TE-10069', // Reorder from Past Order
      'TE-10050', // Reorder Past Orders + Future Pickup
      'TE-10062', // New Signup + Place ASAP Pickup with Reward
    ],
  },
  // ── Batch 9: Discount Order Flows — Infor Store (places orders) ──
  {
    id: 9,
    name: 'Discount Orders — Infor Store',
    description: 'Auto-discount order flows on Infor (NextGen) store — guest and signed-in, pickup and delivery.',
    authMode: 'mixed',
    store: 'infor',
    placesOrders: true,
    keys: [
      'TE-10037', // Guest Pickup Auto Discount + Auto Discount (Infor)
      'TE-10038', // Signed-In Pickup Auto Discount + Reward (Infor)
      'TE-10039', // Guest Delivery Auto Discount + Multi Qty (Infor)
      'TE-10040', // Signed-In Delivery Auto Discount + Promo (Infor)
    ],
  },
  // ── Batch 10: Discount Order Flows — Micros Store (places orders) ──
  {
    id: 10,
    name: 'Discount Orders — Micros Store',
    description: 'Auto-discount order flows on Micros store — guest and signed-in, pickup and delivery.',
    authMode: 'mixed',
    store: 'micros',
    placesOrders: true,
    keys: [
      'TE-10041', // Guest Pickup Auto Discount + Auto Discount (Micros)
      'TE-10042', // Signed-In Pickup Auto Discount + Promo (Micros)
      'TE-10043', // Guest Delivery Auto Discount + Multi Qty (Micros)
      'TE-10044', // Signed-In Delivery Auto Discount + Reward (Micros)
    ],
  },
  // ── Batch 11: Gift Card Orders (signed-in, places orders) ──
  {
    id: 11,
    name: 'Gift Card Orders',
    description: 'Gift card payment flows — ASAP pickup with promo, future delivery with auto-discount.',
    authMode: 'signed-in',
    store: 'micros',
    placesOrders: true,
    keys: [
      'TE-10071', // GC ASAP Pickup Drinks/Frozen + Promo
      'TE-10072', // GC Future Delivery Food + Auto Discount
    ],
  },
];

// ── Prompt Header Template ─────────────────────────────────────────

function generatePromptHeader(batch: TestBatch): string {
  const storeLines: string[] = [];
  if (batch.store === 'micros' || batch.store === 'both') {
    storeLines.push(`Store Name: ${STORE_MICROS} + zipcode: ${ZIP_MICROS}`);
  }
  if (batch.store === 'infor' || batch.store === 'both') {
    storeLines.push(`Store Name: ${STORE_INFOR} + zipcode: ${ZIP_INFOR}`);
  }
  const storeText = storeLines.length > 0
    ? storeLines.map(s => `[${s}]`).join(' or ')
    : 'No store selection needed for this batch';

  const accountText = batch.authMode === 'guest'
    ? 'Guest (no login needed)'
    : batch.authMode === 'signed-in'
      ? `${EMAIL} / ${PASSWORD}`
      : `${EMAIL} / ${PASSWORD} (some tests use guest mode — noted per test)`;

  return `Role: Act as a QA Expert Tester executing end-to-end functional test cases for Brand Three's web ordering platform on a UAT environment.

ENVIRONMENT: ${UAT_URL}
ACCOUNT: ${accountText}
STORE: ${storeText}

TEST CARDS:
5454 5454 5454 5454; 12/33; 444; ${ZIP_MICROS}
4111 1111 1111 1111; 12/33; 444; ${ZIP_MICROS}

EXECUTION RULES:
- Execute ALL ${batch.keys.length} test cases below one by one, fully, without stopping to ask for confirmation between them
- Take a screenshot at every key evidence moment during each test (login, store confirmed, item selected, item added to bag, bag state, checkout summary, confirmation screen, footer version, any error or unexpected behavior)
- After each screenshot, label it clearly: TC[n]-SS[x]: [what it shows]
- At the end of each test case, output a mini summary block (see format below)
- After ALL test cases are done, output a final consolidated report (see format below)
- The chat export (PDF) will serve as the screenshot evidence — no Word doc needed
${batch.authMode !== 'mixed' ? `- All tests in this batch use ${batch.authMode === 'signed-in' ? 'signed-in' : 'guest'} mode — ${batch.authMode === 'signed-in' ? 'sign in once and stay signed in' : 'do NOT sign in'}` : '- This batch mixes guest and signed-in tests — follow the login instruction per test'}
${batch.store !== 'none' && batch.store !== 'both' ? `- All tests use the same store — select it once at the start and keep it` : ''}
${batch.placesOrders ? '- This batch places real orders — verify confirmation number on each' : '- This batch does NOT place orders — no payment/checkout needed'}

SCREENSHOT MOMENTS (capture at each of these per test case):
- Signed-in state confirmed (account name visible in nav) OR Guest mode confirmed
- Store confirmed in header (if applicable)
- Item selected on menu / reward redeemed (if applicable)
- Item added to bag confirmation (if applicable)
- Bag final state (item name, unit price, qty, subtotal, offer/discount applied if any)
- Checkout summary (if applicable — item, discount, total)
- Order confirmation screen (if applicable — confirmation number)
- Footer showing app version: TM & ©20XX Example Corp Brand Properties LLC vX.X.XX
- Any failure, error, or unexpected behavior

MINI SUMMARY FORMAT (output after each test case):
─────────────────────────────
TC[n] | [Jira ID] | [Test Name]
Result: PASS / FAIL / PARTIAL PASS
Account: [email or Guest]
Store: [store name + ZIP or N/A]
App Version: vX.X.XX
Item(s): [item name] | Price: $X.XX | Qty: X | Subtotal: $X.XX
Pickup: [pickup type or N/A] | Timing: [ASAP or scheduled or N/A]
Offer/Reward: [name if applicable] | Discount in Bag: $X.XX | Discount at Checkout: $X.XX
Confirmation #: [XXXXXXXXX or N/A]
Defect: [description or None]
─────────────────────────────

FINAL CONSOLIDATED REPORT FORMAT (output after ALL test cases):
═══════════════════════════════════════
BRAND3 UAT — BATCH ${batch.id}: ${batch.name.toUpperCase()}
Date: [date] | Tester: ${EMAIL} | Env: UAT | App Version: vX.X.XX
Total: ${batch.keys.length} | Pass: X | Fail: X | Partial: X
═══════════════════════════════════════
| TC# | Jira ID | Test Name | Result | Item | Subtotal | Discount | Confirmation # | Notes |
[one row per test case]
═══════════════════════════════════════`;
}

// ── Test Case Block Generator ──────────────────────────────────────

/**
 * Generates a compact test case block from stored test info.
 * This is what goes into the "TEST CASES TO EXECUTE" section.
 */
export interface TestCaseInfo {
  key: string;
  summary: string;
  gherkinSteps: string[];
  isGuest: boolean;
  store: 'micros' | 'infor' | 'none';
  fulfillment: 'pickup' | 'delivery' | 'none';
  timing: 'asap' | 'future' | 'none';
}

function generateTestCaseBlock(tc: TestCaseInfo, index: number): string {
  const authLine = tc.isGuest
    ? 'Account: Guest (no sign-in)'
    : `Account: ${EMAIL} / ${PASSWORD}`;

  let storeLine = 'Store: N/A';
  if (tc.store === 'micros') storeLine = `Store: ${STORE_MICROS} (ZIP ${ZIP_MICROS})`;
  if (tc.store === 'infor') storeLine = `Store: ${STORE_INFOR} (ZIP ${ZIP_INFOR})`;

  const fulfillLine = tc.fulfillment !== 'none'
    ? `Fulfillment: ${tc.timing !== 'none' ? tc.timing.toUpperCase() + ' ' : ''}${tc.fulfillment.charAt(0).toUpperCase() + tc.fulfillment.slice(1)}`
    : '';

  const steps = tc.gherkinSteps
    .map((s, i) => `   ${i + 1}. ${s}`)
    .join('\n');

  return `Test ${index + 1}: ${tc.key} — ${tc.summary}
Jira: https://your-tenant.atlassian.net/browse/${tc.key}
${authLine}
${storeLine}${fulfillLine ? '\n' + fulfillLine : ''}

Steps:
${steps}`;
}

// ── Full Batch Prompt Generator ────────────────────────────────────

export function generateBatchPrompt(
  batch: TestBatch,
  testInfos: TestCaseInfo[],
): string {
  const header = generatePromptHeader(batch);

  const testBlocks = testInfos.map((tc, i) => generateTestCaseBlock(tc, i));

  return `${header}

TEST CASES TO EXECUTE:

${testBlocks.join('\n\n' + '─'.repeat(50) + '\n\n')}`;
}

// ── Helpers to detect test case properties from summary ────────────

export function inferTestCaseInfo(key: string, summary: string, gherkinSteps: string[]): TestCaseInfo {
  const lower = summary.toLowerCase();

  const isGuest = lower.includes('guest');
  const isDelivery = lower.includes('delivery');
  const isFuture = lower.includes('future');
  const isInfor = lower.includes('infor');

  let store: 'micros' | 'infor' | 'none' = 'none';
  if (isInfor) store = 'infor';
  else if (lower.includes('store') || lower.includes('location') || lower.includes('menu') ||
           lower.includes('bag') || lower.includes('order') || lower.includes('pickup') ||
           lower.includes('delivery') || lower.includes('checkout') || lower.includes('reward') ||
           lower.includes('discount') || lower.includes('gift card') || lower.includes('reorder')) {
    store = 'micros';
  }

  let fulfillment: 'pickup' | 'delivery' | 'none' = 'none';
  if (isDelivery) fulfillment = 'delivery';
  else if (lower.includes('pickup') || lower.includes('place') && lower.includes('order')) fulfillment = 'pickup';

  let timing: 'asap' | 'future' | 'none' = 'none';
  if (isFuture) timing = 'future';
  else if (lower.includes('asap')) timing = 'asap';

  return { key, summary, gherkinSteps, isGuest, store, fulfillment, timing };
}

// ── Live API Fetcher ──────────────────────────────────────────────

/**
 * Fetch real summaries and Gherkin steps from Jira/Xray for all keys in a batch.
 */
async function fetchTestCaseInfos(keys: string[]): Promise<TestCaseInfo[]> {
  const config = getConfig();
  const xrayConfig = getXrayConfig();

  if (!config) throw new Error('Jira config not found — check .env (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN)');
  if (!xrayConfig) throw new Error('Xray config not found — check .env (XRAY_CLIENT_ID, XRAY_CLIENT_SECRET)');

  // 1. Fetch Jira issues in bulk (summaries, labels, status)
  console.log(`  ⏳ Fetching ${keys.length} issues from Jira...`);
  const issues = await getIssuesByKeys(config, keys);
  const issueMap = new Map<string, XrayTestIssue>();
  for (const issue of issues) issueMap.set(issue.key, issue);

  // 2. Fetch Gherkin for each test from Xray
  console.log(`  ⏳ Fetching Gherkin definitions from Xray...`);
  const infos: TestCaseInfo[] = [];

  for (const key of keys) {
    const issue = issueMap.get(key);
    if (!issue) {
      console.warn(`  ⚠️  ${key}: Not found in Jira — using placeholder`);
      infos.push(inferTestCaseInfo(key, `[NOT FOUND] ${key}`, [`[Gherkin not available]`]));
      continue;
    }

    // Read Gherkin from Xray
    let gherkinSteps: string[] = [];
    try {
      const xrayTest = await readGherkinDefinition(xrayConfig, key);
      if (xrayTest?.gherkin) {
        // Parse the Gherkin to extract the Given/When/Then steps
        gherkinSteps = xrayTest.gherkin
          .split('\n')
          .map(l => l.trim())
          .filter(l => /^(Given|When|Then|And|But)\s/i.test(l));
      }
    } catch (err: any) {
      console.warn(`  ⚠️  ${key}: Xray error — ${err.message}`);
    }

    if (gherkinSteps.length === 0) {
      gherkinSteps = [`[No Gherkin steps found for ${key}]`];
    }

    // Strip the B3 | WEB | prefix for a clean summary
    const cleanSummary = issue.summary
      .replace(/^B3\s*\|\s*WEB\s*\|\s*/i, '')
      .replace(/^GENERIC[\s_|]*B3[\s_|]*(WEB[\s_|]*)?/i, '')
      .trim();

    infos.push(inferTestCaseInfo(key, cleanSummary, gherkinSteps));
  }

  return infos;
}

// ── CLI ────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);
  const batchArg = args.find((_: string, i: number, a: string[]) => a[i - 1] === '--batch');
  const batchFilter = batchArg ? parseInt(batchArg) : null;
  const saveMode = args.includes('--save');
  const keysArg = args.find((_: string, i: number, a: string[]) => a[i - 1] === '--keys');
  const dryRun = args.includes('--dry-run');
  const liveMode = args.includes('--live') || saveMode;

  console.log('╔══════════════════════════════════════════════════════╗');
  console.log('║  Comet Batch Prompt Generator                       ║');
  console.log('╚══════════════════════════════════════════════════════╝\n');

  // Handle ad-hoc key batching
  if (keysArg) {
    const keys = keysArg.split(',').map(k => k.trim());
    console.log(`🔑 Ad-hoc batch from ${keys.length} keys: ${keys.join(', ')}\n`);
    const adhocBatch: TestBatch = {
      id: 0, name: 'Ad-hoc', description: 'Custom key selection',
      authMode: 'mixed', store: 'both', placesOrders: true, keys,
    };
    const testInfos = await fetchTestCaseInfos(keys);
    const prompt = generateBatchPrompt(adhocBatch, testInfos);
    console.log(prompt);
    return;
  }

  // Show batch overview (always, unless generating a single batch in live mode)
  if (!batchFilter || !liveMode) {
    console.log('📋 Batch Overview:\n');
    let totalTests = 0;
    for (const batch of EXECUTION_BATCHES) {
      console.log(`  Batch ${String(batch.id).padStart(2)}: ${batch.name.padEnd(35)} | ${batch.keys.length} tests | ${batch.authMode.padEnd(9)} | Store: ${batch.store.padEnd(6)} | Orders: ${batch.placesOrders ? 'Yes' : 'No '}`);
      totalTests += batch.keys.length;
    }
    console.log(`\n  Total: ${totalTests} tests across ${EXECUTION_BATCHES.length} batches\n`);

    // Verify all 45 keys are covered
    const allBatchKeys = EXECUTION_BATCHES.flatMap(b => b.keys);
    const missing = WEB_TEST_KEYS.filter(k => !allBatchKeys.includes(k));
    if (missing.length > 0) {
      console.log(`  ⚠️  ${missing.length} keys NOT in any batch: ${missing.join(', ')}`);
    } else {
      console.log(`  ✅ All ${WEB_TEST_KEYS.length} WEB test keys are covered`);
    }

    if (!liveMode && !batchFilter) {
      console.log(`\n💡 Commands:`);
      console.log(`   npx ts-node src/generators/comet-batch-generator.ts --batch 1 --live     # Generate batch 1 with real API data`);
      console.log(`   npx ts-node src/generators/comet-batch-generator.ts --save               # Save ALL batches to files (auto-live)`);
      console.log(`   npx ts-node src/generators/comet-batch-generator.ts --batch 1 --dry-run  # Preview batch 1 with placeholders`);
      console.log(`   npx ts-node src/generators/comet-batch-generator.ts --keys TE-10075,TE-10059 --live  # Ad-hoc batch`);
      return;
    }
  }

  // Determine which batches to process
  const batches = batchFilter
    ? EXECUTION_BATCHES.filter(b => b.id === batchFilter)
    : EXECUTION_BATCHES;

  if (batches.length === 0) {
    console.error(`❌ Batch ${batchFilter} not found. Valid: 1-${EXECUTION_BATCHES.length}`);
    process.exit(1);
  }

  // Process each batch
  const reportDir = path.resolve(__dirname, '..', '..', 'reports', 'comet-batches');
  if (saveMode && !fs.existsSync(reportDir)) fs.mkdirSync(reportDir, { recursive: true });

  let totalGenerated = 0;
  let totalFailed = 0;

  for (const batch of batches) {
    console.log(`\n${'─'.repeat(60)}`);
    console.log(`📦 Batch ${batch.id}: ${batch.name} (${batch.keys.length} tests)`);
    console.log('─'.repeat(60));

    let testInfos: TestCaseInfo[];

    if (dryRun) {
      // Dry run — use placeholder data from the registry comments
      testInfos = batch.keys.map(key => {
        // Use the comment from web-test-cases.ts as a rough summary
        return inferTestCaseInfo(key, `[Dry-run placeholder for ${key}]`, [
          `[Gherkin steps loaded at runtime]`,
        ]);
      });
      console.log(`  🏃 Dry-run mode — using placeholders`);
    } else {
      // Live mode — fetch from Jira/Xray
      try {
        testInfos = await fetchTestCaseInfos(batch.keys);
      } catch (err: any) {
        console.error(`  ❌ Failed to fetch batch ${batch.id}: ${err.message}`);
        totalFailed += batch.keys.length;
        continue;
      }
    }

    const prompt = generateBatchPrompt(batch, testInfos);

    if (saveMode) {
      const fileName = `batch-${String(batch.id).padStart(2, '0')}-${batch.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.txt`;
      const filePath = path.join(reportDir, fileName);
      fs.writeFileSync(filePath, prompt, 'utf-8');
      console.log(`  💾 Saved: ${filePath}`);
      totalGenerated += batch.keys.length;
    } else {
      console.log(`\n${'═'.repeat(70)}`);
      console.log(prompt);
      console.log('═'.repeat(70));
      totalGenerated += batch.keys.length;
    }
  }

  // Final summary
  console.log(`\n${'═'.repeat(60)}`);
  if (saveMode) {
    console.log(`✅ ${batches.length} batch prompts saved to reports/comet-batches/`);
    console.log(`   ${totalGenerated} tests generated | ${totalFailed} failed`);
    console.log(`\n� Files ready — copy-paste each into a Comet session.`);
  } else {
    console.log(`✅ Generated ${batches.length} batch prompt(s) (${totalGenerated} tests)`);
  }
}

main().catch(console.error);
