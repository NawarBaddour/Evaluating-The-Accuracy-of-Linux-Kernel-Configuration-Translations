from enum import Enum


class Evaluator:
    def __init__(
        self, output_dir, linux_ksrc, kernel_version, arch, seed, logger
    ):
        self.logger = logger
        self._linux_ksrc = linux_ksrc
        self._kernel_version = kernel_version
        self._arch = arch
        self._seed = seed

        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True)
        self.logger.debug(
            f"Created model to config directory: '{self._output_dir}'"
        )


class Types(str, Enum):
    BOOL = "bool"
    TRISTATE = "tristate"
    NUMBER = "number"
    STRING = "string"


class HasTypes:
    def __init__(self, value_type=dict):
        for t in Types:
            setattr(self, t.value, value_type())


class HasTypesWithAll(HasTypes):
    def __init__(self, value_type=dict):
        super().__init__(value_type)
        self.all = value_type()


class Categories(str, Enum):
    color: str

    CHANGED = ("changed", "yellow")
    REMOVED = ("removed", "red")
    ADDED = ("added", "green")
    ENABLED = ("enabled", "blue")

    def __new__(cls, value, color):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.color = color
        return obj


class HasStats:
    def __init__(self, value_type=dict):
        for cat in Categories:
            setattr(self, cat.value, HasTypesWithAll(value_type))
