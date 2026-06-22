import chromadb, logging
from fastembed import TextEmbedding
from misc import get_mtime, chunk_text
from pathlib import Path

log = logging.getLogger(__name__)

class Chroma:

    # model details
    modelstring = 'BAAI/bge-small-en-v1.5'
    modelcontext = 512 # tokens max
    chunksize = modelcontext * 3 # roughly 4 chars per token, with headroom
    overlap = 150

    def __init__(self, vaultname: str):
        # where we will store chroma's database
        cache_dir = Path.home() / f".cache/chromadb-{vaultname}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=str(cache_dir))
        self.collection = self.client.get_or_create_collection(vaultname)
        self.model = TextEmbedding(self.modelstring)
    
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
    
    def upsert_file(self, file: Path):
        log.info(f"adding {file}")
        text = file.read_text()
        # need to chunk down to model context size
        chunks = chunk_text(text, self.chunksize, self.overlap)
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
            metadatas = [{'path': str(file),
                          'chunk': i,
                          'mtime': mtime}
                         for i in chunkids],
            ids = [f"{str(file)}::{i}" for i in chunkids]
        )
    
        # delete any surplus chunks if upsert short over long
        if new_count < old_count:
            self.collection.delete(ids=[f"{file}::{i}" for i in range(new_count, old_count)])
    
    def needs_indexing(self, file: Path):
        results = self.collection.get(
                where={"path": {"$eq": str(file)}},
                include=["metadatas"],
                limit=1)
    
        if not results['ids']:
            return True # not indexed yet
    
        assert results['metadatas'] is not None
        stored_mtime = results['metadatas'][0].get('mtime', 0)
        assert isinstance(stored_mtime, int)

        log.debug(f"stored_mtime={stored_mtime}, file_mtime={get_mtime(file)}")
        return get_mtime(file) > stored_mtime
    
    def search(self, term: str, n_results: int = 5): ## TODO magic number
        vectors = [v.tolist() for v in self.model.embed([term])]
        return self.collection.query(vectors, n_results = n_results)
    
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
