import logging, hashlib
from pathlib import Path
log = logging.getLogger(__name__)

def get_mtime(file: Path) -> int:
    return int(file.stat().st_mtime)

def upsearch_collection_name(directory: Path) -> str:
    """Deterministic, Chroma-valid collection name for a one-shot upsearch over
    an arbitrary directory. Keyed by the resolved path so re-running upsearch on
    the same dir reuses its index (unchanged files are skipped). Isolating each
    dir in its own collection keeps upsearches from polluting the daemon's vault
    or bleeding results across dirs. Chroma names must be 3-63 chars of
    [a-zA-Z0-9._-] starting/ending alphanumeric — 'us_' + 20 hex satisfies that."""
    h = hashlib.sha1(str(directory).encode()).hexdigest()[:20]
    return f"us_{h}"

def chunk_text(text: str, chunksize: int, overlap: int) -> list[str]:
    if chunksize <= overlap:
        raise ValueError('overlap must be smaller than chunk size')

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

        end = start + chunksize
        # if this is not the final chunk
        if end < length:
            # find the last space (sensible splitting point)
            boundary = text.rfind(' ', start, end)
            # only move end to boundary if doing so is actually useful
            if boundary > start + overlap:
                end = boundary
        chunks.append(text[start:end])

        # Don't create a new chunk if we reached the end
        if end >= length:
            break
        
        # set next start point back from previous end by overlap chars 
        start = end - overlap

    return chunks

