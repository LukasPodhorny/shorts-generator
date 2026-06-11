from markitdown import MarkItDown, UnsupportedFormatException

_markitdown = MarkItDown(enable_plugins=False)


def extract_text(path: str) -> str:
    """Convert a document (pdf, docx, pptx, html, txt, md, ...) to Markdown."""
    try:
        result = _markitdown.convert(path)
    except UnsupportedFormatException as e:
        raise ValueError(f"Unsupported file type: {path}") from e
    return result.markdown
