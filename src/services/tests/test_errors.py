import inspect

import pytest

from src.services import errors


ERROR_CLASSES = [
    cls for _name, cls in inspect.getmembers(errors, inspect.isclass)
    if cls.__module__ == errors.__name__ and cls is not errors.ServiceError
]


class TestServiceErrors:
    def test_there_are_service_errors_to_catch(self):
        assert len(ERROR_CLASSES) >= 15

    @pytest.mark.parametrize("error", ERROR_CLASSES, ids=lambda cls: cls.__name__)
    def test_every_error_can_be_caught_as_a_service_error(self, error):
        assert issubclass(error, errors.ServiceError)

    @pytest.mark.parametrize("error", ERROR_CLASSES, ids=lambda cls: cls.__name__)
    def test_every_error_carries_its_message(self, error):
        assert str(error("something went wrong")) == "something went wrong"

    def test_service_errors_are_ordinary_exceptions(self):
        assert issubclass(errors.ServiceError, Exception)
