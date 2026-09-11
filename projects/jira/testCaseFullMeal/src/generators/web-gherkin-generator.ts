/**
 * WEB Gherkin Generator
 *
 * Generates title-aware, test-specific Gherkin BDD scenarios for
 * Brand Three Desktop Web (B3 | WEB) Xray test issues.
 *
 * Unlike the APP generator (gherkin-generator.ts) which uses mobile-centric
 * language ("app is launched", "I have selected a store"), this generator:
 *   - Uses web-specific phrasing ("user is on Brand Three Desktop Web")
 *   - References correct store data (1000 1 Example St / 1001 3805 Example Ave)
 *   - Generates steps specific to what each test actually validates
 *   - Includes concrete assertions instead of vague "should display correctly"
 */

import type { XrayTestIssue } from '../client/xray-client';

// ── Test Data Constants ────────────────────────────────────────────

const EMAIL = 'user@example.com';
const PASSWORD = 'replace_me';
const STORE_MICROS = '1000 1 Example St';
const STORE_INFOR  = '1001 3805 Example Ave';
const ZIP_MICROS   = '00000';
const ZIP_INFOR    = '00000';
const CC_NUMBER    = '5555555555554444';
const CC_EXPIRY    = '12/33';
const CC_CVV       = '444';

// ── Helpers ────────────────────────────────────────────────────────

function isInfor(lower: string): boolean {
  return lower.includes('infor');
}

function isMicros(lower: string): boolean {
  return lower.includes('micros') || !isInfor(lower);
}

function store(lower: string): string {
  return isInfor(lower) ? STORE_INFOR : STORE_MICROS;
}

function zip(lower: string): string {
  return isInfor(lower) ? ZIP_INFOR : ZIP_MICROS;
}

function isGuest(lower: string): boolean {
  return lower.includes('guest');
}

function isDelivery(lower: string): boolean {
  return lower.includes('delivery');
}

function isPickup(lower: string): boolean {
  return lower.includes('pickup') || !isDelivery(lower);
}

function isFuture(lower: string): boolean {
  return lower.includes('future');
}

function isASAP(lower: string): boolean {
  return lower.includes('asap') || !isFuture(lower);
}

function loginStep(lower: string): string {
  if (isGuest(lower)) return 'Given the user opens the Brand Three Desktop Web site as a guest';
  return `Given the user is logged in on Brand Three Desktop Web with email "${EMAIL}" and password "${PASSWORD}"`;
}

function storeStep(lower: string): string {
  return `And the user has selected store "${store(lower)}" with zip code "${zip(lower)}"`;
}

function fulfillmentStep(lower: string): string {
  if (isDelivery(lower)) return 'And the user selects "Delivery" as the order type';
  return 'And the user selects "Pickup" as the order type';
}

function timingStep(lower: string): string {
  if (isFuture(lower)) return 'And the user selects a future time slot for the order';
  return 'And the user selects "ASAP" fulfillment';
}

function checkoutSteps(lower: string): string[] {
  const lines: string[] = [];
  lines.push('When the user proceeds to checkout');
  if (isGuest(lower)) {
    lines.push('And the user enters guest contact information');
  }
  return lines;
}

function ccPaymentSteps(): string[] {
  return [
    `And the user enters credit card number "${CC_NUMBER}", expiry "${CC_EXPIRY}", and CVV "${CC_CVV}"`,
    'And the user clicks "Place Order"',
    'Then the order should be placed successfully',
    'And the order confirmation page should display with correct details',
  ];
}

// ── Per-Title Step Generators ──────────────────────────────────────

function generateMaxQuantitySteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user selects a menu item',
    'And the user adds the item to the bag',
    'And the user opens the bag',
    'When the user increases the item quantity to 20',
    'Then the quantity should update to 20 in the bag',
    'When the user tries to increase the quantity beyond 20',
    'Then the quantity should remain at 20 and not exceed the maximum limit',
    'And a maximum quantity message should be displayed to the user',
  ];
}

function generateMenuBrowseSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'Then the menu categories should be displayed on the left navigation',
    'When the user selects a category',
    'Then the products in that category should be displayed on the PLP',
    'When the user clicks on a product',
    'Then the PDP should display with product name, image, price, and customization options',
  ];
}

function generateNutritionSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user selects a menu item from any category',
    'Then the PDP should display for the selected item',
    'When the user clicks on "Nutrition Info" for the item',
    'Then the nutrition information panel should display',
    'And the calorie count should be visible',
    'And the allergen details should be listed',
    'And the full nutritional breakdown (fat, protein, carbs, sodium) should be shown',
  ];
}

function generateModifierBagSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user selects a menu item with modifiers',
    'And the user adds the item to the bag with default modifiers',
    'And the user opens the bag',
    'When the user taps the item in the bag to edit it',
    'And the user changes a modifier option (e.g. size, flavor, or add-on)',
    'And the user saves the modification',
    'Then the bag should reflect the updated modifier selection',
    'And the item price should update if applicable',
  ];
}

function generateModifierIntensityBagSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user selects a menu item that has intensity-level modifiers',
    'And the user selects a modifier with intensity (e.g. Regular, Extra, Light)',
    'And the user adds the item to the bag',
    'And the user opens the My Bag modal',
    'Then the modifier with intensity level should display correctly in the bag',
    'And the intensity label should match the selection made on the PDP',
  ];
}

function generateModifierIntensityFullFlowSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user selects a menu item that has intensity-level modifiers',
    'And the user selects a modifier with intensity (e.g. Regular, Extra, Light)',
    'And the user adds the item to the bag',
    'Then the modifier with intensity should display in the bag',
    'When the user proceeds to checkout',
    'Then the modifier with intensity should display on the checkout page',
    'When the user completes payment',
    'Then the order confirmation page should show the modifier with intensity',
    'And the confirmation email should include the modifier with intensity details',
    'When the user checks the order in Order History',
    'Then the order details should show the modifier with intensity correctly',
  ];
}

function generateTempUnavailableLocationSteps(lower: string): string[] {
  return [
    loginStep(lower),
    `When the user searches for a store location using zip code "${zip(lower)}"`,
    'Then the store results list should display',
    'When a store has a temporarily unavailable status',
    'Then the "Temporarily Unavailable" label should be visible in the locations dropdown header',
    'And the user should not be able to select that store for ordering',
  ];
}

function generateTempUnavailableMenuSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'Then the menu categories should be displayed',
    'When a product is marked as temporarily unavailable',
    'Then the "Temporarily Unavailable" message should appear on the PLP for that product',
    'When the user clicks on the unavailable product',
    'Then the PDP should show the "Temporarily Unavailable" status',
    'And the "Add to Bag" button should be disabled for that product',
  ];
}

function generateRewardsPriceSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Rewards section',
    'And the user selects the "Coke Your Way Green Apple" reward',
    'And the user selects a size for the reward item',
    'Then the correct price for the selected size should display',
    'When the user adds the reward item to the bag',
    'Then the bag should show the reward item with the correct size-based price',
    'When the user proceeds to checkout',
    'Then the checkout page should reflect the correct price for the size',
    'When the user completes the order',
    'Then the confirmation email should show the reward item with the correct price',
  ];
}

function generatePaymentTenderLogoSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user adds a menu item to the bag',
    'And the user proceeds to checkout',
    'And the user enters credit card details for payment',
    'And the user places the order',
    'Then the order confirmation page should display',
    'And the payment tender logo (Visa/Mastercard/Amex) should be visible',
    'And the branding should match the card type used for payment',
  ];
}

function generatePhoneOTPSteps(lower: string): string[] {
  return [
    loginStep(lower),
    'When the user navigates to the Profile page',
    'And the user taps on the phone number field to edit it',
    'And the user enters a new valid phone number',
    'And the user submits the phone number update',
    'Then an OTP verification code should be sent via SMS',
    'When the user enters the received OTP code',
    'Then the phone number should be updated successfully',
    'And the profile should display the new phone number',
  ];
}

function generateComplexDiscountSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user adds an item eligible for auto-discount to the bag',
    'And the user adds another item eligible for a different offer',
    'Then the auto-discount should be applied to the qualifying item in the bag',
    'When the user applies a promo code',
    'Then the promo code discount should stack with the auto-discount',
    'And the bag total should reflect both discounts applied correctly',
    'When the user proceeds to checkout',
    'Then the checkout page should show the itemized discounts and correct total',
  ];
}

function generateMFAProfileDeletionSteps(lower: string): string[] {
  return [
    loginStep(lower),
    'When the user navigates to the Profile page',
    'Then the user profile information should be displayed',
    'When the user updates first name and last name',
    'Then the profile changes should be saved successfully',
    'When the user navigates to security settings',
    'And the user enables MFA (multi-factor authentication)',
    'Then MFA should be activated on the account',
    'When the user initiates account deletion',
    'Then the user should see a confirmation prompt',
    'And the account should be marked for deletion after confirmation',
  ];
}

function generateAutoDiscountSteps(lower: string): string[] {
  const lines: string[] = [loginStep(lower)];
  lines.push(storeStep(lower));
  lines.push(fulfillmentStep(lower));
  lines.push(timingStep(lower));

  if (lower.includes('multiple quantity')) {
    lines.push(
      'When the user navigates to the Menu page',
      'And the user adds a menu item to the bag',
      'And the user increases the item quantity to 3',
      'Then the auto-discount should be applied to the qualifying items',
      'And the discount should apply correctly across multiple quantities',
    );
  } else if (lower.includes('reward')) {
    lines.push(
      'When the user navigates to the Menu page',
      'And the user adds a menu item eligible for auto-discount to the bag',
      'Then the auto-discount should be applied in the bag',
      'When the user navigates to the Rewards section',
      'And the user applies a reward to a qualifying item',
      'Then both the auto-discount and reward should be reflected in the bag',
    );
  } else if (lower.includes('promo')) {
    lines.push(
      'When the user navigates to the Menu page',
      'And the user adds a menu item eligible for auto-discount to the bag',
      'Then the auto-discount should be applied in the bag',
      'When the user applies a promo code at checkout',
      'Then both the auto-discount and promo code discount should be applied',
    );
  } else {
    // Auto Discount + Auto Discount
    lines.push(
      'When the user navigates to the Menu page',
      'And the user adds an item eligible for auto-discount #1 to the bag',
      'And the user adds another item eligible for auto-discount #2 to the bag',
      'Then both auto-discounts should be applied in the bag',
    );
  }

  lines.push(...checkoutSteps(lower));
  lines.push(...ccPaymentSteps());
  return lines;
}

function generateAutoDiscountPromoVerifiedSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user adds Product A (eligible for auto-discount) to the bag',
    'And the user adds Product B (eligible for promo code) to the bag',
    'Then auto-discount should be applied to Product A',
    'When the user enters a promo code',
    'Then the promo code discount should be applied to Product B',
    'When the user proceeds to checkout',
    'Then the order confirmation screen should display both discounts separately',
    'And the auto-discount and promo code should be on different products',
  ];
}

function generateOrderHistoryReorderSteps(lower: string): string[] {
  const lines = [loginStep(lower), storeStep(lower)];
  lines.push(
    'When the user navigates to Order History',
    'Then the user should see a list of past orders',
    'When the user selects a past order',
    'And the user clicks "Reorder"',
    'Then the items from the past order should be added to the bag',
  );
  if (lower.includes('future') || lower.includes('pickup')) {
    lines.push(
      'When the user proceeds to checkout',
      'And the user selects a future time slot',
      ...ccPaymentSteps(),
    );
  }
  return lines;
}

function generateFavoriteItemsSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user selects a menu item',
    'And the user taps the heart/favorite icon on the item',
    'Then the item should be saved to favorites',
    'When the user navigates to the Favorites section',
    'Then the favorited item should appear in the favorites list',
    'And the favorite item should display the correct name and price',
  ];
}

function generateFavoriteLocationSteps(lower: string): string[] {
  return [
    loginStep(lower),
    `When the user searches for a location using zip code "${zip(lower)}"`,
    'And the user selects a store from the results',
    'And the user taps the heart/favorite icon on the store location',
    'Then the store should be saved to favorite locations',
    'When the user navigates to the Favorites > Locations section',
    'Then the favorited store should appear with its address and name',
  ];
}

function generateGuestNoFavoritesSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'Then the user should not see a heart/favorite icon on menu items',
    'When the user navigates to Favorites',
    'Then the Favorites section should prompt the user to sign in',
    'And the user should not see any favorite items or favorite locations',
  ];
}

function generateFacebookLoginSteps(lower: string): string[] {
  return [
    'Given the user is on the Brand Three Desktop Web login page',
    'When the user clicks "Sign in with Facebook"',
    'Then a Facebook authentication window should appear',
    'When the user enters valid Facebook credentials',
    'And the user authorizes the Brand Three app',
    'Then the user should be redirected back to Brand Three Desktop Web',
    'And the user should be logged in successfully',
    'And the user profile should display the Facebook account name',
  ];
}

function generateSignupSteps(lower: string): string[] {
  if (lower.includes('place') && (lower.includes('order') || lower.includes('pickup'))) {
    // Signup + place order
    return [
      'Given the user is on the Brand Three Desktop Web registration page',
      'When the user enters a new email, password, first name, last name, and phone number',
      'And the user agrees to terms and completes the signup',
      'Then the account should be created successfully',
      'And the user should be logged in automatically',
      storeStep(lower),
      'When the user navigates to the Menu page',
      'And the user adds a menu item to the bag',
      fulfillmentStep(lower),
      'And the user proceeds to checkout',
      'When the user navigates to the Rewards section',
      'And the user applies a valid reward or deal to the order',
      'Then the reward/deal discount should be applied',
      ...ccPaymentSteps(),
    ];
  }
  return [
    'Given the user is on the Brand Three Desktop Web registration page',
    'When the user enters a new email, password, first name, last name, and phone number',
    'And the user agrees to terms and completes the signup',
    'Then the account should be created successfully',
    'And the user should be redirected to the home page as a logged-in user',
  ];
}

function generateChangePasswordSteps(lower: string): string[] {
  return [
    loginStep(lower),
    'When the user navigates to the Profile page',
    'And the user clicks on "Change Password"',
    'And the user enters the current password "replace_me"',
    'And the user enters a new password "Newreplace_me"',
    'And the user confirms the new password "Newreplace_me"',
    'And the user submits the password change',
    'Then the password should be updated successfully',
    'And the user should see a confirmation message',
  ];
}

function generateRewardAppliedSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user adds a qualifying item (lower-priced) to the bag',
    'When the user navigates to the Rewards section',
    'And the user selects a reward to apply',
    'Then the reward should be applied to the qualifying item',
    'And the discount amount should be the lesser of the reward value and the item price',
    'And the bag total should reflect the reward discount correctly',
  ];
}

function generateRewardNoQualifyingSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Menu page',
    'And the user adds a non-qualifying item to the bag',
    'When the user navigates to the Rewards section',
    'And the user attempts to apply a reward',
    'Then a modal alert should be displayed',
    'And the alert should say no qualifying items are in the bag for this reward',
    'And the reward should not be applied',
  ];
}

function generateGuestOrderSteps(lower: string): string[] {
  const lines: string[] = [loginStep(lower), storeStep(lower)];
  lines.push(fulfillmentStep(lower));
  lines.push(timingStep(lower));

  if (lower.includes('delivery')) {
    lines.push('And the user enters a valid delivery address');
  }

  // Product category hints
  if (lower.includes('drink') || lower.includes('frozen')) {
    lines.push(
      'When the user navigates to the Drinks/Frozen Zone category on the Menu',
      'And the user adds a drink or frozen item to the bag',
    );
  } else {
    lines.push(
      'When the user navigates to the Menu page',
      'And the user adds a menu item to the bag',
    );
  }

  lines.push(...checkoutSteps(lower));

  // Payment method
  if (lower.includes('apple pay') || lower.includes('google pay')) {
    lines.push(
      'And the user selects Apple Pay / Google Pay as payment method',
      'And the user authorizes the payment',
    );
  } else {
    lines.push(`And the user enters credit card number "${CC_NUMBER}", expiry "${CC_EXPIRY}", and CVV "${CC_CVV}"`);
  }

  lines.push(
    'And the user clicks "Place Order"',
    'Then the order should be placed successfully',
    'And the order confirmation page should display with correct details',
  );
  return lines;
}

function generateAuthOrderSteps(lower: string): string[] {
  const lines: string[] = [loginStep(lower), storeStep(lower)];
  lines.push(fulfillmentStep(lower));
  lines.push(timingStep(lower));

  if (lower.includes('delivery')) {
    lines.push('And the user enters a valid delivery address');
  }

  // Product hints
  if (lower.includes('drink') || lower.includes('frozen')) {
    lines.push('When the user navigates to the Drinks/Frozen Zone category on the Menu');
    lines.push('And the user adds a drink or frozen item to the bag');
  } else if (lower.includes('combo')) {
    lines.push('When the user navigates to the Menu page');
    lines.push('And the user selects a combo meal and builds it');
  } else if (lower.includes('food')) {
    lines.push('When the user navigates to the Food category on the Menu');
    lines.push('And the user adds a food item to the bag');
  } else {
    lines.push('When the user navigates to the Menu page');
    lines.push('And the user adds a menu item to the bag');
  }

  // Discount handling
  if (lower.includes('auto discount') && lower.includes('reward')) {
    lines.push('Then the auto-discount should be applied to the qualifying item');
    lines.push('When the user applies a reward from the Rewards section');
    lines.push('Then both auto-discount and reward should be reflected in the bag');
  } else if (lower.includes('auto discount') && lower.includes('promo')) {
    lines.push('Then the auto-discount should be applied to the qualifying item');
    lines.push('When the user enters a promo code');
    lines.push('Then both auto-discount and promo code should be reflected in the bag');
  } else if (lower.includes('auto discount')) {
    lines.push('Then the auto-discount should be applied to the qualifying item in the bag');
  }

  lines.push(...checkoutSteps(lower));

  // Payment method
  if (lower.includes('gift card')) {
    if (lower.includes('promo')) {
      lines.push('When the user enters a promo code');
      lines.push('Then the promo code discount should be applied');
    }
    if (lower.includes('reload')) {
      lines.push('And the user reloads the gift card with additional funds');
    }
    lines.push('And the user selects gift card as the payment method');
    lines.push('And the user clicks "Place Order"');
  } else if (lower.includes('apple pay') || lower.includes('google pay')) {
    lines.push('And the user selects Apple Pay / Google Pay as payment method');
    lines.push('And the user authorizes the payment');
    lines.push('And the user clicks "Place Order"');
  } else {
    lines.push(`And the user enters credit card number "${CC_NUMBER}", expiry "${CC_EXPIRY}", and CVV "${CC_CVV}"`);
    lines.push('And the user clicks "Place Order"');
  }

  lines.push(
    'Then the order should be placed successfully',
    'And the order confirmation page should display with correct details',
  );
  return lines;
}

function generateCreditCardEditSteps(lower: string): string[] {
  return [
    loginStep(lower),
    'When the user navigates to the Profile page',
    'And the user clicks on the "Payment Methods" section',
    'Then the saved credit card(s) should be displayed',
    'When the user clicks "Edit" on an existing credit card',
    'And the user updates the card number, expiry, or CVV',
    'And the user saves the changes',
    'Then the updated credit card details should be saved successfully',
    'And the updated card should display in the payment methods list',
  ];
}

function generateNewCreditCardSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user navigates to the Profile page',
    'And the user clicks on "Payment Methods"',
    'And the user clicks "Add New Credit Card"',
    `And the user enters card number "${CC_NUMBER}", expiry "${CC_EXPIRY}", and CVV "${CC_CVV}"`,
    'And the user saves the new card',
    'Then the new credit card should be added to the payment methods list',
    'And the card type logo (Mastercard) should display correctly',
  ];
}

function generateConfirmationEmailSteps(lower: string): string[] {
  return [
    loginStep(lower),
    storeStep(lower),
    'When the user adds a menu item to the bag',
    'And the user proceeds to checkout',
    ...ccPaymentSteps(),
    'And a confirmation email should be sent to the user\'s registered email',
    'Then the confirmation email should contain the order details',
    'And the email should include the order number, items, total, and store information',
  ];
}

function generateLoginLogoutSteps(lower: string): string[] {
  return [
    'Given the user is on the Brand Three Desktop Web login page',
    `When the user enters email "${EMAIL}" and password "${PASSWORD}"`,
    'And the user clicks "Sign In"',
    'Then the user should be logged in successfully',
    'And the user should see their name on the home page',
    'When the user clicks on the profile/account menu',
    'And the user clicks "Sign Out"',
    'Then the user should be logged out',
    'And the user should be redirected to the home page as a guest',
  ];
}

function generateMapPinSteps(lower: string): string[] {
  return [
    loginStep(lower),
    `When the user searches for a location using zip code "${zip(lower)}"`,
    'Then the store results list and map view should be displayed',
    'When the user selects a store from the list view',
    'Then the corresponding pin on the map should be highlighted with the brand logo',
    'When the user selects a different store from the list view',
    'Then the previously selected pin should return to normal size',
    'And the newly selected store pin should be highlighted',
  ];
}

function generateProfileUpdateSteps(lower: string): string[] {
  return [
    loginStep(lower),
    'When the user navigates to the Profile page',
    'And the user updates the phone number field with a new number',
    'And the user updates the first name',
    'And the user updates the last name',
    'And the user saves the profile changes',
    'Then the profile should display the updated phone number, first name, and last name',
    'And the changes should persist after refreshing the page',
  ];
}

// ── Category Detection ─────────────────────────────────────────────

type WebCategory =
  | 'max-quantity'
  | 'menu-browse'
  | 'nutrition'
  | 'modifier-bag'
  | 'modifier-intensity-bag'
  | 'modifier-intensity-full'
  | 'temp-unavail-location'
  | 'temp-unavail-menu'
  | 'rewards-price'
  | 'payment-tender-logo'
  | 'phone-otp'
  | 'complex-discount'
  | 'mfa-profile-deletion'
  | 'offers-deals'
  | 'offers-deals-promo-verified'
  | 'order-history-reorder'
  | 'favorite-items'
  | 'favorite-location'
  | 'guest-no-favorites'
  | 'facebook-login'
  | 'signup'
  | 'change-password'
  | 'reward-applied'
  | 'reward-no-qualifying'
  | 'guest-order'
  | 'auth-order'
  | 'credit-card-edit'
  | 'new-credit-card'
  | 'confirmation-email'
  | 'login-logout'
  | 'map-pin'
  | 'profile-update';

function detectWebCategory(summary: string): WebCategory {
  const lower = summary.toLowerCase();

  // Max quantity
  if (lower.includes('max quantity') || lower.includes('maximum quantity')) return 'max-quantity';

  // Temporarily unavailable
  if (lower.includes('temporarily unavailable') && lower.includes('location')) return 'temp-unavail-location';
  if (lower.includes('temporarily unavailable') && (lower.includes('plp') || lower.includes('pdp') || lower.includes('menu'))) return 'temp-unavail-menu';

  // Modifiers with intensity — full flow (bag + checkout + email + history)
  if (lower.includes('intensity') && (lower.includes('checkout') || lower.includes('confirmation') || lower.includes('email'))) return 'modifier-intensity-full';
  // Modifiers with intensity — bag only
  if (lower.includes('intensity') && lower.includes('bag')) return 'modifier-intensity-bag';
  // Modifier/edit in bag
  if (lower.includes('modif') && lower.includes('bag')) return 'modifier-bag';

  // Map pin highlighting
  if (lower.includes('map') && lower.includes('pin')) return 'map-pin';

  // Nutrition
  if (lower.includes('nutrition')) return 'nutrition';

  // Rewards: specific patterns
  if (lower.includes('coke your way') || lower.includes('size price')) return 'rewards-price';
  if (lower.includes('no qualifying') || lower.includes('modal alert')) return 'reward-no-qualifying';
  if (lower.includes('reward') && lower.includes('less price')) return 'reward-applied';

  // Payment tender logo
  if (lower.includes('tender logo') || lower.includes('branding')) return 'payment-tender-logo';

  // Phone OTP
  if (lower.includes('otp') || (lower.includes('phone') && lower.includes('verified'))) return 'phone-otp';

  // Complex discount stacking
  if (lower.includes('complex') && lower.includes('discount')) return 'complex-discount';

  // MFA + Account deletion
  if (lower.includes('mfa') || lower.includes('account deletion')) return 'mfa-profile-deletion';

  // Auto-discount + promo on different products (verified on order confirmation)
  if (lower.includes('auto-discount') && lower.includes('promo') && lower.includes('different product')) return 'offers-deals-promo-verified';

  // Gift card orders — must come BEFORE generic auto-discount check
  // (Gift card + auto discount is a gift card payment flow, not an offer construct test)
  if (lower.includes('gift card')) return 'auth-order';

  // Auto discount / Offers & Deals (GENERIC_Reg_OfferConstruct)
  if (lower.includes('auto discount') || lower.includes('auto-discount')) {
    // Auth order-style with combos + apple pay
    if (lower.includes('combo') || lower.includes('apple pay') || lower.includes('google pay')) return 'auth-order';
    return 'offers-deals';
  }

  // Order history / reorder
  if (lower.includes('reorder') || lower.includes('order history')) return 'order-history-reorder';

  // Favorites
  if (lower.includes('favorite') && lower.includes('guest')) return 'guest-no-favorites';
  if (lower.includes('favorite') && lower.includes('location')) return 'favorite-location';
  if (lower.includes('favorite') && lower.includes('item')) return 'favorite-items';

  // Facebook login
  if (lower.includes('facebook')) return 'facebook-login';

  // Signup
  if (lower.includes('sign up') || lower.includes('signup')) return 'signup';

  // Change password
  if (lower.includes('change password')) return 'change-password';

  // Login/logout
  if (lower.includes('login') && lower.includes('logout')) return 'login-logout';

  // ─── ORDER PLACEMENT patterns (must come before credit card/payment) ───
  // Guest order flows (these contain "credit card" but are order-placement tests)
  if (lower.includes('guest') && lower.includes('place') && lower.includes('order')) return 'guest-order';
  // Authenticated order flows (place order with CC, delivery, etc.)
  if (lower.includes('place') && lower.includes('order') && !lower.includes('edit')) return 'auth-order';

  // Credit card edit (only when explicitly about editing, NOT placing an order)
  if (lower.includes('credit card') && /\bedit/i.test(lower)) return 'credit-card-edit';

  // New credit card addition
  if (lower.includes('new credit card') || lower.includes('credit card addition') || lower.includes('card addition')) return 'new-credit-card';

  // Confirmation email
  if (lower.includes('confirmation email') || lower.includes('confirmation') && lower.includes('email')) return 'confirmation-email';

  // Profile update (name, phone)
  if (lower.includes('profile') && (lower.includes('update') || lower.includes('first name') || lower.includes('last name'))) return 'profile-update';

  // Guest order flows
  if (lower.includes('guest')) return 'guest-order';

  // Authenticated order flows (payment with place/order context, delivery, pickup)
  if (lower.includes('place') || lower.includes('delivery') || lower.includes('pickup')) return 'auth-order';

  // Fallback
  return 'menu-browse';
}

// ── Main Generator ─────────────────────────────────────────────────

export function generateWebGherkin(issue: XrayTestIssue): string {
  const summary = issue.summary;
  const lower = summary.toLowerCase();
  const category = detectWebCategory(summary);

  let steps: string[];
  switch (category) {
    case 'max-quantity':              steps = generateMaxQuantitySteps(lower); break;
    case 'menu-browse':               steps = generateMenuBrowseSteps(lower); break;
    case 'nutrition':                 steps = generateNutritionSteps(lower); break;
    case 'modifier-bag':              steps = generateModifierBagSteps(lower); break;
    case 'modifier-intensity-bag':    steps = generateModifierIntensityBagSteps(lower); break;
    case 'modifier-intensity-full':   steps = generateModifierIntensityFullFlowSteps(lower); break;
    case 'temp-unavail-location':     steps = generateTempUnavailableLocationSteps(lower); break;
    case 'temp-unavail-menu':         steps = generateTempUnavailableMenuSteps(lower); break;
    case 'rewards-price':             steps = generateRewardsPriceSteps(lower); break;
    case 'payment-tender-logo':       steps = generatePaymentTenderLogoSteps(lower); break;
    case 'phone-otp':                 steps = generatePhoneOTPSteps(lower); break;
    case 'complex-discount':          steps = generateComplexDiscountSteps(lower); break;
    case 'mfa-profile-deletion':      steps = generateMFAProfileDeletionSteps(lower); break;
    case 'offers-deals':             steps = generateAutoDiscountSteps(lower); break;
    case 'offers-deals-promo-verified': steps = generateAutoDiscountPromoVerifiedSteps(lower); break;
    case 'order-history-reorder':     steps = generateOrderHistoryReorderSteps(lower); break;
    case 'favorite-items':            steps = generateFavoriteItemsSteps(lower); break;
    case 'favorite-location':         steps = generateFavoriteLocationSteps(lower); break;
    case 'guest-no-favorites':        steps = generateGuestNoFavoritesSteps(lower); break;
    case 'facebook-login':            steps = generateFacebookLoginSteps(lower); break;
    case 'signup':                    steps = generateSignupSteps(lower); break;
    case 'change-password':           steps = generateChangePasswordSteps(lower); break;
    case 'reward-applied':            steps = generateRewardAppliedSteps(lower); break;
    case 'reward-no-qualifying':      steps = generateRewardNoQualifyingSteps(lower); break;
    case 'guest-order':               steps = generateGuestOrderSteps(lower); break;
    case 'auth-order':                steps = generateAuthOrderSteps(lower); break;
    case 'credit-card-edit':          steps = generateCreditCardEditSteps(lower); break;
    case 'new-credit-card':           steps = generateNewCreditCardSteps(lower); break;
    case 'confirmation-email':        steps = generateConfirmationEmailSteps(lower); break;
    case 'login-logout':              steps = generateLoginLogoutSteps(lower); break;
    case 'map-pin':                   steps = generateMapPinSteps(lower); break;
    case 'profile-update':            steps = generateProfileUpdateSteps(lower); break;
    default:                          steps = generateMenuBrowseSteps(lower); break;
  }

  // Build Gherkin with Feature + Tags + Scenario
  const stripped = stripWebPrefix(summary);
  const featureArea = detectFeatureArea(lower);
  const tags = buildTags(issue);

  const gherkin = [
    `Feature: Brand Three Desktop Web ${featureArea}`,
    '',
    `  ${tags}`,
    `  Scenario: ${stripped}`,
    ...steps.map(s => `    ${s}`),
  ].join('\n');

  return gherkin;
}

export function getWebCategory(summary: string): WebCategory {
  return detectWebCategory(summary);
}

// ── Helpers ────────────────────────────────────────────────────────

function stripWebPrefix(s: string): string {
  // "B3 | WEB | Bag - Max Quantity..." → "Bag - Max Quantity..."
  const m = s.match(/^(?:B3|B2|B1)\s*\|\s*WEB\s*\|\s*(.+)/i);
  return m ? m[1].trim() : s;
}

function detectFeatureArea(lower: string): string {
  if (lower.includes('location') || lower.includes('map')) return 'Location';
  if (lower.includes('nutrition')) return 'Menu';
  if (lower.includes('modifier') || lower.includes('intensity')) return 'PDP_PLP';
  if (lower.includes('menu') || lower.includes('plp') || lower.includes('pdp')) return 'Menu';
  if (lower.includes('bag') || lower.includes('quantity')) return 'Menu';
  if (lower.includes('reward') || lower.includes('loyalty') || lower.includes('coke your way')) return 'Loyalty';
  if (lower.includes('auto discount') || lower.includes('auto-discount') || lower.includes('discount') || lower.includes('promo') || lower.includes('offer')) return 'OfferConstruct';
  if (lower.includes('gift card')) return 'GiftCards';
  if (lower.includes('apple pay') || lower.includes('google pay') || lower.includes('credit card') || lower.includes('tender')) return 'Wallet';
  if (lower.includes('payment') || lower.includes('checkout')) return 'Payments';
  if (lower.includes('order history') || lower.includes('reorder')) return 'OrderHistory';
  if (lower.includes('order confirmation') || lower.includes('confirmation email')) return 'Notifications';
  if (lower.includes('favorite')) return 'Loyalty';
  if (lower.includes('mfa') || lower.includes('account deletion')) return 'MFA';
  if (lower.includes('profile') || lower.includes('phone') || lower.includes('password')) return 'UserManagement';
  if (lower.includes('login') || lower.includes('logout') || lower.includes('sign')) return 'SignIn';
  if (lower.includes('facebook')) return 'SignIn';
  if (lower.includes('signup') || lower.includes('sign up')) return 'UserSignUp';
  if (lower.includes('temporarily unavailable')) return 'MenuUnavailability';
  return 'General';
}

function buildTags(issue: XrayTestIssue): string {
  const tags = new Set<string>();
  tags.add('@B3');
  tags.add('@WEB');

  // Add from labels
  for (const label of issue.labels || []) {
    if (label.startsWith('@')) tags.add(label);
    else tags.add(`@${label}`);
  }

  return [...tags].join(' ');
}
