"""Services package for TikTok Auto-Posting Machine."""

# Import submodules to make them accessible as services.models, services.repositories, etc.
from . import models
from . import repositories
from . import infrastructure
# core is imported lazily to avoid circular imports with scripts

__all__ = [
    "models",
    "repositories", 
    "infrastructure",
    "core",
]

def __getattr__(name: str):
    if name == "core":
        from . import core
        return core
    raise AttributeError(f"module 'services' has no attribute '{name}'")