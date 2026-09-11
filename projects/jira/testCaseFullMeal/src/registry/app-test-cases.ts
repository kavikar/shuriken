/**
 * IQE Test Case Registry
 *
 * All 157 Xray Test case IDs organized by functional area.
 * These are the test cases that need Gherkin BDD steps pushed via Xray API.
 */

export interface FunctionalArea {
  name: string;
  keys: string[];
}

export const FUNCTIONAL_AREAS: FunctionalArea[] = [
  {
    name: 'Product Modifiers & Bag',
    keys: [
      'TE-10006', 'TE-10005', 'TE-10004', 'TE-10014',
      'TE-10007', 'TE-10015', 'TE-10021', 'TE-10013',
    ],
  },
  {
    name: 'Combo Builder',
    keys: [
      'TE-10029', 'TE-10030', 'TE-10031', 'TE-10032',
      'TE-10033', 'TE-10034', 'TE-10026', 'TE-10027',
      'TE-10028',
    ],
  },
  {
    name: 'Orders & History',
    keys: [
      'TE-10022', 'TE-10003', 'TE-10002', 'TE-10020',
    ],
  },
  {
    name: 'Delivery & Fulfillment',
    keys: [
      'TE-10024', 'TE-10025', 'TE-10012', 'TE-10008',
    ],
  },
  {
    name: 'Home Page & Banners',
    keys: [
      'TE-10019', 'TE-10023', 'TE-10010',
    ],
  },
];

/**
 * Get all test case keys as a flat array.
 */
export function getAllKeys(): string[] {
  return FUNCTIONAL_AREAS.flatMap((area) => area.keys);
}

/**
 * Get total count of all test case keys.
 */
export function getTotalCount(): number {
  return getAllKeys().length;
}

/**
 * Get the functional area name for a given issue key.
 */
export function getAreaForKey(key: string): string | null {
  for (const area of FUNCTIONAL_AREAS) {
    if (area.keys.includes(key)) {
      return area.name;
    }
  }
  return null;
}
