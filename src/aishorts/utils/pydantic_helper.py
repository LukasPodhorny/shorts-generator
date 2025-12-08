import json


def load_pydantic_dict(path, cls):
    with open(path, "r") as f:
        data = json.load(f)
    return {name: cls.model_validate(a) for name, a in data.items()}


def load_pydantic(path, cls):
    with open(path, "r") as f:
        data = json.load(f)
    return cls.model_validate(data)


def find_by(items: list, **kwargs):
    return next(
        (
            item
            for item in items
            if all(getattr(item, k, None) == v for k, v in kwargs.items())
        ),
        None,
    )
