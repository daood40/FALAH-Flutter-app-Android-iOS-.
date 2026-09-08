---
name: flutter-search-filter
description: Search and filtering in Flutter — Arabic text normalization, debounced input, server-side search with Postgres/Supabase or Firestore, filter state with chips and bottom sheets, pagination, recent searches, and match highlighting. Use when adding a search field, filters, or sorting, or when the user says "بحث", "فلترة", "تصفية", "ترتيب", "search", "filter", "sort".
---

# Search & Filter

## Arabic normalization and local search

Arabic search fails without it: the user types `احمد` and the row holds `أحمد`, or the row carries tashkeel, or the user typed `٢٠٢٤` and the data holds `2024`. Normalize both sides — index and query.

```dart
final _diacritics = RegExp(r'[ً-ْٰـ]');   // harakat, dagger alif, tatweel
const _fold = {0x0623: 0x0627, 0x0625: 0x0627, 0x0622: 0x0627, 0x0671: 0x0627, // أ إ آ ٱ → ا
               0x0629: 0x0647, 0x0649: 0x064A, 0x0626: 0x064A, 0x0624: 0x0648}; // ة→ه ى ئ→ي ؤ→و
String normalizeArabic(String input) {
  final buf = StringBuffer();
  for (final rune in input.toLowerCase().runes) {
    var c = _fold[rune] ?? rune;
    if (c >= 0x0660 && c <= 0x0669) c -= 0x0660 - 0x30;   // ٠-٩ → 0-9
    if (c >= 0x06F0 && c <= 0x06F9) c -= 0x06F0 - 0x30;   // ۰-۹ → 0-9 (Persian)
    buf.writeCharCode(c);
  }
  return buf.toString().replaceAll(_diacritics, '').replaceAll(RegExp(r'\s+'), ' ').trim();
}
```

Precompute this into a `searchText` field at write time; never call it inside a filter callback, which runs per item per keystroke. `ة→ه` and `ى→ي` deliberately lose information so `فاطمه` matches `فاطمة` — never store the result back as the displayed value.

In-memory filtering is fine up to a few thousand loaded items; anything larger or paginated belongs on the server.

```dart
List<Item> filter(List<Item> items, String query) {
  final terms = normalizeArabic(query).split(' ')..removeWhere((t) => t.isEmpty);
  return terms.isEmpty ? items
      : items.where((i) => terms.every((t) => i.searchText.contains(t))).toList();
}
```

Splitting on spaces and requiring every term is what makes `احمد بنغازي` work regardless of word order. A single `contains(q)` on the whole phrase is the #1 reason "search doesn't find anything".

## Debouncing and cancellation

Fire on a pause, not a keystroke — ~350ms. Below 200ms you hammer the backend; above 500ms it feels broken. A `Debouncer` is a `Timer?` field with `void run(VoidCallback a) { _timer?.cancel(); _timer = Timer(delay, a); }` plus a `dispose` that cancels it; keep one per search field and dispose it with the widget.

Debouncing alone is not enough: two requests can still be in flight and land out of order, so a slow old response overwrites a newer one. Guard every async search with a sequence token:

```dart
int _seq = 0;
Future<void> search(String query) async {
  final mine = ++_seq;
  final results = await repo.search(query);
  if (mine != _seq) return;              // superseded by a newer search
  state = state.copyWith(loading: false, results: results);
}
```

With Dio, also cancel the previous `CancelToken` and treat `DioExceptionType.cancel` as a no-op — a cancelled request is not an error and must never surface an error state. Dispose the `TextEditingController` too, and skip all work while the query is empty.

## Server-side search: Postgres / Supabase

| Need | Approach |
|---|---|
| Substring, small tables | `.ilike('title', '%$q%')` |
| Several columns | `.or('title.ilike.*$q*,body.ilike.*$q*')` |
| Ranked word search | `.textSearch('fts', q, config: 'arabic', type: TextSearchType.websearch)` |
| Typo tolerance | `pg_trgm` similarity, through an RPC |

Always finish the query with `.order(...)` and `.range(page * size, page * size + size - 1)` — paginate on the server, never by trimming a full result set in Dart. Inside `.or()` PostgREST uses `*` as the wildcard, and a comma or parenthesis in user input breaks the filter grammar, so strip `,()%*` before interpolating. `.ilike('%q%')` cannot use a b-tree index and degrades badly on large tables; that is what the other two rows are for.

**The `arabic` config caveat.** Postgres ships an `arabic` snowball configuration (PG 11+), but it only stems — it does **not** fold `أ/إ/آ → ا`, strip tashkeel, or convert Arabic-Indic digits, and `unaccent` targets Latin diacritics and does not help. So `أحمد` and `احمد` stay different lexemes and the search still misses. Normalize in the database with an `IMMUTABLE` function, index the normalized column, and run `select ar_norm('أحـمَد ٢٠٢٤');` first to confirm the character classes behave on your server version:

```sql
create extension if not exists pg_trgm;
create or replace function ar_norm(t text) returns text
language sql immutable strict parallel safe as $$
  select regexp_replace(
           translate(lower(t), 'أإآٱةىؤئ٠١٢٣٤٥٦٧٨٩', 'ااااهيوي0123456789'),
           '[ًٌٍَُِّْٰـ]', '', 'g');
$$;
alter table items add column search_norm text  -- one indexed, already-normalized column
  generated always as (ar_norm(coalesce(title,'') || ' ' || coalesce(body,''))) stored;
create index items_search_trgm on items using gin (search_norm gin_trgm_ops);
```

Keep `normalizeArabic` and `ar_norm` in agreement — if they drift, queries silently stop matching. For fuzzy ranking expose an RPC (`similarity(search_norm, ar_norm($1)) > 0.25 order by similarity desc`) and call `supabase.rpc(...)`; PostgREST filters cannot express similarity ordering. **Firestore** has no equivalent — there is **no substring search**. `isGreaterThanOrEqualTo: q` with `isLessThan: '$q'` is prefix-only, case- and diacritic-sensitive, and unusable in Arabic without a normalized field; a `keywords` array with `arrayContainsAny` matches whole words only, caps at 30 values per query, and inflates every document. For anything a user would call "search", mirror the collection into **Algolia** or **Typesense** (both have official Firebase extensions) and query that.

## Filter state, sorting, pagination

One immutable object holds query, filters, sort, and page; every control produces a new instance via `copyWith`.

```dart
enum SortBy { newest, oldest, priceAsc, priceDesc }
class SearchFilters {
  const SearchFilters({this.query = '', this.categories = const {}, this.minPrice,
      this.maxPrice, this.sort = SortBy.newest, this.page = 0});
  final String query;
  final Set<String> categories;
  final double? minPrice, maxPrice;
  final SortBy sort;
  final int page;
  bool get isFiltered =>
      categories.isNotEmpty || minPrice != null || maxPrice != null || sort != SortBy.newest;
  int get activeCount => categories.length + (minPrice != null || maxPrice != null ? 1 : 0);
  SearchFilters copyWith({String? query, Set<String>? categories, double? minPrice,
          double? maxPrice, bool clearPrice = false, SortBy? sort, int? page}) =>
      SearchFilters(query: query ?? this.query, categories: categories ?? this.categories,
          minPrice: clearPrice ? null : (minPrice ?? this.minPrice),
          maxPrice: clearPrice ? null : (maxPrice ?? this.maxPrice),
          sort: sort ?? this.sort, page: page ?? this.page);
}
```

`copyWith` cannot clear a nullable field — `minPrice: null` means "keep it", which is why `clearPrice` exists; without such a flag "remove the price filter" silently does nothing. Give the class value equality (`freezed`, `equatable`, or a hand-written `==`); the pagination below depends on it.

**Any change to query, filters, or sort resets `page` to 0 and clears the accumulated list.** Appending page 2 of the new filter onto page 1 of the old one is the most common bug in this whole area.

```dart
Future<void> apply(SearchFilters next) async {
  final reset = next.copyWith(page: state.filters.page) != state.filters; // value equality!
  state = state.copyWith(filters: reset ? next.copyWith(page: 0) : next,
      items: reset ? const [] : state.items, hasMore: true);   // never append across filters
  await _load();
}
```

With default identity equality that comparison is always true and every call resets. Sort on the server too: sorting only the loaded page reorders 20 rows out of 200 and looks random.

## Chips, the filter sheet, and recents

```dart
Wrap(spacing: 8, children: [
  for (final c in f.categories)
    InputChip(label: Text(c),
        onDeleted: () => apply(f.copyWith(categories: {...f.categories}..remove(c)))),
  if (f.minPrice != null || f.maxPrice != null)
    InputChip(label: Text('السعر: ${f.minPrice ?? 0} - ${f.maxPrice ?? '∞'}'),
        onDeleted: () => apply(f.copyWith(clearPrice: true))),
  if (f.isFiltered)
    ActionChip(label: const Text('مسح الكل'), onPressed: () => apply(const SearchFilters())),
])   // each chip clears exactly its own filter; "مسح الكل" resets everything
```

Open the sheet with `showModalBottomSheet<SearchFilters>(isScrollControlled: true, useSafeArea: true, ...)` and call `apply` only on a non-null result. The sheet edits a **draft** copy — mutating live state as the user taps re-runs the query on every tap and makes cancel impossible. Give it a scrollable body and a pinned bottom row: `TextButton('إعادة تعيين')` returning `const SearchFilters()`, `FilledButton('تطبيق (${draft.activeCount})')` returning the draft. `isScrollControlled` with `useSafeArea` keeps those buttons above the keyboard and gesture bar; put `activeCount` in a `Badge` on the toolbar so filtered state is visible without opening the sheet. Persist the last ~8 queries with `SharedPreferences.setStringList('recent_searches', ...)`: trim the query, ignore anything under 2 characters, de-duplicate by comparing `normalizeArabic` of each entry, insert at index 0, `take(8)`. Save on submit or result-tap, never per keystroke, and always offer a clear action — recent searches are user data and can be sensitive.

## SearchAnchor and the empty state

```dart
SearchAnchor.bar(
  barHintText: 'ابحث عن منتج',
  suggestionsBuilder: (context, controller) async {
    final q = controller.text;
    if (q.isEmpty) return recent.map((r) => ListTile(leading: const Icon(Icons.history),
        title: Text(r), onTap: () => controller.closeView(r)));
    return (await repo.suggest(q)).map((i) => ListTile(
        title: Text.rich(highlight(i.title, q, null, cs)),
        onTap: () => controller.closeView(i.title)));
  },
)
```

`suggestionsBuilder` runs on every keystroke — debounce and cache inside the repository. `closeView(text)` both closes the overlay and sets the bar text; popping the route yourself leaves the controller inconsistent. The empty state is never a bare `'لا توجد نتائج'`: name what was searched and offer the next action — an icon, `Text('لا توجد نتائج لـ "$query"')`, a hint such as `'جرّب كلمات أقل أو تحقق من الإملاء'`, and, when `filters.isFiltered`, a button reading `'مسح الفلاتر (${filters.activeCount})'`, because the filters are usually what killed the results, not the spelling. Distinguish it from "nothing here yet": a first-run empty list needs a create action, not search advice.

## Highlighting matches

The trap: you match on the normalized string but paint on the original, and because normalization strips tashkeel the two have different lengths — so the highlight lands on the wrong characters. Build an index map as you normalize, render with `Text.rich`, mark the match with weight **and** background rather than color alone, and bound the query length (~60 chars) to keep this cheap in a long list.

```dart
TextSpan highlight(String original, String query, TextStyle? base, ColorScheme cs) {
  final q = normalizeArabic(query);
  final buf = StringBuffer(); final map = <int>[];   // map: normalized index → original index
  for (var i = 0; i < original.length; i++) {
    final n = normalizeArabic(original[i]);            // '' for a stripped harakah
    buf.write(n);
    for (var k = 0; k < n.length; k++) map.add(i);
  }
  final at = q.isEmpty ? -1 : buf.toString().indexOf(q);
  if (at < 0) return TextSpan(text: original, style: base);
  final start = map[at], end = at + q.length < map.length ? map[at + q.length] : original.length;
  return TextSpan(style: base, children: [
    TextSpan(text: original.substring(0, start)),
    TextSpan(text: original.substring(start, end),
        style: TextStyle(fontWeight: FontWeight.w700, backgroundColor: cs.primaryContainer)),
    TextSpan(text: original.substring(end)),
  ]);
}
```

## Checklist

- [ ] `normalizeArabic` applied to the stored field and the query, mirrored in SQL, precomputed at write time
- [ ] Multi-term AND matching, not a single phrase `contains`
- [ ] Input debounced ~350ms; stale responses discarded by sequence token, cancels not shown as errors
- [ ] User input escaped before it reaches an `.or()` / `ilike` filter
- [ ] Server-side normalized column indexed (trigram or tsvector); paging and sorting on the server
- [ ] Page reset to 0 and list cleared on any query/filter/sort change (`SearchFilters` needs value equality)
- [ ] Every active filter is an individually removable chip; the sheet edits a draft
- [ ] Empty state names the query and offers a next step (usually: clear the filters)
- [ ] Highlight ranges mapped back to original indices
- [ ] Controllers, timers, and tokens disposed
