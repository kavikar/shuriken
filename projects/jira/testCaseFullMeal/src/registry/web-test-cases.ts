/**
 * WEB Test Case Registry
 *
 * All 45 IQE WEB test case keys from Test Set TE-10048.
 * These are the Brand Three Desktop Web tests that need Comet (Playwright) prompts.
 */

export const WEB_TEST_KEYS: string[] = [
  'TE-10009', // Location - Temporarily Unavailable Status in Locations Dropdown Header Verified
  'TE-10011', // Menu - Temporarily Unavailable Message on PLP and PDP Pages for Single Product
  'TE-10016', // Rewards - Coke Your Way Green Apple: Size Price Correct in Bag, Checkout, and Email
  'TE-10017', // Payment - Order Confirmation Displays Correct Tender Logo and Branding
  'TE-10018', // Profile - Phone Number Update OTP Received and Verified
];

export function getWebTestCount(): number {
  return WEB_TEST_KEYS.length;
}
