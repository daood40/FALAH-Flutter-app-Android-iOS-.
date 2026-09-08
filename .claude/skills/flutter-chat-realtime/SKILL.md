---
name: flutter-chat-realtime
description: Build a real-time chat or live feed between users in Flutter — conversation and message data model, Supabase realtime or Firestore snapshots, RTL message bubbles, optimistic send with delivery status, pagination, typing and presence, read receipts, attachments and push deep-linking. Use when building messaging between people (not an AI chatbot), or when the user says "دردشة", "محادثة", "رسائل", "شات", "chat", "messaging", "realtime".
---

# Realtime Chat Between Users

User-to-user messaging. For an AI assistant UI see `flutter-ai-integration` — the model and delivery guarantees there are different.

## Data model

```sql
create table conversations (
  id uuid primary key default gen_random_uuid(),
  is_group boolean default false, title text,
  last_message_text text, last_message_at timestamptz, last_sender_id uuid);

create table conversation_participants (
  conversation_id uuid references conversations on delete cascade,
  user_id uuid references auth.users on delete cascade,
  unread_count int default 0, last_read_at timestamptz, muted_until timestamptz,
  primary key (conversation_id, user_id));

create table messages (
  id uuid primary key,                    -- generated on the CLIENT
  conversation_id uuid references conversations on delete cascade,
  sender_id uuid references auth.users, body text,
  attachment_url text, attachment_type text,   -- image | file | audio
  duration_ms int,                             -- voice notes
  created_at timestamptz default now(), deleted_at timestamptz);
create index on messages (conversation_id, created_at desc);
```

- **`last_message_*` is denormalized onto the conversation.** The list screen must never fan out one query per row; update it in the same trigger that inserts the message.
- **Unread count is per participant** — incremented server-side for everyone but the sender, reset to 0 when that user opens the thread.
- **Message ids come from the client** (`const Uuid().v4()`) before sending. That is what makes retry idempotent: a resend with the same id is an upsert, not a duplicate.
- Firestore mirrors this: `conversations/{cid}` with a `messages/{mid}` subcollection, a `participantIds` array for `arrayContains` queries, and `participants/{uid}` docs for per-user unread state.
- RLS / security rules: read a conversation only if a participant row exists, insert only with `sender_id = auth.uid()`. Never expose `messages` without a membership check.

## Realtime: Supabase vs Firestore

| | Supabase | Firestore |
|---|---|---|
| New messages | `onPostgresChanges(insert, filter: conversation_id eq cid)` | `.orderBy('created_at', descending: true).limit(30).snapshots()` |
| Echo of own write | you add it to local state yourself | automatic, with `hasPendingWrites: true` |
| Offline send queue | you build it | built in (persistence on by default) |
| Typing / presence | broadcast + presence channel | no primitive — RTDB or a short-TTL doc |
| Cost driver | connections | document reads |

```dart
// Supabase
final channel = supabase.channel('conversation:$cid')
  ..onPostgresChanges(
    event: PostgresChangeEvent.insert, schema: 'public', table: 'messages',
    filter: PostgresChangeFilter(
        type: PostgresChangeFilterType.eq, column: 'conversation_id', value: cid),
    callback: (payload) => _onRemote(Message.fromJson(payload.newRecord)),
  )..subscribe();                            // dispose: supabase.removeChannel(channel)

// Firestore — includeMetadataChanges gives a free "sending" indicator
stream = FirebaseFirestore.instance.collection('conversations').doc(cid)
    .collection('messages').orderBy('created_at', descending: true).limit(30)
    .snapshots(includeMetadataChanges: true);   // d.metadata.hasPendingWrites
```

## Optimistic send and status

```dart
Future<void> send(String text) async {
  final msg = Message(
    id: const Uuid().v4(),           // reused verbatim on every retry
    conversationId: cid, senderId: myId, body: text,
    createdAt: DateTime.now(), status: MessageStatus.sending);
  state = [msg, ...state];           // appears instantly, before any network call
  try {
    await repo.send(msg);            // upsert on primary key id
    _setStatus(msg.id, MessageStatus.sent);
  } catch (_) { _setStatus(msg.id, MessageStatus.failed); }
}
```

`enum MessageStatus { sending, sent, delivered, read, failed }`, rendered only on your own bubbles at the `end` edge: clock, one check, two checks, two colored checks, and a tappable red "!" for `failed` that calls `send` again with the same object — same id, so the server upserts. When the realtime insert for your own message arrives, match by id and **replace** the pending row instead of appending, or every sent message flashes twice.

## Message list UI

```dart
ListView.builder(
  controller: _controller,
  reverse: true,                     // newest at index 0, opens at the bottom
  itemCount: items.length,
  itemBuilder: (context, i) {        // items = day headers + messages, built in the provider
    final item = items[i];
    if (item is DayHeader) return _DayChip(key: ValueKey('d${item.day}'), day: item.day);
    final m = item as Message;
    return MessageBubble(key: ValueKey(m.id), message: m, isMine: m.senderId == myId);
  })
```

`reverse: true` removes all scroll maths. Day labels: `اليوم` for today, `أمس` for yesterday, otherwise `DateFormat('d MMMM yyyy', 'ar').format(day)` — compare with `DateUtils.dateOnly`, not raw `DateTime`s.

RTL bubble — never `Alignment.centerLeft`, `EdgeInsets.only(left:)` or `BorderRadius.only`; only `BorderRadiusDirectional` flips the tail correctly in an Arabic locale:

```dart
Align(
  alignment: isMine ? AlignmentDirectional.centerEnd : AlignmentDirectional.centerStart,
  child: Container(
    margin: EdgeInsetsDirectional.only(start: isMine ? 64 : 8, end: isMine ? 8 : 64),
    constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.75),
    padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
    decoration: BoxDecoration(
      color: isMine ? cs.primaryContainer : cs.surfaceContainerHighest,
      borderRadius: BorderRadiusDirectional.only(   // flips automatically in RTL
        topStart: const Radius.circular(16), topEnd: const Radius.circular(16),
        bottomStart: Radius.circular(isMine ? 16 : 4),   // tail on the sender side
        bottomEnd: Radius.circular(isMine ? 4 : 16))),
    child: Text(m.body, textAlign: TextAlign.start)))
```

## Pagination of history

```dart
_controller.addListener(() {
  // reverse: true → maxScrollExtent is the OLDEST end
  final p = _controller.position;
  if (p.pixels >= p.maxScrollExtent - 300) ref.read(chatProvider(cid).notifier).loadOlder();
});
```

Page with a keyset cursor (`created_at < oldest.createdAt`, `id` as tiebreaker), never `offset` — an offset shifts as new messages arrive and silently skips rows. Because the list is reversed, appending older messages to its end does not move the viewport, so scroll position survives with no extra work. Guard with an `isLoadingOlder` flag so a fast flick does not fire five identical pages.

## Typing, presence, read receipts

Typing and presence are ephemeral state, never written to the database:

```dart
final channel = supabase.channel('presence:$cid')
  ..onBroadcast(event: 'typing', callback: (p) => _showTyping(p['user_id'] as String))
  ..onPresenceSync((_) => _online = channel.presenceState())
  ..subscribe((status, _) async {
    if (status == RealtimeSubscribeStatus.subscribed) await channel.track({'user_id': myId});
  });
// throttled to at most one every 2s while typing:
channel.sendBroadcastMessage(event: 'typing', payload: {'user_id': myId});
```

Clear the "يكتب الآن..." label on a local 3-second timer — a stop event can be lost, a timer cannot.

Read receipts: on opening the thread, and on each new message while it is visible, set `last_read_at = now()` and `unread_count = 0` on your participant row (debounced to once per second). The sender derives `read` by comparing the other participant's `last_read_at` to the message `created_at`. Do not store a per-message-per-recipient flag in group chats — that table grows as `messages × participants`.

## Attachments

Upload first, then insert the message referencing the URL; never put bytes in the message row.
- Pick with `image_picker` or `file_picker`, compress images (`flutter_image_compress`), then show an optimistic bubble using the **local file path** plus an upload progress indicator.
- Upload to `conversations/$cid/$messageId.jpg` so the object inherits the thread's access scope, then insert the message with `attachment_url` + `attachment_type` and swap the bubble to the remote URL.
- Voice notes: record to a temp file (`record` package) and store `duration_ms` at insert, so the waveform lays out before the audio downloads. A failed upload leaves the message `failed` with the local file on disk; retry re-uploads under the same message id.

## Push, muting, blocking

Send from a DB trigger or Cloud Function on insert, to every participant except the sender whose `muted_until` is null or past. The payload carries routing data, not just text:

```json
{ "notification": { "title": "أحمد", "body": "مرحبا" },
  "data": { "type": "chat", "conversation_id": "…", "message_id": "…" } }
```

Route the tap to `/chat/:id`, including `getInitialMessage()` for a killed app (see `flutter-notifications`), and suppress the local notification when the user is already inside that conversation. Muting must be checked server-side — a client-side mute still wakes the device. Blocking is a `blocked_users(blocker_id, blocked_id)` table enforced in the insert policy, so a blocked user's message never reaches the database; reporting writes a row holding the message id and a snapshot of the body, since the sender can delete the original. Both are app-store requirements for user-generated content.

## New message while scrolled up

```dart
final atBottom = _controller.position.pixels <= 80;   // reverse: true → 0 is newest
if (atBottom) {
  _controller.animateTo(0, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
} else {
  setState(() => _newCount++);                        // show the pill instead
}
```

Show a tappable pill above the input: `رسائل جديدة ($_newCount)`. Force-scrolling a user who is reading history is the fastest way to make a chat feel broken.

## Common mistakes

- Rebuilding the whole list per incoming message. Keep messages in an immutable list in a notifier, key every row with `ValueKey(m.id)`, keep `MessageBubble` a plain `StatelessWidget` so elements are reused.
- Server-generated ids: a retry after a timeout that actually succeeded creates a duplicate. Sorting by device `DateTime.now()` — clocks are wrong. Sort by the server timestamp; the local value is a placeholder until the insert returns.
- No `removeChannel` / snapshot cancel in `dispose` — one leaked socket per opened thread — or counting unread rows on every list build instead of reading the maintained counter.
- `Alignment` / `EdgeInsets` / `BorderRadius` instead of the `Directional` variants, mirroring the layout wrongly in Arabic.

## Checklist

- [ ] Client-generated message ids; send is an idempotent upsert
- [ ] `last_message_*` and `unread_count` maintained server-side
- [ ] Optimistic bubble with sending/sent/delivered/read/failed and a working retry
- [ ] Realtime echo replaces the pending row by id instead of appending
- [ ] `ListView(reverse: true)` with keyset pagination for older history
- [ ] Arabic day headers; all bubble geometry uses `*Directional`; typing/presence ephemeral
- [ ] Attachments uploaded before the message row is inserted
- [ ] Push payload carries `conversation_id`; tap deep-links from a killed app; mute honored server-side
- [ ] "رسائل جديدة" pill instead of force-scrolling; channels disposed; every row keyed
- [ ] Block and report implemented and enforced server-side
