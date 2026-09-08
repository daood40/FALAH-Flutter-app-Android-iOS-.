---
name: flutter-monetization
description: Monetize a Flutter app — in-app purchases and subscriptions (in_app_purchase / RevenueCat), server-side receipt validation, entitlement gating, paywall UX, AdMob ads, and store policy on payments. Use when adding paid features, or when the user says "اشتراك", "دفع", "شراء داخل التطبيق", "إعلانات", "subscription", "in-app purchase", "paywall", "AdMob".
---

# Monetization

## Store policy first — this decides your architecture

**Digital goods consumed inside the app** (premium features, coins, ad removal, subscriptions to content) **must** use Apple IAP and Google Play Billing. Both stores take a commission (typically 15–30%). Bypassing this gets the app removed.

**Physical goods and real-world services** (a delivery, an event ticket, a consultation) use a normal payment gateway (Stripe, Paymob, local providers) and pay no store commission.

**Cash prizes, contests, gambling-adjacent mechanics** are heavily restricted: Google Play and the App Store both require compliance with local gambling law, geographic restrictions, and often a separate licence. A competition where users pay to enter and winners receive money is treated very differently from a free contest with sponsored prizes. Check `support.google.com/googleplay/android-developer` (Real-Money Gambling) and App Store Review Guideline 4.7 / 5.3 **before building**, and prefer a model where entry is free or the prize is non-cash if you want a smooth review.

## Which library

| | `in_app_purchase` (official) | RevenueCat (`purchases_flutter`) |
|---|---|---|
| Cost | free | free tier, then a % of tracked revenue |
| Receipt validation | you build it | included |
| Cross-platform entitlements | you build it | included |
| Subscription state, renewals, grace periods | you handle every edge case | handled |

For anything beyond a single one-time purchase, **RevenueCat saves weeks**. Subscription state machines (renewal, cancellation, billing retry, grace period, refund, family sharing, upgrade/downgrade proration) are genuinely hard to get right.

## in_app_purchase basics

```dart
final iap = InAppPurchase.instance;
if (!await iap.isAvailable()) return;

final res = await iap.queryProductDetails({'pro_monthly', 'pro_yearly'});
final product = res.productDetails.first;

iap.purchaseStream.listen(_onPurchases);

await iap.buyNonConsumable(purchaseParam: PurchaseParam(productDetails: product));

Future<void> _onPurchases(List<PurchaseDetails> list) async {
  for (final p in list) {
    switch (p.status) {
      case PurchaseStatus.pending:
        _showPending();
      case PurchaseStatus.error:
        _showError(p.error?.message);
      case PurchaseStatus.purchased:
      case PurchaseStatus.restored:
        final ok = await _verifyOnServer(p.verificationData.serverVerificationData);
        if (ok) await _grantEntitlement();
    }
    if (p.pendingCompletePurchase) await iap.completePurchase(p);
  }
}
```

Two things people get wrong and both cause lost money or a rejected app:

1. **Always call `completePurchase`.** If you don't, Apple refunds the user automatically after a few days and Google re-delivers the purchase forever.
2. **Never grant entitlement based on the client alone.** Validate the receipt server-side against Apple's `verifyReceipt` / App Store Server API and Google Play Developer API, and store the entitlement in your database. A client-only flag is trivially patched.

## Server-side entitlement

```sql
create table entitlements (
  user_id uuid primary key references auth.users on delete cascade,
  plan text not null,                 -- free | pro
  expires_at timestamptz,
  store text,                         -- apple | google
  original_transaction_id text unique,
  updated_at timestamptz default now()
);
```

Gate features with an RLS policy or a server check, not an `if (isPro)` in Dart. Listen to store server notifications (App Store Server Notifications v2, Google Real-time Developer Notifications via Pub/Sub) so cancellations and refunds revoke access without the app opening.

## Restore purchases — required

```dart
await iap.restorePurchases();
```

A visible "استعادة المشتريات" button is **mandatory** for App Store review. Apps get rejected for its absence.

## Paywall UX

- Show value before the price. Let the user experience the free tier first.
- Present 2–3 plans, mark one "الأكثر توفيراً", show the monthly-equivalent price for the yearly plan.
- State clearly: price, currency, billing period, auto-renewal, and how to cancel. Apple requires this text near the buy button, with links to your terms and privacy policy.
- Never block the entire app on first launch with a paywall — that is a common rejection.
- Localize prices with `product.price` (already formatted for the store's locale) — never hardcode a number.

## Testing

- Android: upload a signed build to an internal-testing track first; add licence testers in the Play Console. IAP does not work on a debug build.
- iOS: StoreKit configuration file for local testing, then sandbox testers, then TestFlight.
- Test: purchase, restore, cancel, expiry, refund, and network failure mid-purchase.

## AdMob

```bash
flutter pub add google_mobile_ads
```

```dart
final banner = BannerAd(
  adUnitId: Env.bannerUnitId,
  size: AdSize.banner,
  request: const AdRequest(),
  listener: BannerAdListener(
    onAdLoaded: (_) => setState(() => _loaded = true),
    onAdFailedToLoad: (ad, e) => ad.dispose(),
  ),
)..load();
```

- Use **test ad unit ids** during development. Clicking your own live ads gets the account banned permanently.
- `dispose()` every ad; reserve its space in the layout so content doesn't jump when it loads.
- Interstitials: only at natural breaks (level end, task complete), never on app open or mid-task. Both stores and AdMob penalize aggressive placement.
- Rewarded ads convert best in games — grant the reward only in `onUserEarnedReward`.
- Ads require a privacy policy, a consent flow in the EU/UK (UMP SDK), and correct child-directed / age settings. `App Tracking Transparency` prompt on iOS before requesting personalized ads.

## Choosing a model

Subscriptions suit ongoing value (content, sync, AI usage). One-time unlock suits a tool. Ads suit high-volume, low-intent usage but pay little at small scale — for an app with a few thousand users, one subscription tier usually earns more than ads and costs less in UX.

## Checklist

- [ ] Digital goods use store billing; physical goods use a gateway
- [ ] Receipts validated server-side; entitlement stored server-side
- [ ] `completePurchase` always called
- [ ] Restore button present
- [ ] Store server notifications handled (cancel, refund, expiry)
- [ ] Prices shown from the store, localized
- [ ] Terms + privacy links on the paywall
- [ ] Tested purchase, restore, cancel and refund on real devices
