class ServiceError(Exception):
    pass


class InvalidNameError(ServiceError):
    pass


class InvalidFieldTypeError(ServiceError):
    pass


class InvalidOrderError(ServiceError):
    pass


class EntityNotFoundError(ServiceError):
    pass


class FieldNotFoundError(ServiceError):
    pass


class CategoryNotFoundError(ServiceError):
    pass


class DuplicateCategoryError(ServiceError):
    pass


class DuplicateFieldError(ServiceError):
    pass


class CategoryNotEmptyError(ServiceError):
    pass


class NothingToExportError(ServiceError):
    pass


class ProjectExistsError(ServiceError):
    pass


class ProjectCreationError(ServiceError):
    pass
