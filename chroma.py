import chromadb, logging, os
from fastembed import TextEmbedding
from misc import get_mtime, chunk_text
from pathlib import Path
from config import Config
from db import SearchResult, is_stale

log = logging.getLogger(__name__)

class Model:
    # Once loaded, preserve model across instantiations with a class variable
    model = None

    def __init__(self, model_string):
        self.model_string = model_string

    def embed(self, chunks):
        if not Model.model:
            Model.model = TextEmbedding(self.model_string)
        return Model.model.embed(chunks)
 
class Chroma:
    _schema_version = 2

    def __init__(self, cfg: Config):
        # Chunks of roughly 4 chars per token, with headroom
        cs = cfg.model_context * 3
        o = cfg.overlap
        if cs <= o:
            raise ValueError('overlap must be smaller than chunk size')

        self._chunking = (cs, o)
        # where we will store chroma's database
        cache_dir = cfg.cache_dir / f"chromadb-{cfg.vault_name}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=str(cache_dir))
        self.collection = self.client.get_or_create_collection(cfg.vault_name)

        self.model = Model(cfg.model_string)
    
    # TODO how to handle wiping when multiple dirs are indexed?
    def dangerously_wipe_db(self) -> None:
        log.warning('Wiping all existing DB content...')
        self.collection.delete(where={"path": {"$ne": ""}})
        log.warning('Done wiping')
    
    def delete_file(self, file: Path) -> None:
        # TODO verify file is in DB?? 
        log.info(f"Deleting {file} from DB")
        self.collection.delete(where={"path": {"$eq": str(file)}})
        log.info('Done deleting')
    
    def upsert_file(self, vault_path: Path, file: Path) -> None:
        log.info(f"adding {file}")
        text = file.read_text()
        # need to chunk down to model context size
        chunks = chunk_text(text, self._chunking[0], self._chunking[1])
        if not chunks:
            # No content to embed (e.g. empty/whitespace file). chromadb rejects an
            # empty embeddings list, so never call upsert with nothing.
            log.debug(f"No chunks for {file}, skipping upsert")
            return

        new_count = len(chunks)
        chunkids = range(new_count)
        vectors = [v.tolist() for v in self.model.embed(chunks)] # batch all chunks in one call
    
        # does it already exist?
        old = self.collection.get(where={'path': {'$eq': str(file)}}, include=['metadatas'])
        old_count = len(old['ids'])

        # collection.add silently fails if the id already exists
        # so use upsert!
        mtime = get_mtime(file)
        self.collection.upsert(
            embeddings = vectors,
            documents = chunks,
            metadatas = [{'path'            : str(file),
                          'chunk'           : i,
                          'chunking'        : str(self._chunking),
                          'mtime'           : mtime,
                          'vault_path'      : str(vault_path),
                          'schema_version'  : self._schema_version,
                          }
                         for i in chunkids],
            ids = [f"{str(file)}::{i}" for i in chunkids]
        )
    
        # delete any surplus chunks if upsert short over long
        if new_count < old_count:
            self.collection.delete(ids=[f"{file}::{i}" for i in range(new_count, old_count)])
    
    def needs_indexing(self, file: Path) -> bool:
        # File doesn't exist
        if not os.path.exists(file):
            log.debug(f"Not indexing nonexistent file {file}")
            return False
        size = file.stat().st_size
        # Empty file: guard here in the shell, BEFORE the "not indexed" check below.
        # A brand-new empty file would otherwise return True and crash upsert_file
        # with empty embeddings. (is_stale only runs for already-indexed files.)
        if size == 0:
            log.debug(f"Not indexing empty file {file}")
            return False

        results = self.collection.get(
                where={"path": {"$eq": str(file)}},
                include=["metadatas"],
                limit=1)
    
        # File not yet indexed
        if not results['ids']:
            return True
    
        assert results['metadatas'] is not None

        stored_ver = results['metadatas'][0].get('schema_version', 0)
        stored_chunking = results['metadatas'][0].get('chunking', '')
        stored_mtime = results['metadatas'][0].get('mtime', 0)
        mtime = get_mtime(file)
        assert isinstance(stored_ver, int) and isinstance(stored_mtime, int) and isinstance(stored_chunking, str)

        return is_stale(file, size, stored_ver, self._schema_version, stored_chunking, str(self._chunking), stored_mtime, mtime)

    def _records(self, qr):
        ids = qr['ids'][0]
        di  = qr['distances'][0]
        me  = qr['metadatas'][0]
        do  = qr['documents'][0]
        assert ids is not None and di is not None and me is not None and do is not None
        return zip(ids, di, me, do)

    def search(self, term: str, n_results: int = 5) -> list[SearchResult]:
        log.info(f"Searching for {term}")
        vectors = [v.tolist() for v in self.model.embed([term])]
        query_result = self.collection.query(vectors, n_results = n_results)

        output = []
        for _, dist, meta, doc in self._records(query_result):
            p  = meta['path']
            vp = meta['vault_path']
            assert isinstance(p, str) and isinstance(vp, str)

            # Store absolute paths, return relative paths
            # TODO maybe just *store relative paths* since
            # we also store the vault_path anyway
            if p.startswith(vp):
                p = str(Path(p).relative_to(vp))

            output.append(SearchResult(
                p,
                round(1-dist,3),
                '', #TODO extract this? will not always be available
                doc[:100], # TODO return whole thing?
                ))

        return output
    
    
    def count(self):
        return self.collection.count()
