TTS_PROVIDERS: dict[str, type] = {}


def register_tts(provider_name: str):
    def decorator(cls):
        TTS_PROVIDERS[provider_name.lower()] = cls
        return cls

    return decorator


LIPSYNC_PROVIDERS: dict[str, type] = {}


def register_lipsync(provider_name: str):
    def decorator(cls):
        LIPSYNC_PROVIDERS[provider_name.lower()] = cls
        return cls

    return decorator


EDIT_TEMPLATES: dict[str, type] = {}


def register_edit_template(template_name: str):
    def decorator(cls):
        EDIT_TEMPLATES[template_name.lower()] = cls
        return cls

    return decorator


SUBTITLE_PROVIDERS: dict[str, type] = {}


def register_subtitle(template_name: str):
    def decorator(cls):
        SUBTITLE_PROVIDERS[template_name.lower()] = cls
        return cls

    return decorator


LLM_PROVIDERS: dict[str, type] = {}


def register_llm(provider_name: str):
    def decorator(cls):
        LLM_PROVIDERS[provider_name.lower()] = cls
        return cls

    return decorator
