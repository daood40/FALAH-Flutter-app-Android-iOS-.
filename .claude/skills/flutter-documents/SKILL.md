---
name: flutter-documents
description: Generating and handling documents in Flutter — PDF creation with the pdf and printing packages, Arabic text in PDFs, printing and sharing, in-app PDF viewing, Excel and CSV export/import, QR codes on documents, and large-document performance. Use when the app produces reports, invoices or exports, or when the user says "تقرير", "فاتورة", "طباعة", "تصدير", "ملف", "إكسل", "PDF", "report", "invoice", "export", "print".
---

# Documents: PDF, Excel, CSV

`pdf` builds the document (pure Dart, works in an isolate), `printing` shows it, prints it and shares it. They are by the same author and versioned together — upgrade both at once.

## Page layout

```dart
final doc = pw.Document();
doc.addPage(pw.MultiPage(
  maxPages: 200,                                  // default guard is 20
  pageTheme: pw.PageTheme(
    pageFormat: PdfPageFormat.a4.copyWith(marginTop: 32, marginBottom: 40),
    theme: pw.ThemeData.withFont(base: arabicRegular, bold: arabicBold),
    textDirection: pw.TextDirection.rtl,
  ),
  header: (ctx) => pw.Container(
    alignment: pw.Alignment.centerRight,
    margin: const pw.EdgeInsets.only(bottom: 12),
    child: pw.Text('تقرير المبيعات',
        style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold)),
  ),
  footer: (ctx) => pw.Center(
    child: pw.Text('صفحة ${ctx.pageNumber} من ${ctx.pagesCount}',
        style: const pw.TextStyle(fontSize: 9, color: PdfColors.grey600)),
  ),
  build: (ctx) => [
    pw.TableHelper.fromTextArray(
      headers: ['المنتج', 'الكمية', 'السعر'],
      data: rows.map((r) => [r.name, '${r.qty}', r.price.toStringAsFixed(2)]).toList(),
      headerDecoration: const pw.BoxDecoration(color: PdfColors.grey200),
      cellAlignment: pw.Alignment.centerRight,
    ),
    pw.SizedBox(height: 16),
    pw.Text('الإجمالي: ${total.toStringAsFixed(2)} ر.س'),
  ],
));
final bytes = await doc.save();   // Uint8List
```

`pw.MultiPage` is the only widget that paginates; `pw.Page` renders one fixed page and silently clips or throws on overflow. Its `maxPages` guard defaults to 20 and throws `TooManyPagesException` — raise it for long reports. `build:` returns a `List<pw.Widget>` whose elements each break across pages; a single tall `pw.Column` inside that list cannot break, so put row widgets directly in the list.

## Arabic text in PDFs

This is the hardest part of the package and where most time is lost. Three things must all be true.

**1. A real Arabic TTF, loaded from assets.** The package embeds no fonts with Arabic glyphs; the built-in Helvetica renders Arabic as blanks or tofu.

```dart
final arabicRegular = pw.Font.ttf(await rootBundle.load('assets/fonts/Cairo-Regular.ttf'));
final arabicBold    = pw.Font.ttf(await rootBundle.load('assets/fonts/Cairo-Bold.ttf'));
```

Use a **static** TTF. Variable fonts and OTF/CFF files fail or render wrong — download the static weights from Google Fonts, not the variable file. Declare them under `fonts:` in `pubspec.yaml` (or just `assets:` — the PDF path only needs `rootBundle`).

**2. RTL direction.** Set `textDirection: pw.TextDirection.rtl` on the `PageTheme` so it applies document-wide, and wrap any mixed sub-tree in `pw.Directionality(textDirection: pw.TextDirection.rtl, child: ...)`. Without it, punctuation and digits jump to the wrong end.

**3. Verify the actual output, every time.** Arabic needs bidi reordering *and* contextual shaping (each letter has isolated/initial/medial/final forms plus lam-alef ligatures). Support for this has changed across pdf versions and it is still the weak spot. Open the generated file and check for: letters printed disconnected, reversed word order, a broken لا ligature, and Arabic-Indic vs Western digits. Do not assume it works because it compiled.

If shaping is wrong on the version you are pinned to, two fallbacks, in order of preference:

- **HTML → PDF.** `Printing.convertHtml(html: html, format: PdfPageFormat.a4)` renders through the platform webview, which has a full text engine and shapes Arabic correctly. Set `<html dir="rtl">` and a `font-family` that exists on the device, or inline the font as base64 in `@font-face`. Cost: no offline determinism, and it is unavailable on some desktop targets.
- **Render the page as an image.** Lay the page out as a Flutter widget, capture it via `RepaintBoundary` → `boundary.toImage(pixelRatio: 3)` → PNG bytes, then embed with `pw.Image(pw.MemoryImage(bytes))` sized to the page. Flutter's own text engine shapes Arabic perfectly. Cost: text is no longer selectable or searchable and the file is much larger — reserve it for one Arabic-heavy page (a certificate, a cover), not a 40-page report.

Keep numbers and Latin identifiers (invoice numbers, emails, IBANs) in their own `pw.Text` with `textDirection: pw.TextDirection.ltr` so bidi cannot reorder them.

## Print, share, preview

```dart
await Printing.layoutPdf(onLayout: (format) async => doc.save());     // system print dialog
await Printing.sharePdf(bytes: bytes, filename: 'فاتورة-1024.pdf');   // system share sheet
final info = await Printing.info();                                   // canPrint / canShare
// In-app preview, print and share buttons already wired:
Scaffold(body: PdfPreview(build: (format) => doc.save(), canDebug: false));
```

`Printing.sharePdf` writes to a temp file and hands the OS a content URI. Never build your own `file://` path and pass it to another app — Android blocks it with `FileUriExposedException`.

## Viewing PDFs in-app

```dart
SfPdfViewer.file(File(path), controller: _pdfController, canShowScrollHead: true)
```

`syncfusion_flutter_pdfviewer` is the most complete (text selection, search via `PdfViewerController.searchText`, bookmarks, form fields) but is commercially licensed — the free community license has revenue/headcount limits, so check eligibility before shipping. `pdfx` and the actively maintained `pdfrx` are permissively licensed, lighter alternatives with weaker text search. For a remote PDF, download to the documents directory first and open the local file; streaming a URL re-downloads on every page jump.

## Excel and CSV export

```dart
final excel = Excel.createExcel();
final sheet = excel['التقرير'];
excel.setDefaultSheet('التقرير');
sheet.appendRow([TextCellValue('المنتج'), TextCellValue('الكمية'), TextCellValue('السعر')]);
for (final r in rows) {
  sheet.appendRow([TextCellValue(r.name), IntCellValue(r.qty), DoubleCellValue(r.price)]);
}
sheet.cell(CellIndex.indexByString('A1')).cellStyle =
    CellStyle(bold: true, horizontalAlign: HorizontalAlign.Right);
final bytes = excel.encode();   // List<int>?
```

Typed cell values (`TextCellValue` / `IntCellValue` / `DoubleCellValue` / `DateCellValue`) are required by `excel` ^4.x; passing raw `String`/`int` is the old ^2.x API and will not compile. Write numbers as numeric cells, never strings — otherwise Excel cannot sum the column. CSV is smaller and faster, but Arabic breaks without a byte-order mark:

```dart
final csv = const ListToCsvConverter(eol: '\r\n').convert([
  ['المنتج', 'الكمية', 'السعر'],
  ...rows.map((r) => [r.name, r.qty, r.price]),
]);
final bytes = <int>[0xEF, 0xBB, 0xBF, ...utf8.encode(csv)];  // UTF-8 BOM
await file.writeAsBytes(bytes, flush: true);
```

Without the BOM, Excel on Windows opens the file in the system ANSI code page and every Arabic string becomes mojibake. Also note that Excel splits on the locale's list separator: on many Arabic/European Windows locales that is `;`, not `,`. Either export with `fieldDelimiter: ';'` for those users, or ship `.xlsx` and avoid the problem.

## Importing CSV

```dart
final result = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['csv']);
var text = utf8.decode(await File(result!.files.single.path!).readAsBytes());
if (text.startsWith('﻿')) text = text.substring(1);       // strip an incoming BOM
final rows = const CsvToListConverter(shouldParseNumbers: false).convert(text);
final header = rows.first.cast<String>();
final data = rows.skip(1);
```

Always strip the BOM, always validate the header row against what you expect, and never trust the column order. Report bad rows by line number instead of aborting the whole import.

## QR / barcode on a document

The `pdf` package ships barcode widgets, so there is no image-generation step:

```dart
pw.BarcodeWidget(barcode: pw.Barcode.qrCode(),
    data: 'https://example.com/invoice/1024', width: 90, height: 90)
```

`pw.Barcode.code128()`, `.ean13()` and the rest come off the same factory. For a QR inside the app UI rather than the PDF, use `qr_flutter`.

## File naming and where to save

```dart
final dir = await getApplicationDocumentsDirectory();
final stamp = DateFormat('yyyy-MM-dd_HH-mm').format(DateTime.now());
final file = File('${dir.path}/exports/invoice_1024_$stamp.pdf');
await file.parent.create(recursive: true);
await file.writeAsBytes(bytes, flush: true);
await Share.shareXFiles([XFile(file.path, mimeType: 'application/pdf')], subject: 'فاتورة');
```

- Save to `getApplicationDocumentsDirectory()` (path_provider) for anything the user keeps; `getTemporaryDirectory()` only for a file you are about to share and forget.
- Keep the **filename** ASCII and free of `/ \ : * ? " < > |` and spaces — an Arabic display title belongs in the share `subject` or in the PDF's own header, not in the path. Some mail clients and cloud drives mangle non-ASCII filenames.
- Never show a raw filesystem path to the user or ask them to "find it in /data/...". Hand the file to the system Share sheet or `Printing.sharePdf` and let the OS place it. Note that `share_plus` ≥ 11 replaces `Share.shareXFiles(...)` with `SharePlus.instance.share(ShareParams(files: [...]))` — check the installed major version.

## Large documents and performance

`doc.save()` is CPU-bound pure Dart, so it blocks the UI thread. Move it to an isolate — but load fonts and images **before** the jump, because `rootBundle` is not available off the root isolate without extra setup.

```dart
final fontBytes = (await rootBundle.load('assets/fonts/Cairo-Regular.ttf')).buffer.asUint8List();
final logoBytes = (await rootBundle.load('assets/logo.png')).buffer.asUint8List();
final pdfBytes = await compute(_buildReport, (rows: rows, font: fontBytes, logo: logoBytes));

Future<Uint8List> _buildReport(({List<Row> rows, Uint8List font, Uint8List logo}) a) async {
  final doc = pw.Document();
  final font = pw.Font.ttf(ByteData.sublistView(a.font));
  final logo = pw.MemoryImage(a.logo);
  // ... doc.addPage(pw.MultiPage(...))
  return doc.save();          // Future<Uint8List>, pure Dart, safe off the root isolate
}
```

- Downscale every image to the size it is drawn at before embedding. A 4000×3000 photo in a 200 pt box still stores all its pixels; 50 of them make a 90 MB PDF.
- Reuse one `pw.MemoryImage` for a repeated logo — creating it per page embeds it per page.
- Build in chunks of rows rather than loading 100k records into memory first. Above a few hundred pages, generate server-side; mobile devices will OOM.
- Show determinate progress and let the user cancel; never a bare spinner on a 30-second export.

## Common mistakes

- Using the default font and shipping a PDF full of blank boxes where Arabic should be.
- Setting `textDirection` on a single `pw.Text` instead of the `PageTheme`, so headers and tables stay LTR.
- Using `pw.Page` for a report and losing every row past the first page.
- Hitting `TooManyPagesException` and lowering the row count instead of raising `maxPages`.
- Calling `Table.fromTextArray` — it moved to `pw.TableHelper.fromTextArray`.
- Exporting CSV without a BOM, then blaming Excel.
- Building the PDF on the UI thread and shipping a 4-second freeze, or sharing a raw `file://` path instead of going through `share_plus` / `Printing.sharePdf`.

## Checklist

- [ ] Arabic TTF (static, not variable) bundled and loaded via `pw.Font.ttf`
- [ ] `textDirection: pw.TextDirection.rtl` set on the `PageTheme`
- [ ] Generated PDF opened and visually verified for shaping, ligatures and digit order
- [ ] Fallback decided (HTML→PDF or image page) if shaping is broken on the pinned version
- [ ] `pw.MultiPage` used, with `maxPages` raised for long reports
- [ ] Page numbers and header on every page
- [ ] CSV written with a UTF-8 BOM; `.xlsx` uses typed numeric cells
- [ ] CSV import strips the BOM and validates the header row
- [ ] Files saved to the documents directory with ASCII names, delivered via the Share sheet
- [ ] Generation runs in an isolate, with progress and cancel; images downscaled first
