import logging
from pathlib import Path
log = logging.getLogger(__name__)

def get_mtime(file: Path) -> int:
    return int(file.stat().st_mtime)

def chunk_text(text: str, chunksize: int, overlap: int) -> list[str]:
    length = len(text)
    if not length: return []
    start, end = 0, 0
    chunks = []
    while start < length:
        # ensure start is not in the middle of a word
        if start > 0:
            boundary = text.find(' ', start, end)
            if boundary != -1 and boundary < start + overlap:
                start = boundary + 1
                if start >= length: break

        end = start + chunksize
        # if this is not the final chunk
        if end < length:
            # find the last space (sensible splitting point)
            boundary = text.rfind(' ', start, end)
            # only move end to boundary if doing so is actually useful
            if boundary > start + overlap:
                end = boundary
        chunks.append(text[start:end])

        # set next start point back from previous end by overlap chars 
        start = end - overlap

    return chunks

