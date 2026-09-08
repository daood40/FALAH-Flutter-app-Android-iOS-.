---
name: flutter-ai-integration
description: Add AI to a Flutter app — calling LLM APIs (Claude, OpenAI, Gemini) safely through a backend proxy, streaming responses, chat UI, function/tool calling, RAG with embeddings and pgvector, on-device ML (google_mlkit, tflite), speech and image features, and cost control. Use when the user says "ذكاء اصطناعي", "شات بوت", "AI", "chatbot", "LLM", "embeddings", "RAG", "تحويل الصوت لنص".
---

# AI in Flutter Apps

## Rule zero: never put an API key in the app

A Flutter binary is decompilable and Flutter Web ships the key in plain JavaScript. Every LLM call goes through a server you control — a Supabase Edge Function, Cloud Function, or your own endpoint — which holds the key, enforces auth, and rate-limits per user. Without this, one leaked key means an unbounded bill.

```ts
// supabase/functions/chat/index.ts
import Anthropic from 'npm:@anthropic-ai/sdk';

Deno.serve(async (req) => {
  const auth = req.headers.get('Authorization');
  if (!auth) return new Response('unauthorized', { status: 401 });
  // verify the Supabase JWT, look up the user, check their quota here

  const { messages } = await req.json();
  const client = new Anthropic({ apiKey: Deno.env.get('ANTHROPIC_API_KEY')! });

  const stream = await client.messages.stream({
    model: 'claude-sonnet-4-5',
    max_tokens: 1024,
    system: 'أنت مساعد يجيب بالعربية الفصحى بإيجاز.',
    messages,
  });

  return new Response(stream.toReadableStream(), {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
  });
});
```

```bash
supabase secrets set ANTHROPIC_API_KEY=sk-...
supabase functions deploy chat
```

## Streaming into the UI

Streaming is what makes an AI feature feel fast. Do not wait for the full response.

```dart
Stream<String> chatStream(List<Msg> history) async* {
  final req = http.Request('POST', Uri.parse('$base/functions/v1/chat'))
    ..headers.addAll({
      'Authorization': 'Bearer ${supabase.auth.currentSession!.accessToken}',
      'Content-Type': 'application/json',
    })
    ..body = jsonEncode({'messages': history.map((m) => m.toJson()).toList()});

  final res = await req.send();
  if (res.statusCode != 200) throw AppException('تعذّر الاتصال بالمساعد');

  await for (final line in res.stream
      .transform(utf8.decoder)
      .transform(const LineSplitter())) {
    if (!line.startsWith('data: ')) continue;
    final payload = line.substring(6);
    if (payload == '[DONE]') break;
    final json = jsonDecode(payload);
    final delta = json['delta']?['text'] as String?;
    if (delta != null) yield delta;
  }
}
```

```dart
class ChatController extends AsyncNotifier<List<Msg>> {
  StreamSubscription? _sub;

  Future<void> send(String text) async {
    final msgs = [...state.value!, Msg.user(text), Msg.assistant('')];
    state = AsyncData(msgs);

    final buffer = StringBuffer();
    _sub = chatStream(msgs.sublist(0, msgs.length - 1)).listen(
      (chunk) {
        buffer.write(chunk);
        state = AsyncData([...msgs]..last = Msg.assistant(buffer.toString()));
      },
      onError: (e) => state = AsyncError(e, StackTrace.current),
    );
  }

  void stop() => _sub?.cancel();   // always give the user a stop button
}
```

Chat UI details that matter: `reverse: true` on the `ListView` so new messages appear at the bottom without manual scrolling; a typing indicator before the first token; a stop button; markdown rendering (`flutter_markdown`) with code blocks; long-press to copy; and `Directionality` detection per message when the app mixes Arabic and English.

## Reliability

- **Timeouts**: LLM calls take 5–60 s. Set `receiveTimeout` accordingly, not the 20 s you use elsewhere.
- **Retry** only on 429/5xx with backoff; honour `Retry-After`.
- **Truncate history**: send the last N turns plus a rolling summary, not the whole conversation — cost and latency grow with every message.
- **Never trust the output shape.** If you need JSON, ask for JSON, then parse defensively and re-prompt or fall back on parse failure.

```dart
Map<String, dynamic>? tryJson(String s) {
  final m = RegExp(r'\{[\s\S]*\}').firstMatch(s);
  if (m == null) return null;
  try { return jsonDecode(m.group(0)!) as Map<String, dynamic>; } catch (_) { return null; }
}
```

## Tool / function calling

Define tools on the server, execute them on the server, and return only the final text to the app. Executing model-chosen actions on the client means a prompt injection can drive your app. Anything destructive (delete, pay, send) requires an explicit user confirmation in the UI, not model discretion.

## RAG (search your own content)

1. Chunk documents (~500–1000 tokens, 10–15% overlap) on the server.
2. Embed each chunk, store in Postgres with `pgvector`.
3. At query time embed the question, retrieve top-k, put chunks in the prompt, cite sources.

```sql
create extension if not exists vector;

create table docs (
  id bigserial primary key,
  content text,
  metadata jsonb,
  embedding vector(1536)
);

create index on docs using hnsw (embedding vector_cosine_ops);

create function match_docs(query_embedding vector(1536), match_count int default 5)
returns table (id bigint, content text, similarity float)
language sql stable as $$
  select id, content, 1 - (embedding <=> query_embedding)
  from docs order by embedding <=> query_embedding limit match_count;
$$;
```

Always show the user which sources the answer came from. Answers with no retrieved context should say "لا أعرف" rather than being generated freely.

## On-device (no network, no cost, private)

```bash
flutter pub add google_mlkit_text_recognition google_mlkit_barcode_scanning
```

- **OCR**: `TextRecognizer(script: TextRecognitionScript.latin)` — note ML Kit's Arabic script support is limited; test with real Arabic documents before promising it.
- **Barcode/QR**, face detection, image labeling: all offline via ML Kit.
- **Custom model**: `tflite_flutter` + a quantized `.tflite`. Run inference in an `Isolate` — a 200 ms inference on the UI thread is 12 dropped frames.
- **Speech to text**: `speech_to_text` (on-device, free, needs mic permission) or a server Whisper call for higher accuracy on Arabic dialects.
- **Text to speech**: `flutter_tts`, set `setLanguage('ar-SA')`.

## Cost control (do this before launch, not after)

- Per-user daily quota enforced **on the server**, stored in Postgres, checked before the model call.
- Cache identical prompts (hash the prompt → store the response).
- Use a smaller/cheaper model for classification and routing; reserve the large model for generation.
- Cap `max_tokens` on every call.
- Log tokens-in / tokens-out per request so you can see cost per feature.

## UX and safety

- Label AI output as AI-generated.
- Show a friendly, localized message on failure — never a raw API error.
- Give the user a way to report a bad answer.
- Do not send personal data to a third-party model without disclosing it in your privacy policy; app stores ask about this.
- Moderate user input before sending if the app is public-facing.
