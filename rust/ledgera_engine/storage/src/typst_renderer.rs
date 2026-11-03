use typst::diag::{FileError, FileResult};
use typst::foundations::{Bytes, Datetime, Duration};
use typst::syntax::{FileId, RootedPath, Source, VirtualPath, VirtualRoot};
use typst::text::{Font, FontBook};
use typst::utils::LazyHash;
use typst::{Library, LibraryExt, World};
use typst_layout::PagedDocument;

use super::{ReportResult, StorageResult, build_pdf_presentation_data, load_report_font};

const TEMPLATE: &str = include_str!("typst_statement.typ");

pub(super) fn render(report: &ReportResult, use_current: bool) -> StorageResult<Vec<u8>> {
    let presentation = build_pdf_presentation_data(report, use_current);
    let data = serde_json::to_string(&presentation)
        .map_err(|error| format!("failed to serialize Typst report data: {error}"))?;
    let font_data = load_report_font()?;
    let fonts = Font::iter(Bytes::new(font_data)).collect::<Vec<_>>();
    let font_family = fonts
        .first()
        .map(|font| font.info().family.to_string())
        .ok_or_else(|| "report font contains no readable faces".to_owned())?;
    let template = TEMPLATE.replace("__LEDGER_FONT_FAMILY__", &font_family);

    let main = virtual_file("statement.typ")?;
    let data_file = virtual_file("data.json")?;
    let world = TypstWorld {
        library: LazyHash::new(Library::default()),
        book: LazyHash::new(FontBook::from_fonts(&fonts)),
        main,
        source: Source::new(main, template),
        data_file,
        data: Bytes::from_string(data),
        fonts,
    };

    let compiled = typst::compile::<PagedDocument>(&world);
    let document = compiled
        .output
        .map_err(|errors| format!("Typst compilation failed: {errors:?}"))?;
    typst_pdf::pdf(&document, &typst_pdf::PdfOptions::default())
        .map_err(|errors| format!("Typst PDF export failed: {errors:?}").into())
}

fn virtual_file(path: &str) -> StorageResult<FileId> {
    let path = VirtualPath::new(path)
        .map_err(|error| format!("invalid Typst virtual path {path}: {error}"))?;
    Ok(RootedPath::new(VirtualRoot::Project, path).intern())
}

struct TypstWorld {
    library: LazyHash<Library>,
    book: LazyHash<FontBook>,
    main: FileId,
    source: Source,
    data_file: FileId,
    data: Bytes,
    fonts: Vec<Font>,
}

impl World for TypstWorld {
    fn library(&self) -> &LazyHash<Library> {
        &self.library
    }

    fn book(&self) -> &LazyHash<FontBook> {
        &self.book
    }

    fn main(&self) -> FileId {
        self.main
    }

    fn source(&self, id: FileId) -> FileResult<Source> {
        if id == self.main {
            Ok(self.source.clone())
        } else {
            Err(FileError::NotFound(id.vpath().get_with_slash().into()))
        }
    }

    fn file(&self, id: FileId) -> FileResult<Bytes> {
        if id == self.main {
            Ok(Bytes::from_string(self.source.text().to_owned()))
        } else if id == self.data_file {
            Ok(self.data.clone())
        } else {
            Err(FileError::NotFound(id.vpath().get_with_slash().into()))
        }
    }

    fn font(&self, index: usize) -> Option<Font> {
        self.fonts.get(index).cloned()
    }

    fn today(&self, _offset: Option<Duration>) -> Option<Datetime> {
        None
    }
}
