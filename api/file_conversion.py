import asyncio
import os
import shutil
import tempfile
import uuid

OFFICE_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".ods", ".odp", ".rtf"}


class ConversionError(RuntimeError):
    pass


async def convert_office_to_pdf(input_bytes: bytes, filename: str) -> bytes:
    """Convert an office document to PDF using headless LibreOffice.

    Returns the PDF file's bytes. Raises ConversionError on failure.
    """
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ConversionError("LibreOffice (soffice) is not installed on the server")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in OFFICE_EXTENSIONS:
        raise ConversionError(f"Unsupported office extension: {ext}")

    work_dir = tempfile.mkdtemp(prefix=f"libreoffice_{uuid.uuid4().hex}_")
    user_profile = os.path.join(work_dir, "profile")
    src_path = os.path.join(work_dir, f"input{ext}")

    try:
        with open(src_path, "wb") as f:
            f.write(input_bytes)

        proc = await asyncio.create_subprocess_exec(
            soffice,
            f"-env:UserInstallation=file://{user_profile}",
            "--headless",
            "--norestore",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            work_dir,
            src_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ConversionError("LibreOffice conversion timed out")

        if proc.returncode != 0:
            raise ConversionError(
                f"LibreOffice exited with {proc.returncode}: {stderr.decode(errors='ignore')}"
            )

        pdf_path = os.path.join(work_dir, "input.pdf")
        if not os.path.exists(pdf_path):
            raise ConversionError(
                f"Converted PDF not found. stdout={stdout.decode(errors='ignore')} "
                f"stderr={stderr.decode(errors='ignore')}"
            )

        with open(pdf_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
