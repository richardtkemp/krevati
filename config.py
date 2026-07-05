import os, tomllib, logging, shutil
from pathlib    import Path

log = logging.getLogger(__name__)

_EXAMPLE_PATH = Path(__file__).resolve().parent / 'config.toml.example'


def _config_path() -> Path:
    base = os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config'
    return Path(base) / 'krevati' / 'config.toml'


class ConfigCreated(Exception):
    """Raised when no config file existed, so a blank template was written for
    the user to fill in. Carries the path of the template that was created."""


class Config:
    vault_name      : str
    vault_path      : Path
    exclude_dirs    : list[str]
    cache_dir       : Path
    file_match_glob : str
    socket_path     : str
    server_enabled  : bool
    socket_enabled  : bool
    host            : str
    port            : int
    model_string    : str
    model_context   : int
    model_threads   : int
    overlap         : int
    model_cache_dir : Path
    API_KEY         : str

    def __init__(self, path: Path | None = None) -> None:
        path = path or _config_path()
        if not path.exists():
            self._write_template(path)
            raise ConfigCreated(path)
        with path.open('rb') as f:
            data = tomllib.load(f)

        hints = type(self).__annotations__
        # API_KEY and model_cache_dir resolve separately (env override / generic
        # shared default), so neither is required to appear in the file.
        _optional = ('API_KEY', 'model_cache_dir')
        required = [k for k in hints if k not in _optional]
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"Config file {path} is missing keys: {', '.join(missing)}")

        for key in required:
            value = data[key]
            setattr(self, key, Path(value) if hints[key] is Path else value)

        # Shared on-disk cache for the embedding model (~130MB). Generic default
        # so every agent/user reuses one copy; /var/tmp persists across reboots
        # (unlike /tmp). Override per-agent with model_cache_dir in the config.
        self.model_cache_dir = Path(data.get('model_cache_dir') or '/var/tmp/fastembed_cache')

        self.API_KEY = os.environ.get('KREVATI_API_KEY') or data.get('api_key', '')
        if not self.API_KEY:
            raise ValueError("KREVATI_API_KEY must be set (env var or 'api_key' in config file)")

    @staticmethod
    def _write_template(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_EXAMPLE_PATH, path)
