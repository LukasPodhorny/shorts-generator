from abc import ABC, abstractmethod
from typing import ClassVar


class Provider(ABC):
    """
    Base class for all providers (TTS, Lipsync, Subtitles, EditTemplates, etc.)
    Each provider type maintains its own registry via inheritance.
    """

    # Each subclass gets its own registry
    _registry: ClassVar[dict[str, type["Provider"]]] = {}

    # Subclasses should define this to auto-register
    provider_name: str | None = None

    def __init_subclass__(cls, **kwargs):
        """
        Automatically register providers when they're defined.
        Each provider type (TTS, Lipsync, etc.) gets its own registry.
        """
        super().__init_subclass__(**kwargs)

        # Create a new registry for each direct subclass of Provider
        # This ensures TTS, Lipsync, etc. have separate registries
        if not hasattr(cls, "_registry"):
            cls._registry = {}

        # Only register if provider_name is set (concrete implementations)
        if cls.provider_name:
            if cls.provider_name in cls._registry:
                existing = cls._registry[cls.provider_name]
                raise ValueError(
                    f"Provider name '{cls.provider_name}' already registered "
                    f"by {existing.__name__}. Cannot register {cls.__name__}."
                )
            cls._registry[cls.provider_name] = cls
            print(
                f"Registered {cls.__bases__[0].__name__}: {cls.provider_name} -> {cls.__name__}"
            )

    @classmethod
    def get(cls, name: str) -> type["Provider"]:
        """Get a specific provider by name."""
        if name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(f"Unknown {cls.__name__} '{name}'. Available: {available}")
        return cls._registry[name]

    @classmethod
    def get_all(cls) -> dict[str, type["Provider"]]:
        """Get all registered providers as {name: class} dict."""
        return cls._registry.copy()

    @classmethod
    def list_names(cls) -> list[str]:
        """Get list of all registered provider names."""
        return list(cls._registry.keys())
