"""
TRUTHFORGE AI — Streamlit File Upload Component
Supports .txt, .pdf, .docx transcript upload.
Returns extracted plain text.
"""

from __future__ import annotations
import io
import tempfile
import os
import streamlit as st


def render_upload() -> str | None:
    """
    Render the file upload widget and extract text.
    Returns plain text of the uploaded file, or None if no file uploaded.
    """
    st.subheader("Upload Legal Transcript")

    uploaded_file = st.file_uploader(
        "Upload a transcript file",
        type=["txt", "pdf", "docx"],
        help="Supported formats: Plain text (.txt), PDF (.pdf), Word document (.docx). Max 10 MB.",
        key="transcript_upload",
    )

    # Demo transcript option
    use_demo = st.checkbox(
        "Use demo transcript (pre-loaded contradictory example)",
        value=False,
        key="use_demo",
    )

    if use_demo:
        return _demo_transcript()

    if uploaded_file is None:
        return None

    # Show file metadata
    col1, col2, col3 = st.columns(3)
    col1.metric("File", uploaded_file.name)
    col2.metric("Size", f"{uploaded_file.size / 1024:.1f} KB")
    col3.metric("Type", uploaded_file.type or "unknown")

    # Extract text
    with st.spinner("Extracting text from file..."):
        text = _extract_text(uploaded_file)

    if not text or not text.strip():
        st.error("Could not extract text from the uploaded file. Please check the file format.")
        return None

    # Preview
    with st.expander("Preview extracted text (first 500 chars)", expanded=False):
        st.text(text[:500] + ("..." if len(text) > 500 else ""))

    st.success(f"Extracted {len(text):,} characters from {uploaded_file.name}")
    return text


def _extract_text(uploaded_file) -> str:
    """Extract plain text from uploaded file based on type."""
    name = uploaded_file.name.lower()

    if name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")

    elif name.endswith(".pdf"):
        return _extract_pdf(uploaded_file)

    elif name.endswith(".docx"):
        return _extract_docx(uploaded_file)

    return ""


def _extract_pdf(uploaded_file) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        try:
            text_parts = []
            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n\n".join(text_parts)
        finally:
            os.unlink(tmp_path)
    except ImportError:
        st.warning("pdfplumber not installed. Install with: pip install pdfplumber")
        return ""
    except Exception as e:
        st.error(f"PDF extraction failed: {e}")
        return ""


def _extract_docx(uploaded_file) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(uploaded_file.read()))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        st.warning("python-docx not installed. Install with: pip install python-docx")
        return ""
    except Exception as e:
        st.error(f"DOCX extraction failed: {e}")
        return ""


def _demo_transcript() -> str:
    return """COURT HEARING TRANSCRIPT — CASE NO. HC/S 1234/2024
Date: 15 January 2024
Before: Justice Lee Hwee Lian, High Court of Singapore

EXAMINATION OF PW1 (First Prosecution Witness — Ms. Sarah Lim):
Counsel (DPP): Ms. Lim, can you describe what you observed on the night of 14 January 2024?
PW1: Yes. I clearly saw the defendant, Mr. John Tan, at the carpark of Blk 45 Woodlands Avenue 3 at approximately 10:30pm. He was wearing a red jacket.

Counsel (DPP): How certain are you of the time?
PW1: I checked my phone immediately after I saw him. It was exactly 10:32pm.

Counsel (DPP): And you are certain it was the defendant?
PW1: Yes, absolutely. I recognise him — he is my neighbour. I have known him for three years.

CROSS-EXAMINATION OF PW1 (by Defence Counsel):
Defence: Ms. Lim, you testified you saw Mr. Tan at Blk 45 carpark at 10:32pm. Is that correct?
PW1: That is correct.

Defence: Earlier in your police statement dated 16 January 2024, you stated you saw him at 9:45pm, not 10:32pm. Which is correct?
PW1: I... I may have made an error in the police statement. I believe it was 10:32pm.

EXAMINATION OF DW1 (First Defence Witness — Mr. Ahmad bin Salleh):
Defence: Mr. Ahmad, where were you on the evening of 14 January 2024?
DW1: I was at Changi Airport Terminal 3, together with Mr. John Tan. We went to collect my friend who was arriving from Bangkok.

Defence: What time did you and Mr. Tan arrive at the airport?
DW1: We arrived at Terminal 3 at approximately 9:30pm and left after 11:00pm when my friend had collected his luggage.

Defence: Did Mr. Tan leave at any point during this time?
DW1: No. We were together the entire time. He was with me from 9:30pm to 11:15pm.

EXAMINATION OF DW2 (Second Defence Witness):
The defence tendered Exhibit D1: Official flight arrival records showing that Flight TG412 from Bangkok arrived at Changi Airport Terminal 3 at 9:52pm on 14 January 2024.

The defence also tendered Exhibit D2: CCTV footage timestamp log from Changi Airport showing Mr. John Tan's face at Terminal 3 Arrival Hall at 22:05 hours (10:05pm) on 14 January 2024.

EXAMINATION OF PW2 (Second Prosecution Witness — Officer Rajan s/o Muthu):
Counsel (DPP): Officer Rajan, you took the statement from Ms. Sarah Lim on 16 January 2024?
PW2: Yes, that is correct.

Counsel (DPP): In that statement, did Ms. Lim give you a time for her observation?
PW2: Yes. Ms. Lim clearly stated she saw the defendant at 9:45pm.

END OF TRANSCRIPT EXCERPT"""
