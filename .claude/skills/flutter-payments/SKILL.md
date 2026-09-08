---
name: flutter-payments
description: Taking real money for physical goods and real-world services in a Flutter app — server-created payment intents, Stripe PaymentSheet, webhooks as the source of truth, regional Arab gateways via hosted checkout, cash on delivery, refunds and PCI scope. Use when building a store, booking or delivery flow, or when the user says "دفع", "بوابة دفع", "بطاقة", "الدفع عند الاستلام", "فاتورة", "payment", "checkout", "gateway", "Stripe", "COD".
---

# Payments (physical goods & services)

**Scope check first.** A payment gateway is only allowed for **physical goods and real-world services** — a delivery, a booking, an event ticket, a consultation, a repair. Anything consumed inside the app (premium features, coins, ad removal, content subscriptions) **must** go through Apple IAP / Google Play Billing — see the `flutter-monetization` skill. Shipping a card form for digital goods gets the app removed from both stores.

## The only correct architecture

The app **never** holds a secret key and **never** decides that a payment succeeded.

| Step | Where | What happens |
|---|---|---|
| 1 | App | Sends `{cart_id}` (not a price) to your server |
| 2 | Server | Computes the amount itself, creates the payment intent/session with the **secret key**, returns the client secret / checkout URL |
| 3 | App | Presents the sheet or hosted page; user pays; 3DS handled by the gateway UI |
| 4 | Gateway → Server | **Webhook** confirms the payment; server verifies the signature and marks the order paid |
| 5 | App | Re-fetches the order from the server and shows its state |

The app returning "success" is a *hint to refresh*, never proof. A rooted device, a proxy, or a closed app mid-flow all break any client-side conclusion. Never send the amount from the client either — a tampered request buys a phone for 1 unit.

## Stripe with flutter_stripe

`flutter pub add flutter_stripe`. In `main()`, set the **publishable** key only (`pk_test_…` / `pk_live_…`); it is safe in the binary, the secret key (`sk_…`) never leaves your server.

```dart
WidgetsFlutterBinding.ensureInitialized();
Stripe.publishableKey = Env.stripePublishableKey;   // --dart-define, not hardcoded
Stripe.merchantIdentifier = 'merchant.com.example'; // Apple Pay only
await Stripe.instance.applySettings();
```

Android needs `minSdkVersion 21+` and a launcher Activity theme inheriting from AppCompat/MaterialComponents, or PaymentSheet crashes on open.

```dart
Future<void> pay(String orderId) async {
  // server creates the PaymentIntent and returns its client secret
  final r = await api.post('/orders/$orderId/payment-intent');

  // the sheet handles cards, wallets and 3D Secure itself
  await Stripe.instance.initPaymentSheet(
    paymentSheetParameters: SetupPaymentSheetParameters(
      paymentIntentClientSecret: r['clientSecret'] as String,
      merchantDisplayName: 'متجرنا',
      customerId: r['customerId'] as String?,
      customerEphemeralKeySecret: r['ephemeralKey'] as String?,
      style: ThemeMode.system,
    ),
  );

  try {
    await Stripe.instance.presentPaymentSheet();
  } on StripeException catch (e) {
    final cancelled = e.error.code == FailureCode.Canceled;   // not a failure
    showSnack(cancelled ? 'تم إلغاء عملية الدفع' : 'تعذر إتمام الدفع، حاول مرة أخرى');
    return;
  }
  // do NOT mark it paid here — ask the server what it thinks
  await ref.refresh(orderProvider(orderId).future);
}
```

3D Secure / SCA is presented by the sheet; you write no redirect code for it. Confirm parameter names against the `flutter_stripe` version in your `pubspec.lock` — `SetupPaymentSheetParameters` fields have changed between major versions.

## The webhook is the source of truth

Server side, verify the signature against the **raw** request body (a parsed-then-restringified body fails verification), then act idempotently.

```js
// Node/Stripe. Check current Stripe docs for the event list and helper signature.
app.post('/webhooks/stripe', express.raw({type: 'application/json'}), async (req, res) => {
  let event;
  try {
    event = stripe.webhooks.constructEvent(
      req.body, req.headers['stripe-signature'], process.env.STRIPE_WEBHOOK_SECRET);
  } catch (e) {
    return res.status(400).send('bad signature');    // unsigned = not from Stripe
  }
  // a webhook WILL be retried and may arrive twice
  const fresh = await db.insertIfAbsent('processed_events', {id: event.id});
  if (!fresh) return res.sendStatus(200);            // already handled, don't double-credit

  if (event.type === 'payment_intent.succeeded') {
    await db.markOrderPaid(event.data.object.metadata.order_id, event.data.object.id);
  }
  res.sendStatus(200);                               // 200 fast; queue slow work
});
```

Two separate idempotency concerns, both required. **Outbound**: pass an idempotency key when *creating* a charge, so a retried create does not double-charge. **Inbound**: store every processed `event.id`, so a redelivered webhook does not double-fulfil.

## Money is an integer

Store and transmit amounts as **integers in the smallest currency unit** (`2500` = 25.00 SAR) plus an ISO-4217 currency code — never `double`. `0.1 + 0.2 != 0.3` in IEEE-754 and rounding drift becomes real missing money. Decimal places are per-currency: 2 for SAR/AED/EGP/USD, **3 for LYD, KWD, BHD, OMR, JOD, TND**, 0 for JPY. Gateways have their own rules for 3-decimal currencies (Stripe requires the minor amount to be a multiple of 10 for them) — check the gateway's currency reference before assuming ×100.

```dart
String formatMoney(int minor, String currency, String locale) {
  final digits = currencyDigits[currency]!;          // 2, 3 or 0
  return NumberFormat.currency(
    locale: locale,                                  // 'ar_LY', 'ar_SA', 'ar_EG'
    symbol: currencySymbols[currency],               // 'د.ل', 'ر.س', 'ج.م'
    decimalDigits: digits,
  ).format(minor / pow(10, digits));
}
```

Format for display only, at the edge. Under `ar` locales `intl` may render Arabic-Indic digits — pick one convention and apply it to prices, totals and invoices alike. Wrap prices in bidi isolates so a symbol does not jump to the wrong side of the number inside RTL text.

## Regional gateways in the Arab world

Paymob, HyperPay, Moyasar, Tap, Fawry, Telr, and Libyan bank/wallet rails (Sadad/Tadawul-style local services) follow the **same server-side pattern**: your server authenticates with a secret key, creates a payment/order, and trusts only the callback. The honest difference is SDK availability — many have **no maintained first-party Flutter SDK**, and community packages are often stale or unofficial. The practical, low-risk route:

1. Server creates the payment and returns a **hosted checkout URL**.
2. App opens it — `webview_flutter` with a `NavigationDelegate` watching for your return URL, or `url_launcher` with `LaunchMode.externalApplication` for stricter banks that reject WebViews. Bank/3DS pages run inside that hosted flow.
3. Return arrives as a **deep link / app link** (`app_links`) or an intercepted redirect.
4. App shows "جارٍ التأكيد…" and polls the server; the **callback/webhook** is what flips the order to paid.

Never treat "the redirect URL contained `status=success`" as proof — it is client-controlled. Verify server-side against the gateway's transaction-status API. API shapes, signature/HMAC schemes and sandbox rules differ per provider and change often: read that provider's current documentation rather than any snippet, and confirm whether they require IP allow-listing or a merchant callback registered in their dashboard.

## Cash on delivery

COD is a first-class payment method in much of the region, not a fallback. Model it as a real method with its own state path: order `pending` → `confirmed` → `out_for_delivery` → `paid` (collected by the courier) → `fulfilled`. Add COD-specific concerns: an availability check per city/zone, a maximum order value, an optional COD fee shown before confirmation, and a phone verification (OTP) step — COD's failure mode is a fake order, not a chargeback. Give the courier app/endpoint the ability to mark collection; never let the customer app do it.

## Order state machine

```
pending ──▶ processing ──▶ paid ──▶ fulfilled
   │            │            │
   ▼            ▼            ▼
 failed      failed      refunded / partially_refunded
```

Store the state on the **server**, transition it only from webhook/callback events or authenticated staff actions, and record every transition with the gateway event id. The app reads this state; it never writes it. Fulfil strictly on `paid`.

## Handling an interrupted payment

The user *will* close the WebView, kill the app, or lose signal mid-3DS — that is normal flow, not an error.

- On resume, re-fetch the order. While it is `pending`/`processing`, show "جارٍ التأكيد…" and poll with backoff for ~60–90 seconds; the webhook may simply be seconds behind, so never auto-fail.
- Never open a second payment intent for an order that already has one — reuse it, or cancel it server-side first. Make the pay endpoint idempotent per `order_id` so a double tap cannot create two charges.

## Refunds

Refunds are initiated **server-side** with the secret key, never from the app. Support partial refunds (amount in minor units), and drive the order state from the `charge.refunded` / `refund.updated` webhook rather than from the API response, so a refund created in the gateway dashboard is also reflected. Refunded settlement can take days at the bank — say so in the UI: "قد تستغرق عملية الاسترداد من 5 إلى 10 أيام عمل". Keep the refund reason and the operator id for audit.

## PCI scope

**Never build your own card form.** Raw PAN/CVV touching your Dart code or your server pushes you from SAQ-A into a far heavier PCI DSS assessment, and the stores treat homemade card fields as a red flag. Always use the gateway's own UI: Stripe PaymentSheet / `CardField`, or a hosted checkout page. Do not log, cache, screenshot or persist card data — not even the last four, unless the gateway hands it to you as a token/metadata. Enable `FLAG_SECURE`-style screenshot blocking on payment screens if your risk profile calls for it.

## Testing

- Use sandbox/test keys everywhere but production, and make it visually obvious the app is in test mode.
- Stripe test cards: `4242 4242 4242 4242` succeeds; `4000 0025 0000 3155` forces a 3DS challenge; `4000 0000 0000 9995` fails with insufficient funds. Check Stripe's current test-card list for the rest.
- Test the webhook locally with the gateway's CLI/tunnel and **replay** an event to prove idempotency holds. Rehearse: cancel at the sheet, kill the app mid-3DS, no network on return, duplicate tap, refund, partial refund, and a webhook arriving before the app returns.
- Regional gateways: request a sandbox merchant account early — approval takes days and often needs a commercial registration.

## Receipts

Generate the receipt **server-side** from the order record after it reaches `paid`, with an immutable sequential number, merchant details, itemized lines, tax/VAT, currency and the gateway transaction id. Email it and expose it in-app as a PDF/HTML view. Many jurisdictions in the region have specific e-invoicing rules (Saudi ZATCA phase-2 requires signed XML invoices with a QR code); confirm local requirements before launch — this is a compliance question, not a UI one.

## Common mistakes

- Sending the price from the client, or trusting a client-reported "paid".
- A secret key in the app, in `--dart-define`, or in a committed `.env`. It is extractable from the binary.
- Verifying the webhook against a JSON-parsed body instead of the raw bytes.
- No idempotency, so a retried webhook credits the order twice.
- Amounts as `double`, or blanket ×100 for a 3-decimal currency like LYD.
- Treating a WebView cancel as a payment failure and cancelling a payment that actually went through.
- Fulfilling on `payment_intent.created` instead of `succeeded`.
- Using a gateway for digital goods and getting pulled from the store.

## Checklist

- [ ] Digital goods routed to store billing, not this gateway
- [ ] Secret key server-only; app holds a publishable key at most
- [ ] Amount computed server-side from a cart id
- [ ] Webhook signature verified on the raw body
- [ ] Inbound event ids stored; outbound idempotency key sent
- [ ] Amounts stored as integer minor units, per-currency decimals correct
- [ ] Prices formatted per locale and bidi-isolated in RTL
- [ ] Order state machine lives on the server; app is read-only
- [ ] Interrupted-payment resume path implemented and tested
- [ ] COD modelled with zone limits and phone verification (if offered)
- [ ] Refund flow driven by webhook, partial refunds supported
- [ ] No custom card form anywhere; no card data logged
- [ ] Sandbox tested end to end, including a replayed webhook
- [ ] Server-generated receipt with sequential number and tax fields
