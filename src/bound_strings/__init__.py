import functools
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType
from typing_extensions import TypeVar, Generic, Optional, Self, Protocol, ParamSpec

import libcst as cst


logger = logging.getLogger(__name__)
T = TypeVar("T")
P = ParamSpec("P")


class Bindable(Protocol):
    def bind_text(self, value: cst.FormattedStringText) -> None:
        """Add a string literal to the template"""

    def bind_expression(self, value: cst.FormattedStringExpression) -> None:
        """Save var and bind it to the template"""

    def cst(self: Self) -> cst.BaseExpression:
        """Return a CST representation of the template"""


@dataclass(init=False)
class SQLQuery(Bindable):
    """An example of a Bindable object"""

    template: str
    values: list[cst.BaseExpression]

    def __init__(self: Self, template: str = "", *values: cst.BaseExpression) -> None:
        self.template = template
        self.values = list(values)

    @property
    def self(self: Self) -> Self:
        return self

    def bind_text(self, value: cst.FormattedStringText) -> None:
        self.template += value.value

    def bind_expression(self, value: cst.FormattedStringExpression) -> None:
        # Todo support f-string spec and conversion flags
        self.values.append(value.expression)
        self.template += "$" + str(len(self.values))

    def cst(self: Self) -> cst.BaseExpression:
        return cst.Call(
            func=cst.Name(self.__class__.__name__),
            args=[
                cst.Arg(cst.SimpleString(repr(self.template)), keyword=None),
                *[cst.Arg(value, keyword=None) for value in self.values],
            ],
        )


class FStringBindTransformer(cst.CSTTransformer, Generic[T]):
    def __init__(self: Self, tp: type[Bindable], header_offset: int = 0) -> None:
        """
        Transform f-strings into a Bindable object

        This is a "Safety" transformer, it allows you to write UNSAFE code
        like SQL statements with f-strings (because the UX is nice) and then
        transform the f-strings CST (concrete syntax tree) into a Bindable object
        of seriously questionable safety.

        If all goes well, the transformed code will look like this:
        Original:
            query = f'SELECT * FROM table WHERE id = {id}'

        Transformed:
            query = SQLQuery('SELECT * FROM table WHERE id = $1', id)

        Bindable objects define to "bind" the f-string expressions
        In this case, the SQLQuery binds args to the template with $1, $2, etc.

        Assumption (Which should be challenged):
        - What ever consumer you have for the "f-string", can accept the new Bindable
            object and be useful with it.

        :param tp: A Bindable type, will be constructed instead of each f-string
        :param header_offset: Number of lines to add to the top of the module code
            This keeps line numbers consistent with the original code and helps
            with debugging
        """
        super().__init__()
        self.tp: type[Bindable] = tp
        self.header_offset: int = header_offset
        self._stack: list[Bindable] = []

    @property
    def thing(self: Self) -> Bindable:
        """Shorthand for lazy people who don't want to think about the stack"""
        return self._stack[-1]

    @thing.setter
    def thing(self: Self, value: Bindable) -> None:
        """Shorthand for lazy people who don't want to think about the stack"""
        self._stack.append(value)

    @thing.deleter
    def thing(self: Self) -> None:
        """Shorthand for lazy people who don't want to think about the stack"""
        self._stack.pop()

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        """Update CST to emulate correct line numbers"""
        return updated_node.with_changes(
            header=(tuple(cst.EmptyLine() for _ in range(self.header_offset - 1)))
        )

    def visit_FormattedString(self, node: cst.FormattedString) -> bool | None:
        """Create a new Bindable object for each f-string"""
        self.thing = self.tp()
        return True

    def leave_FormattedString(
        self,
        original_node: cst.FormattedString,
        updated_node: cst.FormattedString,
    ) -> cst.BaseExpression:
        """Return the new CST representation of the f-string"""
        node = self.thing.cst()
        del self.thing
        return node

    def visit_FormattedStringText(
        self: Self,
        node: cst.FormattedStringText,
    ) -> bool | None:
        """Add string literal to the template"""
        self.thing.bind_text(node)
        return True

    def visit_FormattedStringExpression(
        self: Self,
        node: cst.FormattedStringExpression,
    ) -> bool | None:
        """Bind arbitrary expression to the template"""
        self.thing.bind_expression(node)
        return True


Decorator = Callable[[Callable[P, str]], Callable[P, T]]


def bind(tp: type[T]) -> Decorator[P, T]:
    def _bind(func: Callable[P, str]) -> Callable[P, T]:
        func_file, func_line_no = _get_debugging_helper_data(func)
        logger.debug(f"Binding {func.__name__} at {func_file}:{func_line_no}")
        bind_transformer = FStringBindTransformer(tp, func_line_no)
        original_source = inspect.getsource(func)
        logger.debug("original_source %s", original_source)
        module = cst.parse_module(original_source)
        modified_source = module.visit(bind_transformer).code
        logger.debug("modified_source %s", modified_source)
        modified_module = compile(modified_source, func_file, "exec")
        # TODO: Bind globals right before execution?
        func_lookup = [
            maybe_func
            for maybe_func in modified_module.co_consts
            if getattr(maybe_func, "co_name", "") == func.__name__
        ]
        if len(func_lookup) != 1:
            raise ValueError("Could not find function in modified module")
        codeobj = func_lookup[0]

        # Construct a new function with the modified code object
        # Alternatively, we could modify the code object in place
        # Haven't decided which is "better" yet
        new_func = FunctionType(
            codeobj,
            func.__globals__,
            func.__name__,
            func.__defaults__,
            func.__closure__,
        )
        logger.info("Bound f-strings in %s to type %s", func.__name__, tp.__name__)

        @functools.wraps(func)
        def _wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            """Placeholder wrapper, for now not useful."""
            result = new_func(*args, **kwargs)
            if not isinstance(result, tp):
                logger.warning(
                    "Expected return type %s, got %s is this intentional?",
                    tp.__name__,
                    type(result).__name__,
                )
            return result

        return _wrapper

    def _get_debugging_helper_data(func):
        func_file = inspect.getsourcefile(func)
        func_line_no = inspect.getsourcelines(func)[1]
        return func_file, func_line_no

    return _bind
