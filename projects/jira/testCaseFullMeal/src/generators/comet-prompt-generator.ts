/**
 * Comet Prompt Generator (Phase 1 — WEB)
 *
 * Generates Comet-ready AI prompts from Xray Gherkin steps.
 * The prompt is a structured natural-language test script that
 * Comet can consume to generate the automated web test.
 *
 * NO framework-specific code (no Playwright, no imports, no skeleton).
 * Just a clean, structured prompt with:
 *   - Test objective & preconditions
 *   - Step-by-step actions derived from Gherkin
 *   - Expected results per step
 *   - Test data
 *   - Validation checkpoints
 *
 * Phase 2 (future): Maestro-ready prompts for APP test cases.
 */

import type { XrayTestIssue } from '../client/xray-client';

// ── Types ──────────────────────────────────────────────────────────

export interface CometPrompt {
  issueKey: string;
  summary: string;
  strippedTitle: string;
  category: string;
  prompt: string;
}

// ── Helpers ────────────────────────────────────────────────────────

function stripPrefix(summary: string): string {
  return summary
    .replace(/^B3\s*\|\s*WEB\s*\|\s*/i, '')
    .replace(/^GENERIC[\s_|]*B3[\s_|]*(WEB[\s_|]*)?/i, '')
    .trim();
}

function detectWebCategory(title: string): string {
  const t = title.toLowerCase();
  if (/\bsign[\s-]?up\b|\bsignup\b|\bcustomer.*signup\b/.test(t)) return 'Authentication — Signup';
  if (/\bfacebook\b/.test(t)) return 'Authentication — Social Login';
  if (/\blogin\b|\blogout\b|\bsign[\s-]?in\b|\bsign[\s-]?out\b/.test(t)) return 'Authentication';
  if (/\bmfa\b|\baccount deletion\b/.test(t)) return 'Profile — Security';
  if (/\bpassword\b/.test(t)) return 'Profile — Password';
  if (/\bprofile\b|\bphone number\b|\bfirst name\b|\blast name\b/.test(t)) return 'Profile';
  if (/\bgift[\s-]?card\b/.test(t)) return 'Payment — Gift Card';
  if (/\bcredit[\s-]?card\b.*(?:add|edit|new)\b|\b(?:add|edit|new).*credit[\s-]?card\b/.test(t)) return 'Payment — Card Management';
  if (/\bpayment\b|\bcredit[\s-]?card\b|\bapple[\s-]?pay\b|\bgoogle[\s-]?pay\b|\btender\b/.test(t)) return 'Payment';
  if (/\breward\b|\bloyalty\b|\bcoke\b/.test(t)) return 'Rewards';
  if (/\bdiscount\b|\bpromo\b|\boffer\b|\bstacking\b/.test(t)) return 'Discounts';
  if (/\bnutrition\b|\bcalori\b/.test(t)) return 'Menu — Nutrition';
  if (/\bmodifier\b|\bintensity\b/.test(t)) return 'Menu — Modifiers';
  if (/\bunavailable\b/.test(t)) return 'Menu — Availability';
  if (/\bbag\b|\bquantity\b/.test(t)) return 'Bag';
  if (/\blocation\b|\bmap\b|\bpin\b|\bstore\b/.test(t)) return 'Location';
  if (/\breorder\b|\border history\b/.test(t)) return 'Order History';
  if (/\border confirm\b|\bconfirmation\b|\bemail\b/.test(t)) return 'Order Confirmation';
  if (/\bfavorite\b/.test(t)) return 'Favorites';
  if (/\bdelivery\b/.test(t)) return 'Delivery';
  if (/\bpickup\b/.test(t)) return 'Pickup';
  return 'E2E Web';
}

function parseGherkinSteps(gherkin: string): Array<{ keyword: string; action: string }> {
  return gherkin
    .split('\n')
    .map(l => l.trim())
    .filter(l => /^(Given|When|Then|And|But)\s/i.test(l))
    .map(l => {
      const match = l.match(/^(Given|When|Then|And|But)\s+(.*)/i)!;
      return { keyword: match[1], action: match[2].trim() };
    });
}

function extractTestData(gherkin: string): Map<string, string> {
  const data = new Map<string, string>();
  const re = /"([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(gherkin)) !== null) {
    const val = m[1];
    if (/@/.test(val)) data.set('Email', val);
    else if (/^\d{5}$/.test(val)) data.set('ZIP Code', val);
    else if (/^\d{4}\s+/.test(val)) data.set('Store', val);
    else if (/test|password/i.test(val)) data.set('Password', val);
  }
  return data;
}

function extractTags(gherkin: string): string[] {
  const tagLine = gherkin.split('\n').find(l => l.trim().startsWith('@'));
  if (!tagLine) return [];
  return tagLine.trim().split(/\s+/).filter(t => t.startsWith('@'));
}

// ── Main Generator ─────────────────────────────────────────────────

export function generateCometPrompt(
  issue: XrayTestIssue,
  gherkin: string,
): CometPrompt {
  const strippedTitle = stripPrefix(issue.summary);
  const category = detectWebCategory(strippedTitle);
  const steps = parseGherkinSteps(gherkin);
  const testData = extractTestData(gherkin);
  const tags = extractTags(gherkin);

  const preconditions = steps.filter(s => s.keyword.toLowerCase() === 'given').map(s => s.action);
  const actions = steps.filter(s => /when|and/i.test(s.keyword)).map(s => s.action);
  const validations = steps.filter(s => s.keyword.toLowerCase() === 'then').map(s => s.action);

  const stepLines = steps.map((s, i) => `${i + 1}. [${s.keyword}] ${s.action}`);

  // Detect fulfillment and store from title + Gherkin
  const combined = (strippedTitle + ' ' + gherkin).toLowerCase();
  const isDelivery = /delivery/i.test(combined);
  const isPickup = /pickup/i.test(combined);
  const isFuture = /future/i.test(combined);
  const isASAP = /asap/i.test(combined);
  const fulfillment = isDelivery ? 'Delivery' : 'Pickup';
  const timing = isFuture ? 'Future' : 'ASAP';
  const isGuest = /guest/i.test(combined);
  const isSignedIn = /sign[\s-]?in|authenticated|signed[\s-]?in|reward|reorder|favorite|profile|password|mfa|history/i.test(combined);
  const needsAuth = isSignedIn && !isGuest;

  // Detect store: 1001 Infor for Infor tests, 1000 Micros for everything else
  const isInfor = /infor/i.test(combined);
  const storeId = isInfor ? '1001' : '1000';
  const storeName = isInfor ? '1001 Infor Lab' : '1000 Micros Lab';
  const storeAddress = isInfor ? '3805 Example Ave' : '1 Example St';
  const storeZip = isInfor ? '00000' : '00000';

  // Detect product hints from title
  const productHints: string[] = [];
  if (/combo/i.test(combined)) productHints.push('Combos category');
  if (/drink|frozen|coke/i.test(combined)) productHints.push('Drinks/Frozen Zone category');
  if (/burger|food|breakfast/i.test(combined)) productHints.push('Food category (Burgers, Breakfast, etc.)');
  if (/modifier|intensity/i.test(combined)) productHints.push('Item with modifiers/intensity options');
  if (productHints.length === 0) productHints.push('Select any available product from the menu');

  const prompt = `Comet Test Prompt - ${issue.key}

Test: ${strippedTitle}
Platform: Brand Three Desktop Web
Category: ${category}
Tags: ${tags.length > 0 ? tags.join(' ') : 'N/A'}
Jira: https://your-tenant.atlassian.net/browse/${issue.key}

OBJECTIVE
Automate the following web E2E test for brand3.example (UAT environment).

PRECONDITIONS
${preconditions.length > 0 ? preconditions.map(p => `- ${p}`).join('\n') : '- User is on the Brand Three Desktop Web home page'}

TEST STEPS
${stepLines.join('\n')}

ACTIONS
${actions.length > 0 ? actions.map(a => `- ${a}`).join('\n') : '- See test steps above'}

EXPECTED RESULTS
${validations.length > 0 ? validations.map(v => `- ${v}`).join('\n') : '- See test steps above'}

TEST DATA
- Credentials: user@example.com / replace_me${needsAuth ? ' (sign in required)' : isGuest ? ' (guest flow - no sign in)' : ''}
- Store: ${storeZip} - ${storeName} - Address: ${storeAddress}
- Fulfillment: ${timing} ${fulfillment}
- Product Selection: ${productHints.join('; ')}
- Environment: UAT
- Brand: Brand Three (B3)

STORES REFERENCE
- 00000 - 1000 Micros Lab - Address: 1 Example St
- 00000 - 1001 Infor Lab - Address: 3805 Example Ave

GHERKIN
${gherkin}

Generate a web automation test script for the above scenario.
Each test step should be executable, with proper waits and assertions.
Take screenshots at key validation points.
Handle cookie banners, overlays, and popups defensively.`;

  return { issueKey: issue.key, summary: issue.summary, strippedTitle, category, prompt };
}

/**
 * Convert the Comet prompt to Atlassian Document Format (ADF).
 */
export function promptToADF(prompt: string): object {
  const lines = prompt.split('\n');
  const content: any[] = [];
  let inGherkin = false;
  let gherkinBuffer: string[] = [];

  for (const line of lines) {
    // Start of Gherkin section
    if (line === 'GHERKIN') {
      content.push({
        type: 'heading', attrs: { level: 3 },
        content: [{ type: 'text', text: 'Gherkin' }],
      });
      inGherkin = true;
      gherkinBuffer = [];
      continue;
    }

    // End of Gherkin block when we hit the "Generate" instruction
    if (inGherkin && line.startsWith('Generate a web automation')) {
      if (gherkinBuffer.length > 0) {
        content.push({
          type: 'codeBlock',
          attrs: { language: 'gherkin' },
          content: [{ type: 'text', text: gherkinBuffer.join('\n').trim() }],
        });
      }
      inGherkin = false;
      content.push({
        type: 'panel', attrs: { panelType: 'info' },
        content: [{ type: 'paragraph', content: [{ type: 'text', text: line }] }],
      });
      continue;
    }

    if (inGherkin) {
      gherkinBuffer.push(line);
      continue;
    }

    // Title line
    if (line.startsWith('Comet Test Prompt')) {
      content.push({
        type: 'heading', attrs: { level: 1 },
        content: [{ type: 'text', text: line }],
      });
    }
    // Section headers
    else if (/^(OBJECTIVE|PRECONDITIONS|TEST STEPS|ACTIONS|EXPECTED RESULTS|TEST DATA|STORES REFERENCE)\b/.test(line)) {
      content.push({
        type: 'heading', attrs: { level: 3 },
        content: [{ type: 'text', text: line }],
      });
    }
    // Metadata fields (bold label)
    else if (/^(Test|Platform|Category|Tags|Jira):/.test(line)) {
      const idx = line.indexOf(':');
      const label = line.substring(0, idx);
      const value = line.substring(idx + 1).trim();
      const valueContent: any[] = [{ type: 'text', text: value }];
      // Make Jira link clickable
      if (label === 'Jira') {
        valueContent[0] = {
          type: 'text', text: value,
          marks: [{ type: 'link', attrs: { href: value } }],
        };
      }
      content.push({
        type: 'paragraph',
        content: [
          { type: 'text', text: `${label}: `, marks: [{ type: 'strong' }] },
          ...valueContent,
        ],
      });
    }
    // Numbered steps
    else if (/^\d+\.\s/.test(line)) {
      const text = line.replace(/^\d+\.\s*/, '');
      const num = line.match(/^\d+/)![0];
      const kwMatch = text.match(/^\[(\w+)\]\s*(.*)/);
      if (kwMatch) {
        content.push({
          type: 'paragraph',
          content: [
            { type: 'text', text: `${num}. ` },
            { type: 'text', text: `[${kwMatch[1]}] `, marks: [{ type: 'strong' }] },
            { type: 'text', text: kwMatch[2] },
          ],
        });
      } else {
        content.push({ type: 'paragraph', content: [{ type: 'text', text: line }] });
      }
    }
    // Bullet items
    else if (line.startsWith('- ')) {
      content.push({
        type: 'bulletList',
        content: [{
          type: 'listItem',
          content: [{ type: 'paragraph', content: [{ type: 'text', text: line.replace(/^- /, '') }] }],
        }],
      });
    }
    // Remaining instruction lines
    else if (line.startsWith('Each test step') || line.startsWith('Take screenshots') || line.startsWith('Handle cookie')) {
      content.push({
        type: 'bulletList',
        content: [{
          type: 'listItem',
          content: [{ type: 'paragraph', content: [{ type: 'text', text: line }] }],
        }],
      });
    }
    // Skip empty lines
    else if (line.trim() !== '') {
      content.push({ type: 'paragraph', content: [{ type: 'text', text: line }] });
    }
  }

  // Flush remaining Gherkin
  if (inGherkin && gherkinBuffer.length > 0) {
    content.push({
      type: 'codeBlock',
      attrs: { language: 'gherkin' },
      content: [{ type: 'text', text: gherkinBuffer.join('\n').trim() }],
    });
  }

  return { version: 1, type: 'doc', content };
}
