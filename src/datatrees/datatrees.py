"""
Created on 8 Dec 2021

@author: gianni

Wrapper over Python's dataclass that allows for:
- Injection and Binding: the composition of classes by injecting constructor parameters
  or function parameters automatically binding the injected fields to the factory calls.
- self_default: Not unline default_factory, self_default is called after the constructor
  has finished and with the class instance (self) as the first parameter.
- post_init chaining: When the inherited classes post_init will be called in reverse MRO
  order. Doing this manually is error prone and difficult to maitain because manually
  chaining post_init in each class will sometimes result in a pareant post_init being
  called multiple times (classic issue with diamond inheritance).
- docstrings: Docstrings can be provided for fields and these will also be injected.

Datatrees is particularly useful when composing a class from other classes or functions
in a heirarchical manner where fields from classes deeper in the hierarchy need to be
propagated as root class parameters. The boilerplate code for such a composition
is often error prone and difficult to maintain. The impetutus for this library came
from building hierarchical 3D models where each node in the hierarchy collected fields
from nodes nested in the hierarchy. Using datatree, almost all the boilerplate
management of model parameters was eliminated resulting in a clean and maintainable
3D model classes.

Injection and Binding:

The Node[T] annotation with a Node default value is used to determine the injected
fields. Upon class contruction Node fields transform into factories that bind the
injected fields as defaults. Field names can be mapped to different names, prefixed or
suffixed or excluded from injection.

Example:

@datatree  # or @dataclass
class A:
    a: int=1
    b: int=2
    x: int=0

@datatree
class B:
    x: int=3  # Change the default value of x (first x wins)
    a_node: Node[A]=Node(A, 'a', {'b': 'c'}, 'x')  # A factory where field b is mapped to c

b = B(c=5) # field c is mapped to A's b
a = b.a_node() # a is an instance of A with a=1, b=5, x=3

# The following are true

# The a field in B is mapped to the a field in A.
b.a == 1
a.a == 1

# The c field in B is mapped to the b field in A.
b.c == 5
a.b == 5

# The x field in B is mapped to the x field in A
# but the default value is now the value of the x
# field in B.
a.x == 3

In the above example, the Node field a_node causes the fields of A to be
injected into B. The field 'a' is mapped to 'a' and the field 'b' is mapped
to 'c'. Hence B contains 4 fields (but only 3 parameters to the constructor
because by default Node fields are init=False and not included in the constructor
parameters), a_node, a, c (mapped to b) and x. The a_node field is a factory that
creates an instance of A that has the 'a' init parameter default set to the value
of the field 'a' in B and the default value of the init parameter 'b' is set to
the value of the field 'c' in B etc.

Datatree is particularly useful when composing a class from other classes or
functions where the fields or constructor or function parameters
become member fields of the composing class. Datatree will automate the
generation of these fields to become dataclass members. datatree will pull
constructor field definitions of Node declarations and add annotations to
the enclosed datatree class including any default values or other
dataclasses.field properties. This is especially useful when constructing
complex relationships that require a large number of parameters.


Deafault values with self_default:

Like the dataclasses field() function's default_factory parameter, the
self_default parameter to the dtfield() function allows for a parameter that is
provided with the class instance (self) as the first parameter.
The self_default lambda or function is called after the dataclass constructor
has finished and all the Node fields have been initialized to factories
(BoundNodes) and are called in the order of the declaration of fields within the
class. Note than injected fields are placed immedialtly prior to Node that
injects them. Fields with self_default functions are by default init=False
and are not included in the constructor parameters (or injected) however if
they are they will be called in the parent class datatree initialization
and will not work as expected if fields are renamed or not injected.


Post_init Chaining:

The post_init chaining is indicated by the adding the post_init_chain=True parameter
to the datatree decorator.

@datatree(post_init_chain=True)

The post_init chaining is implemented by calling the post_init methods of the
parent classes in reverse MRO order. It will ensure that the parent post_init
methods are called only once. It will also handle InitVar fields and pass InitVar
fields that are nominated in parent classes.

Docstrings:

Adding the doc="field documentation" to dtfield() will associate the field with the
docstring. When fields are injected, the docstring is injected into the field.

Documentation for Injected Fields:

The datatrres.get_injected_fields() function can be used to get injected field
documentation. The get_injected_fields() function returns an InjectedFields object
that can be used to generate an html page containing the injected fields and their
bindings.

        injectedFields = datatrees.get_injected_fields(clz)
        if not injectedFields:
            return
        html_str = injectedFields.generate_html_page(lambda x : str(x))
        ... write html_str to a file or serve it to a client ...

"""

import copy
from dataclasses import (
    dataclass,
    field,
    Field,
    InitVar,
    MISSING,
    _FIELD_INITVAR,
)
from functools import wraps
import sys
from typing import (
    List,
    Dict,
    Any,
    Callable,
    Generic,
    Optional,
    TypeVar,
    get_args,
    get_origin,
    ClassVar,
    TYPE_CHECKING,
    Iterable,
    Mapping,
)

from frozendict import frozendict
import inspect
import builtins
import re
from abc import ABC, abstractmethod

from sortedcollections import OrderedSet

try:
    from typing import get_type_hints
except ImportError:
    # Stub this function for Python 3.12 and earlier.
    def get_type_hints(clz: type, localns: dict[str, Any] | None = None, globalns: dict[str, Any] | None = None) -> dict[str, Any]:
        return clz.__annotations__
if TYPE_CHECKING:
    try:
        from typing import dataclass_transform  # Python 3.11+
    except ImportError:
        from typing_extensions import dataclass_transform  # Python < 3.11


FIELD_FIELD_NAMES = tuple(inspect.signature(field).parameters.keys())
DATATREE_SENTIENEL_NAME = "__datatree_nodes__"
OVERRIDE_FIELD_NAME = "override"  # Deprecated feature.
METADATA_DOCS_NAME = "dt_docs"
ORIGINAL_POST_INIT_NAME = "__original_post_init__"  # User provided post_init renamed to this.
DATATREE_POST_INIT_SENTIENEL_NAME = "__is_datatree_override_post_init__"

_T = TypeVar("_T")  # Generic type variable for Node[T] fields.


class ReservedFieldNameException(Exception):
    f"""The name '{OVERRIDE_FIELD_NAME}' is reserved for use by datatree."""


class NameCollision(Exception):
    """The requested name is already specified."""


class ExpectedDataclassObject(Exception):
    """Node requires the given object to be dataclass decorated."""


class MappedFieldNameNotFound(Exception):
    """Field name specified is not found in the given class."""


class DataclassAlreadyApplied(Exception):
    """The function called in intended to be called before the dataclass decorator."""


class IllegalMetadataClass(Exception):
    """Classes inheriting FieldMetadataBase must override get_doc."""


class SpecifiedMultipleDefaults(Exception):
    """Attempting to specify default and self_default parameters."""


class NodeHasNoClzOrFunc(Exception):
    """The Node specified has no clz_or_func parameter and the Node[T] type T is not specified."""


class _OrderedSet(OrderedSet[Any]):
    def union(self, *others: Iterable[Any]) -> "_OrderedSet":
        result = _OrderedSet(self)
        for other in others:
            for item in other:
                result.add(item)  # type: ignore
        return result

    def intersection(self, *others: Iterable[Any]) -> "_OrderedSet":
        result = _OrderedSet()
        for other in others:
            for item in self:
                if item in other:
                    result.add(item)  # type: ignore
        return result


def _update_name_map(
    clz: type, name_map: dict[str, Any], from_name: str, to_value: Any, description: str
):
    """Updates the given map but does not allow collision."""
    if from_name in name_map:
        raise NameCollision(f"{description} {from_name} specified multiple times in {clz.__name__}")
    name_map[from_name] = to_value


def _update_name_multi_map(clz: type, name_map: dict[str, Any], from_name: str, to_value: Any):
    """Updates the given multi-valued map."""
    if from_name in name_map:
        cur = name_map[from_name]
        name_map[from_name] = cur + (to_value,)
    else:
        name_map[from_name] = (to_value,)


def _dupes_and_allset(itr: Iterable[Any]) -> tuple[_OrderedSet, _OrderedSet]:
    """Returns a tuple containing a set of duplicates and a set of all non
    duplicated items in itr."""
    seen = _OrderedSet()
    dupes = _OrderedSet()
    for x in itr:
        if x in seen:
            dupes.add(x)  # type: ignore
        else:
            seen.add(x)  # type: ignore
    return dupes, seen


@dataclass
class AnnotationDetails:
    """A dataclass/annotation pair."""

    field: object
    anno_type: type

    @classmethod
    def from_init_param(cls, name: str, inspect_params: Mapping[str, inspect.Parameter]):
        """Creates an AnnotationDetails from a name and inspect.Signature.parameters"""
        param = inspect_params[name]

        anno = param.annotation
        if anno is inspect._empty:
            anno = object

        default = param.default

        if default is inspect._empty:
            default = MISSING

        this_field = field(default=default)
        return AnnotationDetails(this_field, anno)


def _field_assign(obj: object, name: str, value: Any):
    """Field assignment that works on frozen objects."""
    builtins.object.__setattr__(obj, name, value)


class FieldMetadataBase(ABC):
    """Datatree metadata object."""

    @abstractmethod
    def get_doc(self) -> str | None:
        pass


@dataclass(frozen=True)
class FieldMetadata(FieldMetadataBase):
    """Provides a docstring for a field."""

    doc: str | None

    def get_doc(self) -> str | None:
        """Returns the docstring."""
        return self.doc


@dataclass(frozen=True)
class NodeFieldMetadata(FieldMetadataBase):
    """Provides a docstring for a Node field."""

    node_doc: str | None
    field_metadata: FieldMetadata

    def get_doc(self) -> str | None:
        if self.node_doc is None:
            return self.field_metadata.get_doc()
        return f"{self.node_doc}: {self.field_metadata.get_doc()}"


CLEANER_REGEX = re.compile("(\n?[ \t][ \t]+)+")


def _get_abbreviated_source(func: Callable[..., Any], max_size: int = 75) -> str:
    """Returns stripped abbreviated source of a function (or lambda)."""
    src = inspect.getsource(func).strip()
    # Remove interspersed white space chunks.
    src = " ".join(s.strip() for s in CLEANER_REGEX.split(src) if s.strip())
    return (src[:max_size] + "...") if len(src) > (3 + max_size) else src


@dataclass(frozen=True, repr=False)
class BindingDefault(Generic[_T]):
    """Like the dataclass field default_factory parameter but called after
    the regular __init__ function is finished and with the class instance
    (self) as the first parameter."""

    self_default: Callable[[Any], _T]

    def __repr__(self):
        return f"{self.__class__.__name__}({_get_abbreviated_source(self.self_default)})"


def field_docs(obj: object, field_name: str) -> str | None:
    """Return the documentation for a field. Returns None if not provided."""
    metadata = obj.__dataclass_fields__[field_name].metadata  # type: ignore

    if not metadata:
        return None

    doc_metadata: FieldMetadata = metadata.get(METADATA_DOCS_NAME, None)  # type: ignore
    if doc_metadata is None:
        return None

    return doc_metadata.get_doc()  # type: ignore


_Node = None  # Forward declaration for Node. This is set later.


def dtfield(
    default: Any = MISSING,
    doc: str | None = None,
    self_default: Callable[[Any], Any] | None = None,
    init: bool | object = MISSING,
    default_factory: Callable[[Any], Any] | None = MISSING,  # type: ignore
    **kwargs: Any,
) -> Any:
    """Like dataclasses.field but also supports doc parameter.
    Args:
      default: The default value for the field.
      doc: A docstring associated with the field.
      self_default: A default factory taking a self parameter.
      Includes all fields allowed by dataclasses.field().
    """
    metadata = kwargs.pop("metadata", {})
    metadata[METADATA_DOCS_NAME] = FieldMetadata(doc)
    if default_factory is not MISSING:
        kwargs["default_factory"] = default_factory

    if self_default:
        if default is not MISSING and default_factory is not MISSING:
            raise SpecifiedMultipleDefaults(
                "Can only specify one of default, default_factory or self_default."
            )
        default = BindingDefault(self_default)

    if init is MISSING:
        # Don't make self_default and Node fields init by self_default.
        types = (_Node, BindingDefault) if _Node is not None else BindingDefault
        init = not isinstance(default, types)

    return field(**kwargs, default=default, metadata=metadata, init=init)


@dataclass(frozen=True, repr=False)
class _ClzOrFuncWrapper(Generic[_T]):
    clz_or_func: type[_T] | Callable[..., _T]

    def __repr__(self):
        return self.clz_or_func.__name__


class MISSING_PARAM_TYPE:
    pass


MISSING_PARAM = MISSING_PARAM_TYPE()


@dataclass(frozen=True)
class Node(Generic[_T]):
    """A specifier for a datatree node. This specifies how fields
    from a class initializer (or function) is translated from fields in the
    composition class.
    """

    clz_or_func: type[_T] | Callable[..., _T] = dtfield(
        doc="A class or function for parameter binding."
    )
    use_defaults: bool = dtfield(
        doc="Allows use of defaults otherwise defaults should be specified elsewhere."
    )
    suffix: str = dtfield(doc="Suffix to apply to injected field names.")
    prefix: str = dtfield(doc="Prefix to apply to injected field names.")
    expose_all: bool = dtfield(
        doc="Forces the mapping of all fields even if the expose_spec "
        " excluded the class or function parameter name."
    )
    expose_if_avail = (dtfield(doc="Expose fields if they are available."),)
    preserve = (dtfield(doc="Preserve fields from the class or function."),)
    exclude = (dtfield(doc="Exclude fields from the class or function."),)
    init_signature: inspect.Signature | None = field(default=None, repr=False)
    expose_map: dict[str, str] = field(default_factory=dict, repr=False)
    expose_rev_map: dict[str, Any] = field(default_factory=dict, repr=False)
    node_doc: str | None = dtfield(None, doc="Field documentation.")
    default_if_missing: Any = field(default=MISSING_PARAM)
    expose_spec: list[str | dict[str, str]] = field(default_factory=list, repr=False)
    anno_getter: 'AnnotationsAccessor' = field(default_factory=lambda: AnnotationsAccessor(), repr=False)

    # The default value for the preserve init parameter. Derived classes can override.
    # This allows for application specific Node types that have a set of
    # field names that should be preserved from prefix and suffix mapping.
    DEFAULT_PRESERVE_SET: ClassVar[frozenset[str]] = frozenset()
    # The default value for the expose_if_avail init parameter. Derived classes can override.
    # Similar to DEFAULT_PRESERVE_SET, allows for application specific Node type.
    DEFAULT_EXPOSE_IF_AVAIL: ClassVar[set[str]] = set()

    ALT_DEFAULT_ALLOW_SET = None

    def __init__(
        self,
        *expose_spec: Any,
        use_defaults: bool = True,
        suffix: str = "",
        prefix: str = "",
        expose_all: bool | None = None,
        expose_if_avail: set[str] | None = None,
        preserve: set[str] | frozenset[str] | None = None,
        exclude: set[str] = set(),
        node_doc: str | None = None,
        default_if_missing: Any = MISSING_PARAM,
    ):
        """Initialize a Node instance for parameter binding.

        Args:
            clz_or_func: A class or function for parameter binding.
            *expose_spec: A list of names and dictionaries for mapping. If these
                are specified, only these fields are mapped unless expose_all is set.
            use_defaults (bool, optional): Whether to use defaults from the source class.
                Defaults to True.
            suffix (str, optional): Suffix to apply to injected field names not otherwise
                mapped. Defaults to ''.
            prefix (str, optional): Prefix to apply to injected field names not otherwise
                mapped. Defaults to ''.
            expose_all (bool, optional): Forces the mapping of all fields even if the
                expose_spec excluded the class or function parameter name. Defaults to None.
            expose_if_avail (set, optional): The set of fields to expose if they're
                available. Defaults to None.
            preserve (set, optional): A set of names that are not prefixed or suffixed.
                Defaults to None.
            exclude (tuple, optional): A set of field names to exclude that would otherwise
                be included by expose_all. Defaults to ().
            node_doc (str, optional): Documentation for the node field. Defaults to None.
            default_if_missing (Any, optional): The value to use if an injected field has
                no default value. Defaults to MISSING_PARAM. Usually set this to None to
                as a generic not set value cut some other application specific value can
                be used. TODO Maybe add type specific default_if_missing values.
        """
        if preserve is None:
            preserve = self.DEFAULT_PRESERVE_SET

        if expose_if_avail is None:
            expose_if_avail = self.DEFAULT_EXPOSE_IF_AVAIL

        clz_or_func: Any
        if expose_spec:
            if isinstance(expose_spec[0], (str, dict)):
                clz_or_func = None
            else:
                clz_or_func = expose_spec[0]
                expose_spec = expose_spec[1:]
        else:
            clz_or_func = None

        _field_assign(self, "use_defaults", use_defaults)
        expose_all = not expose_spec if expose_all is None else expose_all
        _field_assign(self, "expose_all", expose_all)
        _field_assign(self, "suffix", suffix)
        _field_assign(self, "prefix", prefix)
        _field_assign(self, "node_doc", node_doc)
        _field_assign(self, "expose_spec", expose_spec)

        _field_assign(self, "preserve", preserve)
        _field_assign(self, "expose_if_avail", expose_if_avail)
        _field_assign(self, "exclude", exclude)
        _field_assign(self, "default_if_missing", default_if_missing)
        _field_assign(self, "anno_getter", AnnotationsAccessor())
        if clz_or_func:
            self._initialize_node(self.anno_getter, clz_or_func)

    def _inititalize_node_with_annotation(
        self, anno_getter: 'AnnotationsAccessor', anno_detail: type
    ):
        if hasattr(self, "clz_or_func"):
            return
        anno_args = get_args(anno_detail)
        if anno_args:
            self._initialize_node(anno_getter, anno_args[0])
        else:
            raise NodeHasNoClzOrFunc(f"Node[{anno_detail}] has no clz_or_func parameter.")

    def _initialize_node(
        self, anno_getter: 'AnnotationsAccessor', clz_or_func: type[_T] | Callable[..., _T]
    ):
        if self.init_signature is not None:
            return

        _field_assign(self, "init_signature", inspect.signature(clz_or_func))

        _field_assign(self, "clz_or_func", _ClzOrFuncWrapper(clz_or_func))
        fields_specified = tuple(f for f in self.expose_spec if isinstance(f, str))
        maps_specified = tuple(f for f in self.expose_spec if not isinstance(f, str))
        fields_in_maps = tuple(f for m in maps_specified for f in m.keys())
        dupes, all_specified = _dupes_and_allset(fields_specified + fields_in_maps)
        if dupes:
            raise NameCollision(f"Field names have multiple specifiers {dupes!r}")

        params = self.init_signature.parameters
        init_fields = _OrderedSet(params.keys())
        if self.expose_all:
            # Add all the fields not already specified.
            all_fields = _OrderedSet(
                name
                for name in init_fields
                if name != OVERRIDE_FIELD_NAME and name not in self.exclude
            )
            fields_specified = _OrderedSet(fields_specified).union(all_fields - all_specified)

        elif self.expose_if_avail:
            all_fields = _OrderedSet(name for name in init_fields if name != OVERRIDE_FIELD_NAME)
            fields_specified = _OrderedSet(fields_specified).union(
                all_fields.intersection(self.expose_if_avail) - all_specified
            )

        expose_dict: dict[str, str] = {}
        expose_rev_dict: dict[str, Any] = {}

        # If we have a dataclass decorated class, use the __dataclass_fields__
        # to fill in this class,
        if hasattr(clz_or_func, "__dataclass_fields__"):
            for from_id in fields_specified:
                if from_id in self.preserve:
                    to_id = from_id
                else:
                    to_id = self.prefix + from_id + self.suffix
                if from_id not in init_fields:
                    raise MappedFieldNameNotFound(
                        f'Field name "{from_id}" is not an '
                        f"{clz_or_func.__name__}.__init__ parameter name"
                    )
                _update_name_map(clz_or_func, expose_dict, from_id, to_id, "Field name")
                anno_detail = self.make_anno_detail(
                    from_id,
                    clz_or_func.__dataclass_fields__[from_id],
                    anno_getter.get_annotations(clz_or_func),
                )
                _update_name_multi_map(clz_or_func, expose_rev_dict, to_id, anno_detail)

            for map_specified in maps_specified:
                # The dictionary has a set of from:to pairs.
                for from_id, to_id in map_specified.items():
                    if from_id not in init_fields:
                        raise MappedFieldNameNotFound(
                            f'Field name "{from_id}" mapped to "{to_id}" '
                            f"is not an {clz_or_func.__name__}.__init__ parameter name"
                        )
                    _update_name_map(clz_or_func, expose_dict, from_id, to_id, "Field name")
                    anno_detail = self.make_anno_detail(
                        from_id,
                        clz_or_func.__dataclass_fields__[from_id],
                        anno_getter.get_annotations(clz_or_func),
                    )
                    _update_name_multi_map(clz_or_func, expose_rev_dict, to_id, anno_detail)
        else:  # Not a dataclass type, can be a function.
            for from_id in fields_specified:
                to_id = self.prefix + from_id + self.suffix
                if from_id not in init_fields:
                    raise MappedFieldNameNotFound(
                        f'Field name "{from_id}" is not an '
                        f"{clz_or_func.__name__}.__init__ parameter name"
                    )
                _update_name_map(clz_or_func, expose_dict, from_id, to_id, "Field name")
                anno_detail = AnnotationDetails.from_init_param(from_id, params)
                _update_name_multi_map(clz_or_func, expose_rev_dict, to_id, anno_detail)

            for map_specified in maps_specified:
                # The dictionary has a set of from:to pairs.
                for from_id, to_id in map_specified.items():
                    if from_id not in init_fields:
                        raise MappedFieldNameNotFound(
                            f'Field name "{from_id}" mapped to "{to_id}" '
                            f"is not an {clz_or_func.__name__}.__init__ parameter name"
                        )
                    _update_name_map(clz_or_func, expose_dict, from_id, to_id, "Field name")
                    anno_detail = AnnotationDetails.from_init_param(from_id, params)
                    _update_name_multi_map(clz_or_func, expose_rev_dict, to_id, anno_detail)

        _field_assign(self, "expose_map", frozendict(expose_dict))
        _field_assign(self, "expose_rev_map", frozendict(expose_rev_dict))

    def make_anno_detail(self, from_id: str, dataclass_field: Field, annotations: dict[str, Any]):
        if self.default_if_missing is not MISSING_PARAM:
            if dataclass_field.default is MISSING and dataclass_field.default_factory is MISSING:
                dataclass_field = copy.copy(dataclass_field)
                dataclass_field.default = self.default_if_missing

        if from_id in annotations:
            typ = annotations[from_id]
        else:
            typ = dataclass_field.type

        # Unwrap initvars as regular field since we need to bind to the field
        # when the BoundNode is called.
        if typ is InitVar:
            typ = Any
        elif isinstance(typ, InitVar):
            args = get_args(typ)
            if args:
                typ = args[0]
            else:
                typ = Any
        # Skip ClassVar fields by unwrapping them to their underlying type
        elif _is_classvar(typ):
            typ = get_args(typ)[0] if get_args(typ) else object

        return AnnotationDetails(dataclass_field, typ)

    def get_rev_map(self) -> dict[str, Any]:
        return self.expose_rev_map

    def get_map(self) -> dict[str, Any]:
        return self.expose_map

    def __call__(self, *args: Any, **kwargs: Any) -> _T:
        # This is a type specifier, not a callable.
        # These entries are transformed into BoundNode instances at initialization.
        assert False, "Node.__call__ should not be called, this is a type specifier."


def _make_dataclass_field(
    field_obj: Field[_T], use_default: bool, node_doc: str | None
) -> tuple[Field[_T], Node[_T] | None]:
    """Creates a dataclasses Field for the given parameters.
    Args:
      field_obj: the current Field object.
      use_default: If True, the default of the Field is used otherwise the
          default is excluded.
      node_doc: The docstring for the wrapping Node field.
    """
    value_map = dict((name, getattr(field_obj, name)) for name in FIELD_FIELD_NAMES)

    # Fix docs in the metadata.
    metadata = value_map.get("metadata", None)
    metadata_docs = None if metadata is None else metadata.get(METADATA_DOCS_NAME, None)
    if metadata_docs:
        new_metadata = {METADATA_DOCS_NAME: NodeFieldMetadata(node_doc, metadata_docs)}
        new_metadata.update((k, v) for k, v in metadata.items() if k != METADATA_DOCS_NAME)
        value_map["metadata"] = new_metadata

    default_val = value_map["default"]
    if isinstance(default_val, Node):
        return field(**value_map), default_val

    if not use_default:
        value_map.pop("default", None)
        value_map.pop("default_factory", None)
    return field(**value_map), None


@dataclass
class InjectedFieldInfo:
    """The source of an injected field."""

    node_field_name: str
    node_name: str
    node: Node


@dataclass
class InjectedFieldDetails:
    """Details of an injected field and its bindings."""

    field_name: str
    sources: List[InjectedFieldInfo] = field(default_factory=list, init=False)


@dataclass
class InjectedFields:
    """Details of the injected fields and their bindings."""

    clz: type
    injections: Dict[str, InjectedFieldDetails] = field(default_factory=dict, init=False)

    def _add(self, field_name: str, details: InjectedFieldInfo):
        """Adds an instance of an injected field."""
        if not field_name:
            return
        ifd = self.injections.get(field_name, None)
        if not ifd:
            ifd = InjectedFieldDetails(field_name)
            self.injections[field_name] = ifd
        else:
            pass
        ifd.sources.append(details)

    def __str__(self) -> str:
        info = []
        field_names = sorted(self.injections.keys())
        for field_name in field_names:
            details = self.injections[field_name]
            info.append(f"{field_name}:")
            for source in details.sources:
                node = source.node
                node_field_name = source.node_field_name
                info.append(f"    {node_field_name}: {node.clz_or_func!r}")
        return "\n".join(info)

    def _deep_info_helper(self, node: Node, field_name: str, prefix: str, info: list[str]):
        prefix += "    "
        if not node.clz_or_func:
            return
        level = get_injected_fields(node.clz_or_func.clz_or_func)
        if field_name in level.injections:
            for source in level.injections[field_name].sources:
                info.append(f"{prefix}{source.node_field_name}: {source.node.clz_or_func!r}")
                self._deep_info_helper(source.node, source.node_field_name, prefix, info)

    def deep_str(self) -> str:
        """Returns a string representation of the injected fields and their
        bindings including the deeper levels of the injected fields."""
        info = []
        field_names = sorted(self.injections.keys())
        for field_name in field_names:
            details = self.injections[field_name]
            info.append(f"{field_name}: {self.clz.__name__}")
            prefix = "    "
            for source in details.sources:
                node = source.node
                node_field_name = source.node_field_name
                info.append(f"{prefix}{node_field_name}: {node.clz_or_func!r}")
                self._deep_info_helper(source.node, source.node_field_name, prefix, info)

        return "\n".join(info)

    def generate_html_page(self, url_generator: Callable[[type], str]) -> str:
        """Generates an html page containing the injected fields and their
        bindings including the deeper levels of the injected fields.
        Args:
          url_generator: A function that takes a class name and returns a string
            that can be used as a url to the class's documentation.
        """

        import html

        def _html_row(field_name: str, details: InjectedFieldDetails, is_nested: bool) -> str:
            rows = ""
            for source in details.sources:
                if not source.node.clz_or_func:
                    continue
                link = url_generator(source.node.clz_or_func.clz_or_func)
                nested_table_content = ""
                if hasattr(source.node.clz_or_func, "clz_or_func"):
                    next_level = get_injected_fields(source.node.clz_or_func.clz_or_func)
                    if source.node_field_name in next_level.injections:
                        nested_table_content = _html_row(
                            source.node_field_name,
                            next_level.injections[source.node_field_name],
                            True,
                        )
                rows += (
                    """
                <tr>
                """
                    + (
                        "<td>&nbsp;</td>"
                        if is_nested
                        else f"""    <td>{field_name}</td>
                """
                    )
                    + f"""    <td>{source.node_field_name}</td>
                    <td><a href='{link}'>{html.escape(str(source.node.clz_or_func))}</a></td>
                </tr>
                """
                )
                if nested_table_content:
                    rows += f"""
                    <tr>
                        <td colspan='3'>
                            <table>{nested_table_content}</table>
                        </td>
                    </tr>
                    """
            return rows

        docstring = inspect.getdoc(self.clz)
        if docstring:
            class_docstring = "<p>" + html.escape(docstring).replace("\n", "<br/>") + "</p>"
        else:
            class_docstring = ""

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Datatree Injected Fields for {self.clz.__name__}</title>
            <style>
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #4CAF50;
                    color: white;
                }}
            </style>
        </head>
        <body>
            <h1>Datatree Injected Fields for {self.clz.__name__}</h1>
            {class_docstring}
            <table>
                <thead>
                    <tr>
                        <th>Field Name</th>
                        <th>Node Field Name</th>
                        <th>Node Class/Func</th>
                    </tr>
                </thead>
                <tbody>
        """
        for field_name in sorted(self.injections.keys()):
            details = self.injections[field_name]
            html_content += _html_row(field_name, details, False)

        html_content += """
                </tbody>
            </table>
        </body>
        </html>
        """
        return html_content

    def __bool__(self) -> bool:
        return bool(self.injections)


def _get_injected_fields(clz: type) -> InjectedFields:
    nodes = getattr(clz, DATATREE_SENTIENEL_NAME, {})
    injected_fields = InjectedFields(clz)

    for node_name, node in nodes.items():
        if not isinstance(node, Node):
            continue
        for field_name, injected_name in node.get_map().items():
            injected_fields._add(injected_name, InjectedFieldInfo(field_name, node_name, node))
    return injected_fields


# Cache the injected fields for each class.
_INJECTED_FIELDS_CACHE: dict[type, InjectedFields] = {}


def get_injected_fields(clz: type) -> InjectedFields:
    """Returns information about the injected fields for the given class.
    This can be used to find how fields are injected and bound. In particular,
    a number of Node fields can inject the same field name. This will also
    provide all the Node fields will bind to a field.
    Args:
      clz: The class to inspect.
    """
    result = _INJECTED_FIELDS_CACHE.get(clz, None)
    if result is None:
        result = _get_injected_fields(clz)
        _INJECTED_FIELDS_CACHE[clz] = result
    return result


def _merge_field_metadata(
    existing_field: Field, new_field: Field, anno_type: Any, new_anno_type: Any
) -> Field[Any]:
    """Merges metadata from two fields, preserving existing metadata but adding docs if missing.
    Only merges docs if the annotation types match."""

    # Only merge docs if types match and existing field doesn't have docs
    if anno_type == new_anno_type:
        existing_metadata = existing_field.metadata
        if METADATA_DOCS_NAME not in existing_metadata:
            new_metadata = new_field.metadata
            if METADATA_DOCS_NAME in new_metadata:
                # Only create field_params copy if we actually need to merge
                field_params = {name: getattr(existing_field, name) for name in FIELD_FIELD_NAMES}
                if existing_metadata:
                    existing_metadata = existing_metadata.copy()
                    existing_metadata[METADATA_DOCS_NAME] = new_metadata[METADATA_DOCS_NAME]
                else:
                    existing_metadata = {METADATA_DOCS_NAME: new_metadata[METADATA_DOCS_NAME]}
                field_params["metadata"] = existing_metadata
                return field(**field_params)

    return existing_field


def _apply_node_fields(anno_getter: 'AnnotationsAccessor', clz: type) -> type:
    """Adds new fields from Node annotations."""
    annotations = anno_getter.get_annotations(clz)

    new_annos = {}  # New set of annos to build.

    # The order in which items are added to the new_annos dictionary is important.
    # Here we maintain the same order of the original with the new exposed/injected fields
    # interspersed between the Node annotated fields.
    nodes = {}
    for name, anno in annotations.items():
        # Skip ClassVar fields - they should not be processed as Node fields or have injections
        if _is_classvar(anno):
            new_annos[name] = anno
            continue

        new_annos[name] = anno
        if not hasattr(clz, name):
            anno_origin = get_origin(anno)
            anno_args = get_args(anno)
            node_clz = None
            if anno_origin and isinstance(anno_origin, type) and issubclass(anno_origin, Node):
                node_clz = anno_origin
            elif anno == Node:
                node_clz = Node

            if node_clz and len(anno_args) == 1:
                # This is a Node but the default value is not provided.
                # Use this as a short-hand way to specify a Node field.
                default_value = node_clz(anno_args[0])
                setattr(clz, name, field(default=default_value, init=False, compare=False))
            else:
                continue

        anno_default = getattr(clz, name)
        if isinstance(anno_default, Field):
            anno_default = anno_default.default
        else:
            field_params = {"default": anno_default}
            if isinstance(anno_default, Node):
                # By default don't make Node parameters initializer fields nor compare node fields.
                field_params["init"] = False
                field_params["compare"] = False
            setattr(clz, name, field(**field_params))

        if isinstance(anno_default, Node):
            # If the Node was specified without a clz_or_func parameter,
            # we complete the initialization here where we pull the clz_or_func
            # parameter from the annotation. If the Node object has already been
            # initialized, this does nothing.
            anno_default._inititalize_node_with_annotation(anno_getter, anno)  # type: ignore
            nodes[name] = anno_default
            rev_map = anno_default.get_rev_map()
            # Add the fields from the Node specification.
            for rev_map_name, anno_detail_tuple in rev_map.items():
                if rev_map_name is None:
                    continue  # Skip fields mapped to None, these are not injected.
                anno_detail = anno_detail_tuple[0]
                if rev_map_name not in new_annos:
                    new_annos[rev_map_name] = anno_detail.anno_type
                    if not hasattr(clz, rev_map_name):
                        field_default, node_default = _make_dataclass_field(
                            anno_detail.field, anno_default.use_defaults, anno_default.node_doc
                        )
                        setattr(clz, rev_map_name, field_default)
                        if node_default:
                            nodes[rev_map_name] = node_default
                else:
                    # Field already exists - check if we need to merge metadata
                    existing_field = getattr(clz, rev_map_name, None)
                    if existing_field is None:
                        # Field only exists as annotation, create a default field
                        existing_field = field()
                    if isinstance(existing_field, Field):
                        field_default, node_default = _make_dataclass_field(
                            anno_detail.field, anno_default.use_defaults, anno_default.node_doc
                        )
                        merged_field = _merge_field_metadata(
                            existing_field,
                            field_default,
                            new_annos[rev_map_name],
                            anno_detail.anno_type,
                        )
                        setattr(clz, rev_map_name, merged_field)
                        if node_default:
                            nodes[rev_map_name] = node_default
        elif isinstance(anno_default, BindingDefault):
            nodes[name] = anno_default

    clz.__annotations__ = new_annos
    del anno_getter.cache[clz]

    for bclz in clz.__mro__[-1:0:-1]:
        bnodes = getattr(bclz, DATATREE_SENTIENEL_NAME, {})
        for name, val in bnodes.items():
            if name not in nodes:
                nodes[name] = val

    setattr(clz, DATATREE_SENTIENEL_NAME, nodes)
    return clz


_Node = Node


@dataclass(frozen=True, repr=False)
class BoundNode(Generic[_T]):
    """The result of binding a Node to a class instance. Once a datatree
    object is created, all Node fields become BoundNode fields."""

    parent: object = field(compare=False)
    name: str
    node: Node[_T] = field(compare=False)
    instance_node: object = field(repr=False)
    chained_node: object = field(default=None, repr=False, compare=False)

    def chain(self, new_parent, node) -> "BoundNode[_T]":
        return BoundNode(new_parent, self.name, self.node, node, self)

    def __call__(self, *args: Any, **kwargs: Any) -> _T:
        return self._invoke(self, self.node.clz_or_func.clz_or_func, args, kwargs)

    def call_with(self, clz_or_func, *args, **kwds) -> _T:
        return self._invoke(self, clz_or_func, args, kwds)

    def call_with_alt_defaults(self, clz_or_func, *args, alt_defaults=None, **kwds) -> _T:
        return self._invoke(self, clz_or_func, args, kwds, alt_defaults)

    @classmethod
    def _invoke(cls, node, clz_or_func, args, kwds, alt_defaults=None) -> _T:
        # Resolve parameter values.
        # Priority order:
        # 1. Override (if any)
        # 2. Passed in parameters
        # 3. Parent field values
        passed_bind = node.node.init_signature.bind_partial(*args, **kwds).arguments
        ovrde = (
            node.parent.override.get_override(node.name)
            if hasattr(node.parent, "override") and node.parent.override
            else MISSING
        )
        if ovrde is not MISSING:
            ovrde_bind = ovrde.bind_signature(node.node.init_signature)

            for k, v in passed_bind.items():
                if k not in ovrde_bind:
                    ovrde_bind[k] = v

            if ovrde.clazz:
                clz_or_func = ovrde.clazz
        else:
            ovrde_bind = passed_bind

        alt_default_allow_set = node.node.ALT_DEFAULT_ALLOW_SET
        # Pull any values left from the parent or, as a final resort,
        # the alt_defaults object.
        for fr, to in node.node.expose_map.items():
            if fr not in ovrde_bind:
                val = getattr(node.parent, to)
                if (
                    val is None
                    and ((alt_default_allow_set is None) or (fr in alt_default_allow_set))
                    and hasattr(alt_defaults, to)
                ):
                    # Pull the attribute from alt_defaults if
                    # its available and otherwise we have None.
                    val = getattr(alt_defaults, to)
                ovrde_bind[fr] = val

        return clz_or_func(**ovrde_bind)

    def __repr__(self) -> str:
        return f"BoundNode(node={repr(self.node)})"


@dataclass
class Exposures:
    items: tuple = None


class Overrides:
    def __init__(self, kwds: dict[str, Any]):
        self.kwds = kwds

    def get_override(self, name: str) -> Any:
        return self.kwds.get(name, MISSING)


# Deprecated: support for this will be removed in a future release.
def override(**kwds: Any) -> Overrides:
    return Overrides(kwds)


@dataclass
class Args:
    arg: tuple[Any, ...]
    kwds: dict[str, Any]
    clazz: type | None = None

    def bind_signature(self, signature: inspect.Signature) -> dict[str, Any]:
        return signature.bind_partial(*self.arg, **self.kwds).arguments


def dtargs(*arg: Any, clazz: type | None = None, **kwds: Any) -> Args:
    return Args(arg, kwds, clazz=clazz)


def _initialize_node_instances(clz: type, instance: object):
    """Post dataclass initialization binding of nodes to instance."""
    nodes = getattr(clz, DATATREE_SENTIENEL_NAME)

    bindings: list[tuple[str, "BindingDefault[Any]"]] = []
    for name, node in nodes.items():
        # The cur-value may contain args specifically for this node.
        cur_value = getattr(instance, name)
        if isinstance(cur_value, BoundNode):
            field_value = cur_value.chain(instance, node)
        elif isinstance(cur_value, Node):
            field_value = BoundNode(instance, name, node, cur_value)
        elif isinstance(cur_value, BindingDefault):
            # Evaluate the default value after all BoundNode initializations.
            bindings.append((name, cur_value))  # type: ignore
            continue
        else:
            # Parent node has passed something other than a Node or a chained BoundNode.
            # Assume they just want to have it called.
            continue
        _field_assign(instance, name, field_value)

    # Evaluate any default values after all BoundNode initializations.
    # This allows binding functions to reference any Node fields as
    # long as the Node fields do not use bindings that not evaluated yet.
    for name, cur_value in bindings:
        field_value = cur_value.self_default(instance)
        _field_assign(instance, name, field_value)

@dataclass(frozen=True)
class Scope:
    localns: dict[str, Any] | None = None
    globalns: dict[str, Any] | None = None
    
_EMPTY_SCOPE = Scope()

@dataclass(frozen=True)
class AnnotationsAccessor:
    """A cache of type hints for classes as well as the scope to evaluate forward references.
    
    As of Python 3.12, get_type_hints are all stored as forward references. This is a helper
    class to cache the type hints and evaluate forward references.
    
    Scope is used to evaluate forward references when the class is defined in a local scope
    which means that the the forward references are not available in the global scope.
    """
    cache: dict[type, dict[str, Any]] = field(default_factory=dict)
    scope: Scope = _EMPTY_SCOPE
    
    def get_annotations(
        self, 
        clz: type) -> dict[str, Any]:
        if clz in self.cache:
            return self.cache[clz]

        scope = self.scope
        try:
            types: dict[str, Any] = get_type_hints(
                clz, 
                localns=None if scope.localns is scope.globalns else scope.localns, 
                globalns=scope.globalns)  # type: ignore
            # get_type_hints returns more than just the annotations in the original __annotations__
            # so we need to filter out the extra keys.
            result = {k: types[k] for k in clz.__annotations__.keys()}
        except Exception:
            # If we can't get the type hints, just use the original __annotations__.
            # This is a fallback for when a forward reference is used in 
            # __annotations__ but not in scope. If all the type hints can't be resolved,
            # then there may be an error later.
            result = clz.__annotations__

        self.cache[clz] = result
        return result
    
    def resolve_forward_reference(self, anno: str) -> Any:
        localsns = self.scope.localns
        if type(localsns) is not dict:
            localsns = dict(localsns)
        globalns = self.scope.globalns
        if type(globalns) is not dict:
            globalns = dict(globalns)
        return eval(anno, localsns, globalns)
    
def get_scope(frame: int = 2) -> Scope:
    try:
        defining_frame = sys._getframe(frame)
        localns: dict[str, Any] = defining_frame.f_locals
        globalns: dict[str, Any] = defining_frame.f_globals
        return Scope(localns, globalns)
    except (ValueError, AttributeError):
        return _EMPTY_SCOPE


# Provide dataclass compatiability post python 3.8.
# Default values for the dataclass function post Python 3.8.
_POST_38_DEFAULTS = dtargs(match_args=True, kw_only=False, slots=False, weakref_slot=False).kwds


def _process_datatree(
    anno_getter: AnnotationsAccessor,
    dataclass_func: Callable[[], type | tuple[Any, ...]],
    clz: type,
    init: bool,
    repr: bool,
    eq: bool,
    order: bool,
    unsafe_hash: bool,
    frozen: bool,
    match_args: bool,
    kw_only: bool,
    slots: bool,
    weakref_slot: bool,
    chain_post_init: bool,
    provide_override_field: bool
) -> type | tuple[Any, ...]:

    if provide_override_field:
        if OVERRIDE_FIELD_NAME in clz.__annotations__:
            if clz.__annotations__[OVERRIDE_FIELD_NAME] != Overrides:
                raise ReservedFieldNameException(
                    f"Reserved field name {OVERRIDE_FIELD_NAME} used by class {clz.__name__}"
                )
        else:
            clz.__annotations__[OVERRIDE_FIELD_NAME] = Overrides
            setattr(clz, OVERRIDE_FIELD_NAME, field(default=None, repr=False))

    # Move the user defined __post_init__ to __original_post_init__
    post_init_func = clz.__dict__.get("__post_init__", None)
    if post_init_func is not None:
        if not hasattr(post_init_func, DATATREE_POST_INIT_SENTIENEL_NAME):
            setattr(clz, ORIGINAL_POST_INIT_NAME, post_init_func)

    clz.__initialize_node_instances_done__ = False

    # Get InitVar fields from entire inheritance chain
    init_vars: list[str] = []
    # Go through MRO in reverse to get base class InitVars first
    for base_cls in reversed(clz.__mro__[:-1]):  # Skip object
        base_cls_annotations = anno_getter.get_annotations(base_cls)
        if base_cls_annotations:
            for name, type_hint in base_cls_annotations.items():
                if type_hint is InitVar or isinstance(type_hint, InitVar):
                    if name not in init_vars:  # Avoid duplicates
                        init_vars.append(name)

    # Create the override post_init function with proper parameter handling
    clz.__post_init__ = _create_post_init_function(
        anno_getter, clz, post_init_func, chain_post_init
    )

    _apply_node_fields(anno_getter, clz)

    # Create dict of only the post-Python 3.8 dataclass parameters that differ from defaults.
    # This ensures compatibility with older Python versions while still supporting newer parameters
    # when they're explicitly set to non-default values.
    values_post_38 = dtargs(
        match_args=match_args, kw_only=kw_only, slots=slots, weakref_slot=weakref_slot
    ).kwds
    values_post_38_differ = dict(
        ((k, v) for k, v in values_post_38.items() if v != _POST_38_DEFAULTS[k])
    )

    return dataclass_func(
        clz,  # type: ignore
        init=init,
        repr=repr,
        eq=eq,
        order=order,
        unsafe_hash=unsafe_hash,
        frozen=frozen,
        **values_post_38_differ,
    )
    
def scoped_datatree(
        clz: Optional[type[_T]] = None,
        init: bool = True,
        repr_: bool = True,
        eq: bool = True,
        order: bool = False,
        unsafe_hash: bool = False,
        frozen: bool = False,
        match_args: bool = True,
        kw_only: bool = False,
        slots: bool = False,
        weakref_slot: bool = False,
        chain_post_init: bool = False,
        provide_override_field: bool = False,
        anno_getter: AnnotationsAccessor = AnnotationsAccessor(),
    ) -> Callable[[type[_T]], type[_T]]:
    """A version of the datatree decorator (not intended to be used directly
    as a decorator) that allows for the local and global scope of the class being decorated to be
    passed in via the anno_getter parameter.
    
    This allows for the datatree decorator to be used in another decorator (like xdatatrees)
    that needs to know the scope of the class being decorated. 
    """

    return _process_datatree(
        anno_getter,
        dataclass,
        clz,
        init,
        repr_,
        eq,
        order,
        unsafe_hash,
        frozen,
        match_args,
        kw_only,
        slots,
        weakref_slot,
        chain_post_init,
        provide_override_field,
    )


if TYPE_CHECKING:

    @dataclass_transform(
        init_default=True,
        repr_default=True,
        eq_default=True,
        order_default=False,
        unsafe_hash_default=False,
        frozen_default=False,
        field_specifiers=(Field, field, dtfield, Node, BindingDefault),
    )
    def datatree(
        clz: Optional[type[_T]] = None,
        /,
        *,
        init: bool = True,
        repr_: bool = True,
        eq: bool = True,
        order: bool = False,
        unsafe_hash: bool = False,
        frozen: bool = False,
        match_args: bool = True,
        kw_only: bool = False,
        slots: bool = False,
        weakref_slot: bool = False,
        chain_post_init: bool = False,
        provide_override_field: bool = False
    ) -> Callable[[type[_T]], type[_T]]:
        
        anno_getter = AnnotationsAccessor(scope=get_scope(2))

        def wrap(clz):
            return _process_datatree(
                anno_getter,
                dataclass,
                clz,
                init,
                repr_,
                eq,
                order,
                unsafe_hash,
                frozen,
                match_args,
                kw_only,
                slots,
                weakref_slot,
                chain_post_init,
                provide_override_field
            )

        # See if we're being called as @datatree or @datatree().
        if clz is None:
            # We're called with parens.
            return wrap

        # We're called as @datatree without parens.
        return wrap(clz)

else:

    def datatree(
        clz: Optional[type[_T]] = None,
        /,
        *,
        init: bool = True,
        repr_: bool = True,
        eq: bool = True,
        order: bool = False,
        unsafe_hash: bool = False,
        frozen: bool = False,
        match_args: bool = True,
        kw_only: bool = False,
        slots: bool = False,
        weakref_slot: bool = False,
        chain_post_init: bool = False,
        provide_override_field: bool = False
    ) -> Callable[[type[_T]], type[_T]]:
        """Python decorator similar to dataclasses.dataclass providing parameter injection,
        injection, binding and overrides for parameters deeper inside a tree of objects.
        Args:
            clz: The class to decorate.
            init: If True, a __init__ method will be generated.
            repr_: If True, a __repr__ method will be generated.
            eq: If True, __eq__ and __ne__ methods will be generated.
            order: If True, __lt__, __le__, __gt__, and __ge__ methods will be generated.
            unsafe_hash: If True, a __hash__ method will be generated.
            frozen: If True, the class is made immutable.
            match_args: If True, the generated __init__ method will accept only the parameters
                that are defined in the class.
            kw_only: If True, the generated __init__ method will accept only keyword arguments.
            slots: If True, the class will be a slots class.
            chain_post_init: If True, the __post_init__ method will chain the post init methods
                of the base classes.
            provide_override_field: If True, the class will provide an override field that can be
                used to provide overrides for the Node fields
        """

        anno_getter = AnnotationsAccessor(scope=get_scope(2))

        def wrap(clz):
            return _process_datatree(
                anno_getter,
                dataclass,
                clz,
                init,
                repr_,
                eq,
                order,
                unsafe_hash,
                frozen,
                match_args,
                kw_only,
                slots,
                weakref_slot,
                chain_post_init,
                provide_override_field,
            )

        # See if we're being called as @datatree or @datatree().
        if clz is None:
            # We're called with parens.
            return wrap

        # We're called as @datatree without parens.
        return wrap(clz)


@dataclass(frozen=True)
class _PostInitClasses:
    """
    mro_index: the index of the class in the MRO
    post_init_func: the post-init function
    post_init_name: the name of the post-init function in the current class
    fields: the fields of the base class
    """

    mro_index: int
    post_init_func: Callable | None
    post_init_name: str
    fields: dict[str, tuple[Field, "_PostInitParameter"]]


@dataclass(frozen=True)
class _PostInitParameter:
    """
    name: the field name
    is_in_self: from the final class clz's viewpoint, is this a normal field
                stored on self or an InitVar that won't appear on self?
    """

    name: str
    is_in_self: bool


def _is_initvar(ann_type: Any) -> bool:
    """
    Returns True if 'ann_type' is exactly 'InitVar' or 'InitVar[...]'.
    """
    return ann_type is InitVar or isinstance(ann_type, InitVar)


def _is_classvar(ann_type: Any) -> bool:
    """
    Returns True if 'ann_type' is exactly 'ClassVar' or 'ClassVar[...]'.
    """
    return get_origin(ann_type) is ClassVar


def _get_post_init_parameter_map(
    anno_getter: 'AnnotationsAccessor',
    clz: type,
    post_init_new_name: str,
    post_init_orig_name: str,
) -> dict[int, list[_PostInitParameter]]:
    """
    Returns a map of all the post-init parameters for a class and its
    base classes.
    """
    fields: dict[str, tuple[Field, _PostInitParameter]] = {}
    dataclass_parents: list[_PostInitClasses] = []

    for i, b in tuple(enumerate(clz.__mro__))[-2:0:-1]:
        orig_post_init_func = b.__dict__.get(post_init_new_name, None)
        override_post_init_func = b.__dict__.get(post_init_orig_name, None)
        base_dataclass_fields = getattr(b, "__dataclass_fields__", None)
        base_fields: dict[str, tuple[Field, _PostInitParameter]] = {}
        if base_dataclass_fields is not None:
            for f in base_dataclass_fields.values():
                v: tuple[Field, _PostInitParameter] = (
                    f,
                    _PostInitParameter(f.name, f._field_type is not _FIELD_INITVAR),
                )
                if not v[1].is_in_self:
                    base_fields[f.name] = v
                fields[f.name] = v
            if orig_post_init_func is not None:
                # This is a datatree class with a renamed __post_init__ function.
                # When chaining we will pass initvar parameters to this post-init function.
                dataclass_parents.append(
                    _PostInitClasses(i, orig_post_init_func, post_init_new_name, base_fields)
                )

            elif override_post_init_func is not None and not hasattr(
                override_post_init_func, DATATREE_POST_INIT_SENTIENEL_NAME
            ):
                # The base class has a __post_init__ and is a dataclass (not a datatree).
                # When chaining we can pass initvar parameters to this post-init function.
                dataclass_parents.append(
                    _PostInitClasses(i, override_post_init_func, post_init_orig_name, base_fields)
                )
        elif override_post_init_func is not None:
            # The base class has a __post_init__ function but is not a dataclass.
            # When chaining we can call this function without any parameters.
            dataclass_parents.append(
                _PostInitClasses(i, override_post_init_func, post_init_orig_name, {})
            )

    cls_annotations = anno_getter.get_annotations(clz)

    for name, typ in cls_annotations.items():
        # Skip ClassVar fields - they are not instance fields
        if _is_classvar(typ):
            continue
        fields[name] = (None, _PostInitParameter(name, not _is_initvar(typ)))

    result: dict[int, tuple[list[_PostInitParameter], str]] = {}
    for post_init_class in dataclass_parents:
        b = clz.__mro__[post_init_class.mro_index]
        post_init_params: list[_PostInitParameter] = (
            [
                fields[f.name][1]
                for f in b.__dataclass_fields__.values()
                if f._field_type is _FIELD_INITVAR
            ]
            if hasattr(b, "__dataclass_fields__")
            else []
        )
        result[post_init_class.mro_index] = (post_init_params, post_init_class.post_init_name)

    result[0] = ([t[1] for t in fields.values() if not t[1].is_in_self], post_init_new_name)

    return result


def _create_chain_post_init_text(
    anno_getter: 'AnnotationsAccessor',
    clz: type,
    post_init_new_name: str,
    post_init_orig_name: str,
    chain_post_init: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Creates a chain of post-init functions for a class.
    This assumes that the post-init functions are moved to another entry in the same class
    named post_init_name.

    The advantage of this approach is that the post-init functions are called without
    repitition in case of diamond inheritance. If each class has a post-init function
    that calls the post-init function of the next class in the chain, then the post-init
    function of the deepest class will be called multiple times.
    """
    locals = {"clz": clz}
    mapping = _get_post_init_parameter_map(
        anno_getter, clz, post_init_new_name, post_init_orig_name
    )
    header_text = []
    body_text = []
    params_derived: list[_PostInitParameter] = mapping.get(0, ([], ""))[0]
    pnames = ("self",) + tuple(p.name for p in params_derived if not p.is_in_self)

    header_text.append(f"def {post_init_orig_name}({', '.join(pnames)}):")
    body_text.append("    mro = clz.__mro__")
    if chain_post_init:
        for mro_index, (params, funcname) in mapping.items():
            if mro_index == 0:
                continue
            names = ("self",) + tuple(f"self.{p.name}" if p.is_in_self else p.name for p in params)
            body_text.append(
                f"    mro[{mro_index}].{funcname}({', '.join(names)})"
                f" # {clz.__mro__[mro_index].__name__}"
            )

    # Call the original post-init function if it exists as post_init_name.
    if post_init_new_name in clz.__dict__:
        body_text.append(f"    mro[0].{post_init_new_name}({', '.join(pnames)})")
    elif not chain_post_init:
        # Find the post-init function in MRO order. Here we don't call all the post-init functions.
        # We just call the first one we find which is the way the dataclass works. However,
        # here we also fix the signature of the post-init.
        for mro_index in range(1, len(clz.__mro__)):
            if mro_index in mapping:
                params, funcname = mapping[mro_index]
                names = ("self",) + tuple(
                    f"self.{p.name}" if p.is_in_self else p.name for p in params
                )
                body_text.append(
                    f"    mro[{mro_index}].{funcname}({', '.join(names)})"
                    f" # {clz.__mro__[mro_index].__name__}"
                )
                break

    return locals, header_text, body_text


def _create_post_init_function(
    anno_getter: AnnotationsAccessor,
    clz: type,
    wrap_fn: Callable[[Any], None] | None = None,
    chain_post_init: bool = False,
) -> Callable[[Any], None]:
    """Creates a custom __post_init__ function with named parameters."""

    if clz.__module__ in sys.modules:
        globals = sys.modules[clz.__module__].__dict__
    else:
        globals = {}

    locals, header_text, body_text = _create_chain_post_init_text(
        anno_getter, clz, ORIGINAL_POST_INIT_NAME, "__post_init__", chain_post_init
    )

    wrap_decorator = []
    if wrap_fn is not None:
        wrap_decorator = ["@wraps(wapped_function)"]

    init_code = [
        "    if not self.__initialize_node_instances_done__:",
        "        _field_assign(self, '__initialize_node_instances_done__', True)",
        "        _initialize_node_instances(clz, self)",
    ]

    header_lines = wrap_decorator + header_text
    body_lines = init_code + body_text

    # Create the function using existing _create_fn
    local_vars = {
        "wraps": wraps,
        "wapped_function": wrap_fn,
        "_field_assign": _field_assign,
        "_initialize_node_instances": _initialize_node_instances,
    }

    all_locals = {**locals, **local_vars}

    override_post_init: Callable[[Any], None] = _create_fn(
        "__post_init__", header_lines, body_lines, locals=all_locals, globals=globals
    )

    # Mark the function as a datatree generatedpost-init function
    setattr(override_post_init, DATATREE_POST_INIT_SENTIENEL_NAME, True)
    return override_post_init


def _create_fn(
    name: str,
    header_lines: list[str],
    body_lines: list[str],
    *,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
) -> Callable[[Any], None]:
    """Creates a function dynamically.

    Args:
        name: Function name
        header_lines: List of function header lines
        body_lines: List of function body lines
        globals: Global namespace
        locals: Local namespace
    """
    if locals is None:
        locals = {}
    if globals is None:
        globals = {}

    local_vars = ", ".join(locals.keys())

    # Convert body lines to properly indented string
    body = "\n".join(f"    {line}" for line in header_lines + body_lines)

    func_text = f"def __create_fn__({local_vars}):\n{body}\n    return {name}"

    # Create the function
    exec_locals: dict[str, Any] = {}
    # Uncomment to debug.
    # print("\n" * 3)
    # print(f"# {locals['clz'].__name__}")
    # print(func_text)
    # print("\n" * 3)
    exec(func_text, globals, exec_locals)

    function = exec_locals["__create_fn__"](**locals)

    return function
