import base64
import html as html_lib
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from email import policy
from email.parser import BytesParser

import streamlit as st
import streamlit as st
from bs4 import BeautifulSoup


# -----------------------------
# Streamlit page setup
# -----------------------------

st.set_page_config(
    page_title="Tidsskriftet PDF generator",
    page_icon="📄",
    layout="centered",
)

st.title("Tidsskriftet-style PDF generator")
st.write(
    "Upload an MHTML article and a logo. The app generates a print-ready A4 PDF "
    "with two-column layout, Tidsskriftet-style typography, and page numbers."
)


# -----------------------------
# CSS used in generated PDF
# -----------------------------

PDF_CSS = """
@page {
  size: A4;
  margin: 15mm 14mm 17mm 14mm;

  @bottom-right {
    content: counter(page) " / " counter(pages);
    font-family: Georgia, "Times New Roman", serif;
    font-size: 10px;
    color: #111;
  }
}

html {
  font-size: 10.1pt;
}

body {
  margin: 0;
  color: #111;
  background: #fff;
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1.38;
  hyphens: auto;
  font-weight: 400;
}

.print-page {
  max-width: 180mm;
  margin: 0 auto;
}

.article-header {
  margin-bottom: 7.5mm;
  padding-top: 1mm;
  padding-bottom: 5mm;
  border-top: 3pt solid #111;
  border-bottom: 0.8pt solid #777;
}

.logo-wrap {
  width: 50%;
  margin-left: 0;
  margin-bottom: 7mm;
  text-align: left;
}

.logo-wrap img {
  display: block;
  width: 100%;
  height: auto;
}

.kicker {
  display: inline-block;
  font-size: 8.2pt;
  line-height: 1.2;
  font-weight: 700;
  color: #111;
  text-transform: uppercase;
  letter-spacing: 0.035em;
  margin: 0 0 4.5mm 0;
  padding-bottom: 1.5mm;
  border-bottom: 0.8pt solid #999;
}

h1 {
  margin: 0 0 9mm 0;
  font-size: 22.5pt;
  line-height: 1.08;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.meta {
  margin-top: 3.2mm;
  padding-top: 2.5mm;
  border-top: 0.45pt solid #aaa;
  font-size: 8.7pt;
  line-height: 1.35;
  color: #333;
}

.article-columns {
  column-count: 2;
  column-gap: 8mm;
  column-rule: 0.35pt solid #c9c9c9;
}

p,
li {
  margin: 0 0 2.85mm 0;
  text-align: left;
  orphans: 3;
  widows: 3;
}

strong,
b {
  font-weight: 700;
}

em,
i {
  font-style: italic;
}

h2,
h3 {
  break-after: avoid;
  page-break-after: avoid;
  color: #111;
}

h2 {
  column-span: all;
  clear: both;
  margin: 6.4mm 0 3.2mm 0;
  padding-top: 3.2mm;
  border-top: 2pt solid #111;
  border-bottom: 0.5pt solid #9a9a9a;
  padding-bottom: 1.4mm;
  font-size: 14.2pt;
  line-height: 1.15;
  font-weight: 700;
}

h3 {
  margin: 3.7mm 0 1.8mm 0;
  padding-top: 1.4mm;
  border-top: 0.45pt solid #b5b5b5;
  font-size: 10.7pt;
  line-height: 1.18;
  font-weight: 700;
}

ul,
ol {
  margin: 0 0 3mm 4mm;
  padding-left: 3mm;
}

a[href] {
  color: #111;
  text-decoration: none;
}

figure,
.figure-span,
.table-image-span {
  column-span: all;
  break-inside: avoid;
  page-break-inside: avoid;
}

figure {
  margin: 5.5mm 0 6mm 0;
  padding: 3.2mm 0 0 0;
  border-top: 1.8pt solid #111;
  border-bottom: 0.55pt solid #aaa;
  background: transparent;
}

figure img {
  display: block;
  max-width: 100%;
  max-height: 115mm;
  width: auto;
  height: auto;
  margin: 0 auto 2.5mm auto;
  object-fit: contain;
}

figcaption {
  margin: 2mm 0 2.5mm 0;
  padding-top: 1.8mm;
  border-top: 0.45pt solid #aaa;
  font-size: 8.2pt;
  line-height: 1.3;
  color: #222;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 5mm 0;
  font-size: 7.5pt;
  line-height: 1.22;
  break-inside: avoid;
  page-break-inside: avoid;
}

th,
td {
  border-top: 0.45pt solid #999;
  border-bottom: 0.45pt solid #999;
  padding: 1.25mm 1.4mm;
  vertical-align: top;
}

th {
  background: #efefef;
  font-weight: 700;
}

fieldset,
.wp-block-rm-section,
.wp-block-rm-container,
.section-content {
  border: 0 !important;
  outline: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  min-width: 0 !important;
}

legend {
  display: none !important;
}

.page-break,
.pdf-page-break {
  break-before: page;
  page-break-before: always;
  column-span: all;
  height: 0;
  margin: 0;
  padding: 0;
}

.avoid-break {
  break-inside: avoid;
  page-break-inside: avoid;
}
"""


# -----------------------------
# Helper functions
# -----------------------------

def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def data_url_from_bytes(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")

    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def parse_mhtml(mhtml_bytes: bytes):
    msg = BytesParser(policy=policy.default).parsebytes(mhtml_bytes)

    html_part = next(
        part for part in msg.walk()
        if part.get_content_type() == "text/html"
    )

    source_html = html_part.get_payload(decode=True).decode(
        html_part.get_content_charset() or "utf-8",
        "replace",
    )

    resources = {}

    for part in msg.walk():
        loc = part.get("Content-Location")
        payload = part.get_payload(decode=True)
        ctype = part.get_content_type()

        if loc and payload and ctype.startswith("image/"):
            encoded = base64.b64encode(payload).decode("ascii")
            resources[loc] = f"data:{ctype};base64,{encoded}"

    return source_html, resources


def build_print_html(mhtml_bytes: bytes, logo_filename: str, logo_bytes: bytes) -> str:
    source_html, resources = parse_mhtml(mhtml_bytes)
    source_soup = BeautifulSoup(source_html, "html.parser")

    article = source_soup.select_one("article.scientific-article--full")
    if not article:
        raise RuntimeError("Could not find article.scientific-article--full")

    body = article.select_one(".field--name-body")
    if not body:
        raise RuntimeError("Could not find .field--name-body")

    title_el = article.find("h1")
    title = normalize_whitespace(title_el.get_text(" ", strip=True)) if title_el else "Article"

    channel_el = article.select_one(".field--name-field-channel")
    channel = normalize_whitespace(channel_el.get_text(" ", strip=True)) if channel_el else "Originalartikkel"

    byline_el = article.select_one(".field--name-field-byline")
    byline = normalize_whitespace(byline_el.get_text(" ", strip=True)) if byline_el else ""

    content = BeautifulSoup(str(body), "html.parser")

    for el in content.select(
        "button, svg, nav, .visually-hidden, .contextual, .js-contextual-links"
    ):
        el.decompose()

    for img in content.find_all("img"):
        src = img.get("src", "")

        if src in resources:
            img["src"] = resources[src]

        img.attrs.pop("loading", None)
        img.attrs.pop("srcset", None)
        img.attrs.pop("sizes", None)

    for a in content.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            a["href"] = "https://tidsskriftet.no" + href

    logo_src = data_url_from_bytes(logo_filename, logo_bytes)

    final_html = f"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>{html_lib.escape(title)} - A4 print</title>
<style>
{PDF_CSS}
</style>
</head>
<body>
<div class="print-page">

  <header class="article-header">
    <div class="logo-wrap">
      <img src="{logo_src}" alt="Tidsskriftet">
    </div>

    <div class="kicker">{html_lib.escape(channel)}</div>

    <h1>{html_lib.escape(title)}</h1>

    <div class="meta">{html_lib.escape(byline)}</div>
  </header>

  <article class="article-columns">
    {str(content)}
  </article>

</div>
</body>
</html>
"""

    return final_html


def render_pdf_with_weasyprint(html_text: str, output_dir: Path):
    html_path = output_dir / "article_A4_two_column.html"
    pdf_path = output_dir / "article_A4_two_column.pdf"
    zip_path = output_dir / "article_A4_two_column_package.zip"

    html_path.write_text(html_text, encoding="utf-8")

    subprocess.run(
        ["weasyprint", str(html_path), str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(html_path, arcname=html_path.name)
        z.write(pdf_path, arcname=pdf_path.name)

    return html_path, pdf_path, zip_path


# -----------------------------
# Streamlit interface
# -----------------------------

st.header("Upload files")

mhtml_file = st.file_uploader(
    "Upload MHTML article",
    type=["mhtml", "mht"],
)

logo_file = st.file_uploader(
    "Upload logo",
    type=["jpg", "jpeg", "png", "svg", "webp"],
)

generate = st.button("Generate PDF", type="primary")

if generate:
    if not mhtml_file:
        st.error("Please upload an MHTML file.")
        st.stop()

    if not logo_file:
        st.error("Please upload a logo file.")
        st.stop()

    try:
        with st.spinner("Generating PDF..."):
            mhtml_bytes = mhtml_file.read()
            logo_bytes = logo_file.read()

            html_text = build_print_html(
                mhtml_bytes=mhtml_bytes,
                logo_filename=logo_file.name,
                logo_bytes=logo_bytes,
            )

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                html_path, pdf_path, zip_path = render_pdf_with_weasyprint(
                    html_text=html_text,
                    output_dir=tmp_path,
                )

                pdf_bytes = pdf_path.read_bytes()
                html_bytes = html_path.read_bytes()
                zip_bytes = zip_path.read_bytes()

        st.success("PDF generated.")

        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name="article_A4_two_column.pdf",
            mime="application/pdf",
        )

        st.download_button(
            label="Download HTML",
            data=html_bytes,
            file_name="article_A4_two_column.html",
            mime="text/html",
        )

        st.download_button(
            label="Download ZIP package",
            data=zip_bytes,
            file_name="article_A4_two_column_package.zip",
            mime="application/zip",
        )

    except subprocess.CalledProcessError as e:
        st.error("WeasyPrint failed to generate the PDF.")
        st.code(e.stderr or str(e))

    except Exception as e:
        st.error("Could not generate PDF.")
        st.code(str(e))