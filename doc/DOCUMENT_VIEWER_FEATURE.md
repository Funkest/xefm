# Documents as Text

XeFM's viewer shows **what a document says**: the text of PDF, Word, Excel,
PowerPoint, OpenDocument and EPUB files, with their headings, lists, tables,
pages, slides and sheets. You can search it, select and copy it, and wrap it
to the window, even when the file is on a server or inside an archive.

| Files | |
|---|---|
| PDF `.pdf` | the text of each page |
| Word `.docx`, OpenDocument `.odt` | headings, paragraphs, lists, tables, and page headers and footers |
| Excel `.xlsx`, OpenDocument `.ods` | one table per sheet |
| PowerPoint `.pptx`, OpenDocument `.odp` | one section per slide, with its title, bullets, tables and **speaker notes** |
| EPUB `.epub` | one section per chapter |

The old Office formats (`.doc`, `.xls`, `.ppt`) are not read. They open in
their applications as before.

## Opening one

`Enter` or `V` on the file opens it in the viewer. A large or remote
document first shows a progress dialog while it is read. `Esc` stops the
reading.

The viewer has two modes, as for Markdown files. `M` switches between them,
and XeFM remembers your choice for each kind of file:

- **Rendered** (the first time): headings, lists, tables, and a heading for
  each page, slide, sheet or chapter.
- **Text**: the plain text, line by line, as search sees it.

Search (`F`), selection and copy work in both. The header names the document
kind and its size, for example "PowerPoint · 12 slides".

## What you see, and what you don't

The viewer shows the text, not the page. Layout, fonts, pictures and charts
are not drawn. To see what a document looks like, open it in its application
with `Ctrl-O` (`Cmd-Enter` on macOS).

- **A scanned PDF** has no text, only a picture of each page. The viewer says
  so instead of showing an empty page. XeFM does no OCR.
- **A password-protected PDF** isn't opened. The viewer says so, and the
  application can open it.
- **A PDF** gives the text of each page in reading order. A PDF does not
  record headings or tables as such, so none are shown.
- **Spreadsheet cells** show the values they hold. A date shows as the number
  Excel stores for it.

## Searching inside documents

**Search Content** (`Shift-G`) reads these documents through the same text,
so a word in a PDF or a slide deck is found like a word in a text file. Each
hit shows its line of the extracted text.

## If V still opens Preview or Word

XeFM's shipped configuration sends `V` on these files to the built-in viewer.
A `config.py` created before this feature still says otherwise, and it
wins. Change the `'view'` of the PDF and Office entries in
`FILE_ASSOCIATIONS` to `None`:

```python
{
    'pattern': '*.pdf',
    'open': ['open', '-a', 'Preview'],
    'view': None,           # V: XeFM's own viewer
    'edit': None,
},
```

`Enter` already uses the built-in viewer, whatever `'view'` says.

## Requirements

Reading documents uses [doc-files](https://github.com/crftwr/doc-files),
with [pypdf](https://pypi.org/project/pypdf/) for PDF. Both come with XeFM.
