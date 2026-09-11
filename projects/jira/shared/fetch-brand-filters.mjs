import fs from 'fs';
import https from 'https';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envPath = path.join(__dirname, '../.env');
const raw = fs.readFileSync(envPath, 'utf8').replace(/^\uFEFF/, '');

const env = {};
for (const line of raw.split('\n')) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('#')) continue;
  const eq = trimmed.indexOf('=');
  if (eq < 0) continue;
  env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
}

const email = env.JIRA_EMAIL || env.JIRA_USERNAME;
const token = env.JIRA_API_TOKEN || env.JIRA_TOKEN;
const base64 = Buffer.from(`${email}:${token}`).toString('base64');

function jiraGet(path) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'your-tenant.atlassian.net',
      path,
      method: 'GET',
      headers: {
        'Authorization': `Basic ${base64}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      rejectUnauthorized: false
    };
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error(`Parse error: ${data.slice(0, 200)}`)); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function fetchFilter(filterId, brandName) {
  console.log(`\n========== ${brandName} (filter=${filterId}) ==========`);
  
  // Get filter info to extract the JQL
  const filterInfo = await jiraGet(`/rest/api/3/filter/${filterId}`);
  console.log(`Filter Name: ${filterInfo.name || 'N/A'}`);
  
  const jql = filterInfo.jql || '';
  
  // Count keys directly from the JQL (pattern: key in (KEY-1, KEY-2, ...))
  const keyMatch = jql.match(/key\s+in\s*\(([^)]+)\)/i);
  let keys = [];
  if (keyMatch) {
    keys = keyMatch[1].split(',').map(k => k.trim()).filter(Boolean);
  }
  console.log(`Keys in filter: ${keys.length}`);
  
  // Fetch issues using cursor-based pagination (new API)
  let allIssues = [];
  let nextPageToken = undefined;
  const maxResults = 100;
  
  while (true) {
    const encoded = encodeURIComponent(jql);
    const paging = nextPageToken ? `&nextPageToken=${encodeURIComponent(nextPageToken)}` : '';
    const result = await jiraGet(
      `/rest/api/3/search/jql?jql=${encoded}&fields=summary,status,issuetype,labels,components,priority&maxResults=${maxResults}${paging}`
    );
    
    if (result.errorMessages) {
      console.error('Error:', result.errorMessages);
      break;
    }
    
    const issues = result.issues || [];
    allIssues = allIssues.concat(issues);
    
    nextPageToken = result.nextPageToken;
    if (!nextPageToken || issues.length === 0) break;
  }
  
  console.log(`Issues fetched via API: ${allIssues.length}`);
  
  // Group by status
  const byStatus = {};
  const byIssueType = {};
  const byComponent = {};
  
  for (const issue of allIssues) {
    const status = issue.fields.status?.name || 'Unknown';
    const issueType = issue.fields.issuetype?.name || 'Unknown';
    const components = issue.fields.components?.map(c => c.name) || ['(none)'];
    
    byStatus[status] = (byStatus[status] || 0) + 1;
    byIssueType[issueType] = (byIssueType[issueType] || 0) + 1;
    for (const comp of components) {
      byComponent[comp] = (byComponent[comp] || 0) + 1;
    }
  }
  
  console.log('\nBy Status:');
  for (const [s, count] of Object.entries(byStatus).sort((a,b) => b[1]-a[1])) {
    console.log(`  ${s}: ${count}`);
  }
  
  console.log('\nBy Issue Type:');
  for (const [t, count] of Object.entries(byIssueType).sort((a,b) => b[1]-a[1])) {
    console.log(`  ${t}: ${count}`);
  }
  
  console.log('\nBy Component:');
  for (const [c, count] of Object.entries(byComponent).sort((a,b) => b[1]-a[1])) {
    console.log(`  ${c}: ${count}`);
  }
  
  // Print all test cases (first 50 for readability)
  console.log(`\nTest Cases (showing up to 50 of ${allIssues.length}):`);
  for (const issue of allIssues.slice(0, 50)) {
    const status = issue.fields.status?.name || '?';
    const summary = issue.fields.summary || '?';
    const components = issue.fields.components?.map(c => c.name).join(', ') || '-';
    console.log(`  [${issue.key}] [${status}] [${components}] ${summary}`);
  }
  
  return { brand: brandName, total: keys.length || allIssues.length, byStatus, byIssueType, byComponent, issues: allIssues };
}

async function main() {
  const brands = [
    { id: 43841, name: "Brand One" },
    { id: 43842, name: "B2" },
    { id: 43865, name: "Brand Three" }
  ];
  
  const results = [];
  for (const brand of brands) {
    try {
      const result = await fetchFilter(brand.id, brand.name);
      results.push(result);
    } catch (err) {
      console.error(`Error fetching ${brand.name}:`, err.message);
    }
  }
  
  console.log('\n\n========== GRAND SUMMARY ==========');
  let grandTotal = 0;
  for (const r of results) {
    console.log(`${r.brand}: ${r.total} total`);
    grandTotal += r.total;
  }
  console.log(`TOTAL ACROSS ALL BRANDS: ${grandTotal}`);
  console.log('\nAt 15 tests/day:');
  const onDays = Math.ceil(grandTotal / 15);
  const offDays = Math.ceil(grandTotal / 15);
  console.log(`  Flag ON pass: ~${onDays} working days`);
  console.log(`  Flag OFF pass: ~${offDays} working days`);
  console.log(`  Total working days needed: ~${onDays + offDays}`);
}

main();
