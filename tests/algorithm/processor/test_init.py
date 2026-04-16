import importlib


def test_processor_package_imports():
    module = importlib.import_module('processor')

    assert module.__name__ == 'processor'
    assert module.__path__
