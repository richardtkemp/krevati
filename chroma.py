import chromadb, logging, os, json
from fastembed import TextEmbedding
from misc import get_mtime, chunk_text
from pathlib import Path
from config import Config

log = logging.getLogger(__name__)

class Chroma:
    schema_version = 2

    def __init__(self, cfg: Config, vault_name: str):
        # Chunks of roughly 4 chars per token, with headroom
        self._chunking = (cfg.model_context * 3, cfg.overlap)
        # where we will store chroma's database
        cache_dir = Path.home() / f".cache/chromadb-{vault_name}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=str(cache_dir))
        self.collection = self.client.get_or_create_collection(vault_name)
        self.model = TextEmbedding(cfg.model_string)
    
    # TODO how to handle wiping when multiple dirs are indexed?
    def dangerously_wipe_db(self):
        log.warning('Wiping all existing DB content...')
        self.collection.delete(where={"path": {"$ne": ""}})
        log.warning('Done wiping')
    
    def delete_file(self, file: Path):
        # TODO verify file is in DB?? 
        log.info(f"Deleting {file} from DB")
        self.collection.delete(where={"path": {"$eq": str(file)}})
        log.info('Done deleting')
    
    def upsert_file(self, vault_path: Path, file: Path):
        log.info(f"adding {file}")
        text = file.read_text()
        # need to chunk down to model context size
        chunks = chunk_text(text, self._chunking[0], self._chunking[1])

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
                          'schema_version'  : self.schema_version,
                          }
                         for i in chunkids],
            ids = [f"{str(file)}::{i}" for i in chunkids]
        )
    
        # delete any surplus chunks if upsert short over long
        if new_count < old_count:
            self.collection.delete(ids=[f"{file}::{i}" for i in range(new_count, old_count)])
    
    def needs_indexing(self, file: Path):
        # File doesn't exist
        if not os.path.exists(file):
            log.debug(f"Not indexing nonexistent file {file}")
            return False

        # File is empty
        if file.stat().st_size == 0: # empty
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

        # Schema version changed
        stored_ver = results['metadatas'][0].get('schema_version', 0)
        assert isinstance(stored_ver, int)
        if stored_ver < self.schema_version: 
            # TODO might need to do some extra to wipe out old schema keys,
            # if any are ever removed!
            return True

        # Chunking changed
        stored_chunking = results['metadatas'][0].get('chunking', '')
        assert isinstance(stored_ver, str)
        if stored_chunking != str(self._chunking):
            return True
        
        # File changed
        stored_mtime = results['metadatas'][0].get('mtime', 0)
        assert isinstance(stored_mtime, int)
        if get_mtime(file) > stored_mtime:
            log.debug(f"Not indexing unchanged file {file}")
            return True

        return False
    
    def search(self, term: str, n_results: int = 5):
        log.info(f"Searching for {term}")
        vectors = [v.tolist() for v in self.model.embed([term])]
        return self.collection.query(vectors, n_results = n_results)
    
    def json_print(self, result) -> str:
        hits = zip(
                result['distances'][0],
                result['metadatas'][0],
                result['documents'][0],
                )
        output = []
        for dist, meta, doc in hits:
            path = meta['path']
            if path.startswith(meta['vault_path']):
                path = str(Path(path).relative_to(meta['vault_path']))

            output.append({
                'path': path,
                'header': '', #TODO extract this? will not always be available
                'snippet': doc[:100], # TODO store whole thing?
                'score': round(1-dist,3),
                })

        return json.dumps(output)
    
    def pretty_print(self, result) -> str:
        hits = zip(
                result['ids'][0],
                result['distances'][0],
                result['metadatas'][0],
                result['documents'][0],
                )
        output = []
        for id_, dist, meta, doc in hits:
            output.append(f"\n%%%% DISTANCE {dist:.3f} %%%%\n%%%% PATH {meta['path']} %%%%\n%%%% CHUNK {meta['chunk']} %%%%")
            output.append(doc[:200])

        return '\n'.join(output)
    
    def count(self):
        return self.collection.count()
