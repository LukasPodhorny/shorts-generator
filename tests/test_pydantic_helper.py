import pytest
from unittest.mock import mock_open, patch
from pydantic import BaseModel
from aishorts.utils.pydantic_helper import load_pydantic, load_pydantic_dict, find_by


class MockModel(BaseModel):
    id: int
    name: str


def test_load_pydantic():
    json_data = '{"id": 1, "name": "test"}'
    with patch("builtins.open", mock_open(read_data=json_data)):
        obj = load_pydantic("dummy.json", MockModel)
        assert obj.id == 1
        assert obj.name == "test"


def test_load_pydantic_dict():
    json_data = '{"item1": {"id": 1, "name": "a"}, "item2": {"id": 2, "name": "b"}}'
    with patch("builtins.open", mock_open(read_data=json_data)):
        data = load_pydantic_dict("dummy.json", MockModel)
        assert len(data) == 2
        assert data["item1"].name == "a"


def test_find_by():
    items = [MockModel(id=1, name="a"), MockModel(id=2, name="b")]
    found = find_by(items, id=2)
    assert found.name == "b"

    not_found = find_by(items, id=3)
    assert not_found is None
