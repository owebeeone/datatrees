"""
Wrapper over Python's dataclass that allows for the composition of classes
by injecting constructor parameters or function parameters into a datatree
annotated class with a Node type hint.
"""

from .datatrees import *

from .datatrees import (
    datatree,
    dtargs,
    override,
    Node,
    BoundNode,
    dtfield,
    field_docs,
    BindingDefault,
    get_injected_fields,
    _field_assign,
    _PostInitParameter,
    _get_post_init_parameter_map,
    _create_chain_post_init_text,
    _create_post_init_function,
    _apply_node_fields,
)

__version__ = "0.1.0"
__all__ = [
    "datatree",
    "dtargs", 
    "override",
    "Node",
    "BoundNode",
    "dtfield",
    "field_docs",
    "BindingDefault",
    "get_injected_fields",
    "_PostInitParameter",
    "_field_assign",
    "_get_post_init_parameter_map",
    "_create_chain_post_init_text",
    "_create_post_init_function",
    "_apply_node_fields",
] 