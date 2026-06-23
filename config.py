import os
from pathlib    import Path

class Config:
    vault_name      = 'vault'
    vault_path      = Path('/home/rich/vault')
    file_match_glob = '*.md'
    socket_path     = '/tmp/krevati.sock'
    server_enabled  = True
    socket_enabled  = True
    host            = '0.0.0.0'
    port            = 5000
    API_KEY         = os.environ.get('KREVATI_API_KEY', 'default')


    # model details
    model_string    = 'BAAI/bge-small-en-v1.5'
    model_context   = 512 # tokens max per embedding request
    overlap         = 150

    def __init__(self):
        if self.API_KEY == 'default':
            raise ValueError("KREVATI_API_KEY must be set")
