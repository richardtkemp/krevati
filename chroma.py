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

    def __init__(self, model_string: str, threads: int, cache_dir: Path | None = None) -> None:
        self.model_string = model_string
        self.cache_dir = str(cache_dir) if cache_dir else None
        # 0 means "auto": all usable cores but one, at least one. Otherwise use as
        # given. process_cpu_count() respects CPU affinity (taskset/cpuset).
        self.threads = threads or max(1, (os.process_cpu_count() or 1) - 1)

    def embed(self, chunks: list[str]):
        if not Model.model:
            # threads caps ONNX Runtime's intra-op thread pool; cache_dir is the
            # shared on-disk model store (default /var/tmp/fastembed_cache)
            Model.model = TextEmbedding(self.model_string, cache_dir=self.cache_dir, threads=self.threads)
        return Model.model.embed(chunks)
 
class Chroma:
    _schema_version = 3

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

        self.model = Model(cfg.model_string, cfg.model_threads, cfg.model_cache_dir)
    
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
    
    def upsert_file(self, vault_path: Path, relative_path: Path) -> None:
        log.info(f"adding {relative_path}")
        full_path = vault_path / relative_path
        text = full_path.read_text()
        # need to chunk down to model context size
        chunks = chunk_text(text, self._chunking[0], self._chunking[1])
        if not chunks:
            # No content to embed (e.g. empty/whitespace file). chromadb rejects an
            # empty embeddings list, so never call upsert with nothing.
            log.debug(f"No chunks for {relative_path}, skipping upsert")
            return

        new_count = len(chunks)
        chunkids = range(new_count)
        vectors = [v.tolist() for v in self.model.embed(chunks)] # batch all chunks in one call
    
        # does it already exist? (metadata stores vault_path, not full_path — the
        # old {'full_path': ...} filter never matched, so surplus chunks from a
        # shrunk file were never cleaned up)
        old = self.collection.get(where={'$and': [
            {'relative_path':   {'$eq': str(relative_path)}},
            {'vault_path':      {'$eq': str(vault_path)}}]},
            include=['metadatas'])
        old_count = len(old['ids'])

        # collection.add silently fails if the id already exists
        # so use upsert!
        # NB it does a full *replace* of embedding, document text, and metadata
        mtime = get_mtime(full_path)
        self.collection.upsert(
            embeddings = vectors,
            documents = chunks,
            metadatas = [{'relative_path'   : str(relative_path),
                          'vault_path'      : str(vault_path),
                          'chunk'           : i,
                          'chunking'        : str(self._chunking),
                          'mtime'           : mtime,
                          'schema_version'  : self._schema_version,
                          }
                         for i in chunkids],
            ids = [f"{str(full_path)}::{i}" for i in chunkids]
        )
    

        # delete any surplus chunks if upsert short over long
        if new_count < old_count:
            self.collection.delete(ids=[f"{full_path}::{i}" for i in range(new_count, old_count)])
    
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

        # Chunks are stored under ids "{full_path}::{chunk_index}" with metadata
        # keyed by relative_path/vault_path — there is NO "path" field, so the
        # old where={"path": ...} filter never matched and every file was treated
        # as unindexed and re-embedded on every run. Look up the first chunk by id.
        results = self.collection.get(
                ids=[f"{str(file)}::0"],
                include=["metadatas"])

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

    def _records(self, qr: chromadb.QueryResult) -> zip:
        ids = qr['ids']
        di  = qr['distances']
        me  = qr['metadatas']
        do  = qr['documents']
        assert ids is not None and di is not None and me is not None and do is not None
        return zip(ids[0], di[0], me[0], do[0])

    def search(self, term: str, n_results: int = 5) -> list[SearchResult]:
        log.info(f"Searching for {term}")
        vectors = [v.tolist() for v in self.model.embed([term])]
        query_result = self.collection.query(vectors, n_results = n_results)

        output = []
        for _, dist, meta, doc in self._records(query_result):
            rp = meta['relative_path']
            vp = meta['vault_path']
            assert isinstance(rp, str) and isinstance(vp, str)

            output.append(SearchResult(
                rp,
                round(1-dist,3),
                '', #TODO extract this? will not always be available
                doc,
                ))

        return output
    
    
    def count(self) -> int:
        return self.collection.count()
