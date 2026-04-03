import sys
from pathlib import Path
import fitz  # PyMuPDF

def simple_chunk_pdf(pdf_path: str):
    doc = fitz.open(pdf_path)
    chunks = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        # Very basic chunk by page for now
        if text.strip():
            chunks.append({
                "text": text.strip(),
                "metadata": {
                    "source": Path(pdf_path).name,
                    "page": page_num + 1
                }
            })
    print(f"Extracted {len(chunks)} chunks from {pdf_path}")
    return chunks

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: drun python scripts/ingest_pdfs.py path/to/past_papers/")
        sys.exit(1)
    papers_dir = Path(sys.argv[1])
    for pdf_file in papers_dir.glob("*.pdf"):
        simple_chunk_pdf(str(pdf_file))