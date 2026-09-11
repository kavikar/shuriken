/**
 * Gherkin Generator
 *
 * Generates title-aware Gherkin BDD scenarios for Xray Test issues.
 * Analyzes the test title to determine the functional area and generates
 * relevant Given/When/Then steps instead of generic order-flow steps.
 *
 * Ported from mobileAPPAutomation/src/jira/converter.ts (generateSkeleton)
 * and adapted for Xray Cucumber Scenario format.
 */

import type { XrayTestIssue } from '../client/xray-client';

// ── Test Data Constants ────────────────────────────────────────────

const TEST_EMAIL = 'user@example.com';
const TEST_PASSWORD = 'replace_me';
const STORE_ZIP = '00000';
const STORE_1 = '1000 1 Example St';
const STORE_2 = '1001 3805 Example Ave';

// ── Flow Category Detection ────────────────────────────────────────

type FlowCategory =
  | 'login'
  | 'signup'
  | 'password'
  | 'location'
  | 'menu-bag-modify'
  | 'combo-builder'
  | 'nutrition'
  | 'reorder'
  | 'offers-deals'
  | 'delivery'
  | 'profile-account'
  | 'loyalty-rewards'
  | 'payment-gift-card'
  | 'push-notification'
  | 'checkin'
  | 'timeslot'
  | 'home-banner'
  | 'negative-scenario'
  | 'order-history'
  | 'e2e-order-flow';

/**
 * Detect the primary flow category from the test title.
 * Uses the STRIPPED title (no brand/platform prefix) for more accurate matching.
 */
function detectCategory(summary: string): FlowCategory {
  // Strip prefix first so "B3 | iOS | Menu - ..." matches on "Menu - ..."
  const stripped = stripBrandPlatformPrefix(summary);
  const lower = stripped.toLowerCase();

  // In-Store Check-In  (BEFORE timeslot — "Check-In for ASAP" is checkin, not timeslot)
  if (lower.includes('check-in') || lower.includes('checkin') || lower.includes('check in') ||
      lower.includes('in-store') || lower.includes('i\'m here')) {
    return 'checkin';
  }

  // Login / Auth sign-in
  if (lower.includes('login') || lower.includes('sign in') || lower.includes('signin')) {
    return 'login';
  }

  // Signup / Registration
  if (lower.includes('signup') || lower.includes('sign up') || lower.includes('sign-up') ||
      lower.includes('register') || lower.includes('create account')) {
    return 'signup';
  }

  // Password flows (recover, reset, change, forgot)
  if (lower.includes('password') || lower.includes('recover password')) {
    return 'password';
  }

  // Push Notifications / SFMC
  if (lower.includes('push notification') || lower.includes('push-notification') ||
      lower.includes('sfmc') || (lower.includes('notification') && lower.includes('push')) ||
      (lower.includes('notification') && lower.includes('deeplink'))) {
    return 'push-notification';
  }

  // Combo builder
  if (lower.includes('combo') || lower.includes('build your')) {
    return 'combo-builder';
  }

  // Timeslots (specific keyword — not "asap" alone which is too broad)
  if (lower.includes('timeslot') || lower.includes('time slot') || lower.includes('time-slot') ||
      lower.includes('pickup/delivery slots') || lower.includes('pickup slots') ||
      (lower.includes('slots') && (lower.includes('holiday') || lower.includes('store')))) {
    return 'timeslot';
  }

  // Negative / Error scenarios
  if (lower.includes('negative') || lower.includes('invalid') || lower.includes('error') ||
      lower.includes('decline') || lower.includes('expired') || lower.includes('failure')) {
    return 'negative-scenario';
  }

  // Location / Store / Map
  if (lower.includes('location') || lower.includes('map view') || lower.includes('store location') ||
      lower.includes('map pin') || lower.includes('store finder')) {
    return 'location';
  }

  // Nutrition / Allergen
  if (lower.includes('nutri') || lower.includes('calorie') || lower.includes('allergen')) {
    return 'nutrition';
  }

  // Menu / Bag (broader matching — display, product, item, add-on, suggest, unavailable)
  if ((lower.includes('menu') || lower.includes('bag') || lower.includes('cart')) &&
      (lower.includes('modif') || lower.includes('edit') || lower.includes('update') ||
       lower.includes('remove') || lower.includes('quantity') || lower.includes('max') ||
       lower.includes('upcharge') || lower.includes('intensity') || lower.includes('customiz') ||
       lower.includes('display') || lower.includes('product') || lower.includes('item') ||
       lower.includes('add-on') || lower.includes('suggest') || lower.includes('unavailable') ||
       lower.includes('categor'))) {
    return 'menu-bag-modify';
  }

  // Reorder / Past orders  (but NOT "order history" which is different)
  if ((lower.includes('reorder') || lower.includes('re-order') || lower.includes('past order')) &&
      !lower.includes('order history')) {
    return 'reorder';
  }

  // Order History (view only, not reorder)
  if (lower.includes('order history') || lower.includes('order details') || lower.includes('order status')) {
    return 'order-history';
  }

  // Home Page / Banners / Store banners
  if ((lower.includes('home') && (lower.includes('banner') || lower.includes('carousel') || lower.includes('page'))) ||
      (lower.includes('store') && (lower.includes('banner') || lower.includes('closed banner') || lower.includes('temporarily closed')))) {
    return 'home-banner';
  }

  // Offers / Deals / Promo / Discount / Rewards
  if (lower.includes('offer') || lower.includes('deal') || lower.includes('promo') ||
      lower.includes('campaign') || lower.includes('discount') || lower.includes('coupon') ||
      lower.includes('reward')) {
    return 'offers-deals';
  }

  // Loyalty / Points
  if (lower.includes('loyalty') || lower.includes('points')) {
    return 'loyalty-rewards';
  }

  // Profile / Account / OTP
  if (lower.includes('profile') || lower.includes('account') || lower.includes('settings') ||
      lower.includes('otp')) {
    return 'profile-account';
  }

  // Payment / Gift Card / Saved Cards / Wallet / Tender
  if (lower.includes('payment') || lower.includes('gift card') || lower.includes('credit card') ||
      lower.includes('apple pay') || lower.includes('google pay') || lower.includes('visa') ||
      lower.includes('mastercard') || lower.includes('amex') || lower.includes('saved card') ||
      lower.includes('wallet') || lower.includes('tender') || lower.includes('change payment')) {
    return 'payment-gift-card';
  }

  // Delivery-specific (including Vromo, DoorDash, track your order)
  if (lower.includes('delivery') || lower.includes('vromo') || lower.includes('doordash') ||
      lower.includes('track your order')) {
    return 'delivery';
  }

  // Default: full E2E order flow
  return 'e2e-order-flow';
}

// ── Step Generators per Category ───────────────────────────────────

function generateLoginSteps(lower: string): string[] {
  const lines = ['Given the app is launched'];
  if (lower.includes('facebook')) {
    lines.push('When I tap on "Sign In" button',
      'And I select "Continue with Facebook" option',
      'And I enter Facebook credentials',
      'Then I should be logged in successfully',
      'And I should see the home screen');
  } else if (lower.includes('google')) {
    lines.push('When I tap on "Sign In" button',
      'And I select "Continue with Google" option',
      'And I complete Google authentication',
      'Then I should be logged in successfully',
      'And I should see the home screen');
  } else if (lower.includes('apple')) {
    lines.push('When I tap on "Sign In" button',
      'And I select "Continue with Apple" option',
      'And I complete Apple authentication',
      'Then I should be logged in successfully',
      'And I should see the home screen');
  } else {
    lines.push(
      `When I tap on "Sign In" button`,
      `And I enter email "${TEST_EMAIL}" and password "${TEST_PASSWORD}"`,
      'And I tap on "Log In" button',
      'Then I should be logged in successfully',
      'And I should see the home screen');
  }
  return lines;
}

function generateSignupSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'When I tap on "Sign Up" button',
    'And I enter a valid first name',
    'And I enter a valid last name',
    'And I enter a new email address',
    'And I enter a valid password',
    'And I accept the terms and conditions',
    'And I tap on "Create Account" button',
    'Then I should see signup success confirmation',
    'And I should be logged in as the new user',
  ];
  if (lower.includes('order')) {
    lines.push(...generateOrderSubSteps(lower));
  }
  return lines;
}

function generatePasswordSteps(_lower: string): string[] {
  return [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    'When I navigate to my profile settings',
    'And I tap on "Change Password"',
    'And I enter my current password',
    'And I enter a new password',
    'And I confirm the new password',
    'And I tap on "Save" button',
    'Then I should see password changed successfully',
  ];
}

function generateLocationSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'When I navigate to the location page',
    `And I search for a location using zip code "${STORE_ZIP}"`,
    'Then I should see a list of nearby stores',
  ];
  if (lower.includes('map')) {
    lines.push(
      'When I switch to map view',
      'Then I should see store pins on the map',
      'When I select a store from the list',
      'Then the selected store pin should be highlighted on the map',
      'When I select a different store',
      'Then the previously selected pin should become smaller',
      'And the newly selected pin should be highlighted with the brand logo');
  } else {
    lines.push(
      'When I select a store from the results',
      'Then I should see the store details',
      'And I should see the store hours and address');
  }
  return lines;
}

function generateMenuBagModifySteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    `And I have selected store "${STORE_1}"`,
    'And I navigate to the menu',
  ];
  if (lower.includes('quantity') || lower.includes('max')) {
    lines.push(
      'When I add a menu item to the bag',
      'And I open the bag',
      'And I increase the item quantity to the maximum allowed',
      'Then I should see the quantity updated in the bag',
      'And the quantity should not exceed the maximum limit');
  } else if (lower.includes('modif') || lower.includes('edit') || lower.includes('customiz')) {
    lines.push(
      'When I add a menu item to the bag',
      'And I open the bag',
      'And I tap on the item to edit it',
      'And I modify the item customization',
      'And I save the changes',
      'Then I should see the updated item in the bag');
  } else if (lower.includes('remove')) {
    lines.push(
      'When I add a menu item to the bag',
      'And I open the bag',
      'And I remove the item from the bag',
      'Then the bag should be empty');
  } else if (lower.includes('upcharge') || lower.includes('intensity')) {
    lines.push(
      'When I select a menu item with modifiers',
      'And I select a modifier with intensity that has a price upcharge',
      'Then I should see the upcharge price reflected',
      'When I add the item to the bag',
      'And I open the bag',
      'Then I should see the modifier upcharge in the item price');
  } else {
    lines.push(
      'When I add a menu item to the bag',
      'And I open the bag',
      'Then I should see the item in the bag with correct details');
  }
  return lines;
}

function generateComboBuilderSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    `And I have selected store "${STORE_1}"`,
    'When I navigate to the menu',
    'And I select a combo meal',
    'Then I should see the combo builder screen',
  ];
  if (lower.includes('customiz') || lower.includes('swap') || lower.includes('modif')) {
    lines.push(
      'When I customize the combo components',
      'And I swap a side item',
      'And I swap a drink',
      'Then I should see the updated combo with my selections');
  } else if (lower.includes('default')) {
    lines.push(
      'Then I should see default combo items pre-selected',
      'And the combo price should reflect the default configuration');
  } else {
    lines.push(
      'When I select combo components',
      'And I complete the combo configuration',
      'And I add the combo to the bag',
      'Then I should see the combo in the bag with correct items and price');
  }
  if (lower.includes('order') || lower.includes('checkout') || lower.includes('place')) {
    lines.push(...generateOrderSubSteps(lower));
  }
  return lines;
}

function generateNutritionSteps(_lower: string): string[] {
  return [
    'Given the app is launched',
    `And I have selected store "${STORE_1}"`,
    'When I navigate to the menu',
    'And I select a menu item',
    'Then I should see nutritional information for the item',
    'And I should see calorie count',
    'And I should see allergen details',
  ];
}

function generateReorderSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    'When I navigate to my past orders',
    'And I select a previous order to reorder',
    'Then the items from the past order should be added to the bag',
  ];
  if (lower.includes('pickup')) {
    lines.push('When I select "Pickup" order type');
  } else if (lower.includes('delivery')) {
    lines.push('When I select "Delivery" order type');
  }
  lines.push(
    'And I proceed to checkout',
    'And I fill payment details',
    'And I place the order',
    'Then I should see order confirmation');
  return lines;
}

function generateOffersSteps(lower: string): string[] {
  const lines = ['Given the app is launched'];
  if (lower.includes('auto') && lower.includes('discount')) {
    lines.push(
      'And I am logged in as an authenticated user',
      `And I have selected store "${STORE_1}"`,
      'When I add an item eligible for auto discount to the bag',
      'Then I should see the auto discount applied in the bag',
      'And the discounted price should be reflected in the total');
  } else if (lower.includes('promo') && lower.includes('code')) {
    lines.push(
      'And I have items in the bag',
      'When I proceed to checkout',
      'And I enter a valid promo code',
      'And I apply the promo code',
      'Then the promo discount should be applied to the order total');
  } else if (lower.includes('reward')) {
    lines.push(
      'And I am logged in as an authenticated user',
      'When I navigate to the rewards section',
      'Then I should see available rewards',
      'When I select a reward to redeem',
      'Then the reward should be applied to my order');
  } else {
    lines.push(
      'And I am logged in as an authenticated user',
      'When I navigate to the offers section',
      'Then I should see available offers',
      'When I select an offer',
      'And I add the offer to the bag',
      'Then the offer discount should be reflected in the bag');
  }
  if (lower.includes('order') || lower.includes('checkout') || lower.includes('place')) {
    lines.push(...generateOrderSubSteps(lower));
  }
  return lines;
}

function generateDeliverySteps(lower: string): string[] {
  const lines = ['Given the app is launched'];
  if (!lower.includes('guest')) {
    lines.push('And I am logged in as an authenticated user');
  }
  lines.push(
    'When I select "Delivery" order type',
    'And I enter a valid delivery address',
    'And I select the delivery store from results',
    'And I navigate to the menu',
    'And I add the first available item to the bag',
    'And I proceed to checkout');
  if (lower.includes('guest')) {
    lines.push('And I continue as guest', 'And I fill the guest contact info');
  }
  lines.push(
    'And I fill payment details',
    'And I place the order',
    'Then I should see order confirmation',
    'And the order type should show "Delivery"');
  return lines;
}

function generateProfileSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    'When I navigate to my profile',
    'Then I should see my account information',
  ];
  if (lower.includes('edit') || lower.includes('update')) {
    lines.push(
      'When I tap on "Edit Profile"',
      'And I update my profile information',
      'And I save the changes',
      'Then I should see the profile updated successfully');
  }
  if (lower.includes('delete') || lower.includes('deactivate')) {
    lines.push(
      'When I tap on "Delete Account"',
      'And I confirm account deletion',
      'Then my account should be deactivated');
  }
  return lines;
}

function generateLoyaltySteps(_lower: string): string[] {
  return [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    'When I navigate to the rewards section',
    'Then I should see my loyalty points balance',
    'And I should see available rewards',
  ];
}

function generatePaymentSteps(lower: string): string[] {
  const lines = ['Given the app is launched', 'And I am logged in as an authenticated user'];
  if (lower.includes('gift card')) {
    lines.push(
      'When I navigate to payment methods',
      'And I tap on "Add Gift Card"',
      'And I enter a valid gift card number',
      'And I enter the gift card PIN',
      'And I tap on "Add" button',
      'Then the gift card should be added to my payment methods',
      'And I should see the gift card balance');
  } else if (lower.includes('apple pay')) {
    lines.push(
      'When I add items to the bag and proceed to checkout',
      'And I select "Apple Pay" as payment method',
      'And I authenticate the Apple Pay payment',
      'And I place the order',
      'Then I should see order confirmation with Apple Pay');
  } else if (lower.includes('google pay')) {
    lines.push(
      'When I add items to the bag and proceed to checkout',
      'And I select "Google Pay" as payment method',
      'And I authenticate the Google Pay payment',
      'And I place the order',
      'Then I should see order confirmation with Google Pay');
  } else {
    lines.push(
      'When I navigate to payment methods',
      'And I add a new credit card',
      'And I enter valid card details',
      'And I save the payment method',
      'Then the new payment method should be saved successfully');
  }
  return lines;
}

function generatePushNotificationSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
  ];
  if (lower.includes('opt') && lower.includes('in')) {
    lines.push(
      'When I navigate to notification settings',
      'And I enable push notifications',
      'Then push notifications should be enabled',
      'And I should receive notification confirmation');
  } else if (lower.includes('opt') && lower.includes('out')) {
    lines.push(
      'When I navigate to notification settings',
      'And I disable push notifications',
      'Then push notifications should be disabled');
  } else {
    lines.push(
      'When a push notification is triggered',
      'Then I should see the push notification',
      'When I tap on the notification',
      'Then I should be navigated to the relevant screen');
  }
  return lines;
}

function generateCheckinSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    'And I have an active pickup order',
  ];
  if (lower.includes('geo') || lower.includes('gps')) {
    lines.push(
      'When I arrive near the store location',
      'Then the app should detect my arrival via geofence',
      'And I should see the "I\'m Here" check-in prompt',
      'When I confirm check-in',
      'Then the store should be notified of my arrival');
  } else {
    lines.push(
      'When I tap on "I\'m Here" button',
      'Then the store should be notified',
      'And I should see check-in confirmation',
      'And the order status should update');
  }
  return lines;
}

function generateTimeslotSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    `And I have selected store "${STORE_1}"`,
  ];
  if (lower.includes('asap')) {
    lines.push(
      'When I add items to the bag',
      'And I proceed to checkout',
      'And I select "ASAP" timeslot',
      'Then the order should be set to ASAP pickup',
      'And I should see the estimated ready time');
  } else if (lower.includes('future') || lower.includes('schedule') || lower.includes('advance')) {
    lines.push(
      'When I add items to the bag',
      'And I proceed to checkout',
      'And I tap on "Schedule for Later"',
      'And I select a future date and time',
      'Then the scheduled timeslot should be displayed',
      'And the order should be confirmed for the scheduled time');
  } else {
    lines.push(
      'When I add items to the bag',
      'And I proceed to checkout',
      'Then I should see available timeslots',
      'When I select a timeslot',
      'Then the selected timeslot should be applied to my order');
  }
  return lines;
}

function generateHomeBannerSteps(lower: string): string[] {
  const lines = [
    'Given the app is launched',
    'And I am on the home screen',
  ];
  if (lower.includes('banner')) {
    lines.push(
      'Then I should see promotional banners',
      'When I tap on a banner',
      'Then I should be navigated to the banner destination');
  } else if (lower.includes('carousel')) {
    lines.push(
      'Then I should see the carousel on the home page',
      'When I swipe through the carousel',
      'Then I should see different promotional items');
  } else {
    lines.push(
      'Then I should see the home page content',
      'And I should see navigation elements',
      'And I should see featured items or promotions');
  }
  return lines;
}

function generateNegativeSteps(lower: string): string[] {
  const lines = ['Given the app is launched'];
  if (lower.includes('login') || lower.includes('sign in')) {
    lines.push(
      'When I tap on "Sign In" button',
      'And I enter invalid credentials',
      'And I tap on "Log In" button',
      'Then I should see an error message',
      'And I should not be logged in');
  } else if (lower.includes('payment') || lower.includes('card') || lower.includes('decline')) {
    lines.push(
      'And I am logged in as an authenticated user',
      'And I have items in the bag',
      'When I proceed to checkout',
      'And I enter an invalid payment method',
      'And I attempt to place the order',
      'Then I should see a payment error message',
      'And the order should not be placed');
  } else {
    lines.push(
      'When I perform the action with invalid input',
      'Then I should see an appropriate error message',
      'And the system should handle the error gracefully');
  }
  return lines;
}

function generateOrderHistorySteps(_lower: string): string[] {
  return [
    'Given the app is launched',
    'And I am logged in as an authenticated user',
    'When I navigate to order history',
    'Then I should see my past orders',
    'When I select an order',
    'Then I should see the order details',
    'And I should see the order items and total',
    'And I should see the order date and status',
  ];
}

function generateE2EOrderFlowSteps(lower: string): string[] {
  const lines = ['Given the app is launched'];

  if (!lower.includes('guest')) {
    lines.push('And I am logged in as an authenticated user');
  }

  if (lower.includes('pickup')) {
    lines.push('When I select "Pickup" order type');
  } else if (lower.includes('delivery')) {
    lines.push('When I select "Delivery" order type');
  }

  lines.push(
    `And I search for store "${STORE_1}"`,
    'And I select the first store from results',
    'And I navigate to the menu',
    'And I add the first available item to the bag',
    'And I proceed to checkout');

  if (lower.includes('guest')) {
    lines.push('And I continue as guest', 'And I fill the guest contact info');
  }

  lines.push(
    'And I fill payment details',
    'And I place the order',
    'Then I should see order confirmation');

  return lines;
}

/**
 * Helper: generates order-completion substeps for composite flows.
 */
function generateOrderSubSteps(lower: string): string[] {
  const lines: string[] = [];
  if (lower.includes('pickup')) {
    lines.push('When I select "Pickup" order type');
  } else if (lower.includes('delivery')) {
    lines.push('When I select "Delivery" order type');
  }
  lines.push(
    `And I search for store "${STORE_1}"`,
    'And I select the first store from results',
    'And I navigate to the menu',
    'And I add the first available item to the bag',
    'And I proceed to checkout');
  if (lower.includes('guest')) {
    lines.push('And I continue as guest', 'And I fill the guest contact info');
  }
  lines.push(
    'And I fill payment details',
    'And I place the order',
    'Then I should see order confirmation');
  return lines;
}

// ── Public API ─────────────────────────────────────────────────────

/**
 * Generate Gherkin scenario text for an Xray test issue.
 * Returns the Cucumber Scenario field value (no Feature wrapper).
 */
export function generateGherkin(issue: XrayTestIssue): string {
  const summary = issue.summary;
  const lower = summary.toLowerCase();
  const category = detectCategory(summary);

  let steps: string[];
  switch (category) {
    case 'login':              steps = generateLoginSteps(lower); break;
    case 'signup':             steps = generateSignupSteps(lower); break;
    case 'password':           steps = generatePasswordSteps(lower); break;
    case 'location':           steps = generateLocationSteps(lower); break;
    case 'menu-bag-modify':    steps = generateMenuBagModifySteps(lower); break;
    case 'combo-builder':      steps = generateComboBuilderSteps(lower); break;
    case 'nutrition':          steps = generateNutritionSteps(lower); break;
    case 'reorder':            steps = generateReorderSteps(lower); break;
    case 'offers-deals':       steps = generateOffersSteps(lower); break;
    case 'delivery':           steps = generateDeliverySteps(lower); break;
    case 'profile-account':    steps = generateProfileSteps(lower); break;
    case 'loyalty-rewards':    steps = generateLoyaltySteps(lower); break;
    case 'payment-gift-card':  steps = generatePaymentSteps(lower); break;
    case 'push-notification':  steps = generatePushNotificationSteps(lower); break;
    case 'checkin':            steps = generateCheckinSteps(lower); break;
    case 'timeslot':           steps = generateTimeslotSteps(lower); break;
    case 'home-banner':        steps = generateHomeBannerSteps(lower); break;
    case 'negative-scenario':  steps = generateNegativeSteps(lower); break;
    case 'order-history':      steps = generateOrderHistorySteps(lower); break;
    case 'e2e-order-flow':     steps = generateE2EOrderFlowSteps(lower); break;
    default:                   steps = generateE2EOrderFlowSteps(lower); break;
  }

  // Format as Xray Cucumber Scenario
  const scenarioTitle = stripBrandPlatformPrefix(summary);
  const gherkin = [
    `Scenario: ${scenarioTitle}`,
    ...steps.map((s) => `  ${s}`),
  ].join('\n');

  return gherkin;
}

/**
 * Get the detected category for a test case (for reporting).
 */
export function getCategory(summary: string): FlowCategory {
  return detectCategory(summary);
}

/**
 * Strip brand/platform prefix from summary for cleaner scenario names.
 *
 * Handles many real-world formats:
 *   "B3 | iOS APP | Bag - ..."          → "Bag - ..."
 *   "B3 | iOS | Auth - ..."             → "Auth - ..."
 *   "B3 | AOS | Order - ..."            → "Order - ..."
 *   "GENERIC | B3 | Pickup/Delivery ..."   → "Pickup/Delivery ..."
 *   "GENERIC_B3_Verify that ..."           → "Verify that ..."
 *   "GENERIC - [Automated] 'Choose ...'     → "Choose ..."
 *   "GENERIC Vromo Delivery - Email ..."    → "Delivery - Email ..."
 *   "GENERIC _ VROMO -SMS Alert ..."        → "SMS Alert ..."
 */
function stripBrandPlatformPrefix(summary: string): string {
  let s = summary.trim();

  // Pattern 1: "BRAND | PLATFORM | title"  (covers B3|B2|B1|B4 + iOS APP|iOS|AOS APP|AOS|Web)
  const pipe3 = s.match(/^(?:B3|B2|B1|B4|GENERIC)\s*\|\s*(?:B3\s*\|\s*)?(?:iOS\s*APP|AOS\s*APP|iOS|AOS|Web)\s*\|\s*(.+)/i);
  if (pipe3) return pipe3[1].trim();

  // Pattern 2: "GENERIC | B3 | title"  (no platform segment)
  const pipe2 = s.match(/^GENERIC\s*\|\s*(?:B3|B2|B1|B4)\s*\|\s*(.+)/i);
  if (pipe2) return pipe2[1].trim();

  // Pattern 3: "GENERIC_B3_title"
  const underscore = s.match(/^GENERIC[_\s]+(?:B3|B2|B1|B4)[_\s]+(.+)/i);
  if (underscore) return underscore[1].trim();

  // Pattern 4: "GENERIC - [Automated] title"  or "GENERIC - [Automated]'title'"
  const automated = s.match(/^GENERIC\s*-\s*\[Automated\]\s*'?(.+)/i);
  if (automated) return automated[1].replace(/'$/, '').trim();

  // Pattern 5: "GENERIC Vromo ..." or "GENERIC _ VROMO ..."
  const vromo = s.match(/^GENERIC\s*[_\s]*(?:VROMO|Vromo)\s*[-–]?\s*(.+)/i);
  if (vromo) return vromo[1].trim();

  // Pattern 6: Simple "GENERIC - title"
  const genericSimple = s.match(/^GENERIC\s*-\s*(.+)/i);
  if (genericSimple) return genericSimple[1].trim();

  return s;
}
