import dataclasses
import inspect
from typing import Callable, List, Optional, Type

from .arguments import get_arguments_from_resolver
from .permission import BasePermission
from .types.types import FederationFieldParams, FieldDefinition
from .utils.str_converters import to_camel_case


class StrawberryField(dataclasses.Field):
    _field_definition: FieldDefinition

    def __init__(self, field_definition: FieldDefinition):
        self._field_definition = field_definition

        super().__init__(  # type: ignore
            default=dataclasses.MISSING,
            default_factory=dataclasses.MISSING,
            init=field_definition.base_resolver is None,
            repr=True,
            hash=None,
            compare=True,
            metadata=None,
        )

    def __call__(self, resolver: Callable) -> Callable:
        """Migrate the field definition to the resolver"""

        # TODO: This does not copy the data and now two objects share the same
        #       FieldDefinition. Presumably this field will be GC-ed soon
        #       though?
        field_definition = self._field_definition
        # Note: field_definition.name is finalized in type_resolver._get_fields

        resolver_name = to_camel_case(resolver.__name__)

        field_definition.origin_name = resolver_name

        field_definition.origin = resolver
        field_definition.base_resolver = resolver
        field_definition.arguments = get_arguments_from_resolver(resolver)

        field_definition.type = resolver.__annotations__.get("return", None)

        if not inspect.ismethod(resolver):
            # resolver is a normal function
            resolver._field_definition = field_definition  # type: ignore
        else:
            # resolver is a bound method and immutable (most likely a
            # classmethod or an instance method). We need to monkeypatch its
            # underlying .__func__ function
            # https://stackoverflow.com/a/7891681/8134178
            resolver.__func__._field_definition = field_definition  # type:ignore

        return resolver

    def __setattr__(self, name, value):
        if name == "type":
            self._field_definition.type = value

        if value and name == "name":
            if not self._field_definition.origin_name:
                self._field_definition.origin_name = value

            if not self._field_definition.name:
                self._field_definition.name = to_camel_case(value)

        return super().__setattr__(name, value)


def field(
    resolver: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    is_subscription: bool = False,
    description: Optional[str] = None,
    permission_classes: Optional[List[Type[BasePermission]]] = None,
    federation: Optional[FederationFieldParams] = None
):
    """Annotates a method or property as a GraphQL field.

    This is normally used inside a type declaration:

    >>> @strawberry.type:
    >>> class X:
    >>>     field_abc: str = strawberry.field(description="ABC")

    >>>     @strawberry.field(description="ABC")
    >>>     def field_with_resolver(self, info) -> str:
    >>>         return "abc"

    it can be used both as decorator and as a normal function.
    """

    field_definition = FieldDefinition(
        origin_name=None,  # modified by resolver in __call__
        name=name,  # modified by resolver in __call__
        type=None,  # type: ignore
        origin=resolver,  # type: ignore
        description=description,
        base_resolver=resolver,
        is_subscription=is_subscription,
        permission_classes=permission_classes or [],
        arguments=[],  # modified by resolver in __call__
        federation=federation or FederationFieldParams(),
    )

    field_ = StrawberryField(field_definition)

    if resolver:
        patched_resolver = field_(resolver)
        return patched_resolver
    else:
        return field_
