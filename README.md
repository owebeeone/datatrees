# Datatrees

A wrapper to Python's dataclasses for simplifying class composition with automatic field 
injection, binding, self-defaults and more.

Datatrees is particularly useful for composing a class from other classes or functions
in a hierarchical manner, where fields from classes deeper in the hierarchy need to be
propagated as root class parameters. The boilerplate code for such a composition
is often error-prone and difficult to maintain. The impetus for this library came
from building hierarchical 3D models where each node in the hierarchy collected fields
from nodes nested deeper in the hierarchy. Using datatrees, almost all the boilerplate
management of model parameters was eliminated, resulting in clean and maintainable
3D model classes.

## Installation

```bash
pip install datatrees
```

## Core Features

- **Field Injection and Binding**: Automatically inject fields from other classes or functions
- **Field Mapping**: Map fields between classes with custom naming
- **Self-Defaulting**: Fields can default based on other fields
- **Field Documentation**: Field documentation is preserved through the injection chain
- **Post-Init Chaining**: Automatically chain inherited __post_init__ functions
- **Type Annotations**: Typing support for static type checkers and shorthands for Node[T]

Exports:

- **datatree**: The decorator for creating datatrees akin to dataclasses.dataclass()
- **dtfield**: The decorator for creating fields akin to dataclasses.field()
- **Node**: The class for creating node factories.
- **field_docs**: The function for getting the documentation for a datatree field
- **get_injected_fields**: Produces documentation on how fields are injected and bound

## Basic Usage

The "Node[T]" annotation is used to indicate that the field is used to inject fields from a class or parameters from a function. The default value (an instance of a Node) contains options on how the fields are injected, namely prefix, suffix etc. If the default value is not specified, the a Node object will be created with the T parameter used as the class or function to inject e.g. the following are equivalent:

### Various ways to specify a Node[T]

```python
class A:
    a: int = 1

class B:
    a: Node[A] = Node(A)

# The following shorthand declarations are available in datatrees v0.1.9 and later.
class C:
    a: Node[A] # Shorthand for Node(A)

class D:
    a: Node[A] = Node('a') # Shorthand for Node(A, 'a')

class E:
    a: Node[A] = dtfield(init=False) # Shorthand for dtfield(Node(A), init=False)
```

Notably, in the shorthand declarations, the annotation arg is used to specify the class to inject if it is not already specified. (This feature is only availble for datatrees v0.1.9 and later)

Here's an example showing how datatrees can simplify configuration for a database connection pool:

```python
from datatrees import datatree, Node, dtfield

@datatree
class RetryPolicy:
    max_attempts: int = 3
    delay_ms: int = 1000
    exponential_backoff: bool = True
    
    def get_delay(self, attempt: int) -> int:
        if self.exponential_backoff:
            return self.delay_ms * (2 ** (attempt - 1))
        return self.delay_ms

@datatree
class ConnectionConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "mydb"
    username: str = "user"
    password: str = "pass"
    timeout_ms: int = 5000
    
    def get_connection_string(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@datatree
class ConnectionPool:
    # Inject all fields from ConnectionConfig and RetryPolicy
    connection: Node[ConnectionConfig] = Node(ConnectionConfig, prefix="db_")  # All fields will be injected and prefixed with db_
    retry: Node[RetryPolicy] # default value is Node(RetryPolicy)
    
    min_connections: int = 5
    max_connections: int = 20
    
    # Self-defaulting field that depends on other fields
    connection_string: str = dtfield(
        self_default=lambda self: self.connection().get_connection_string(),
        init=False  # Won't appear in __init__ (default is False for self_default)
    )
    
    def __post_init__(self):
        print(f"Initializing pool: {self.connection_string}")
        print(f"Pool size: {self.min_connections}-{self.max_connections}")
        print(f"Retry policy: {self.max_attempts} attempts, starting at {self.delay_ms}ms")

# Usage
pool = ConnectionPool(
    db_host="db.example.com",      # Prefixed field from ConnectionConfig
    db_port=5432,                  # Prefixed field from ConnectionConfig
    max_attempts=5,                # Field from RetryPolicy
    delay_ms=200,                  # Field from RetryPolicy
    min_connections=10             # Direct field
)

# Access injected fields
assert pool.db_host == "db.example.com"
assert pool.max_attempts == 5

# Access the Node directly to create a ConnectionConfig instance
config = pool.connection()
assert config.host == "db.example.com"
assert config.port == 5432

# Use the self-defaulting field
assert "db.example.com:5432" in pool.connection_string

# Use methods from injected classes
retry_delay = pool.retry().get_delay(2)  # Gets exponential delay for 2nd attempt
```

This example demonstrates:
1. Field injection from multiple source classes
2. Field prefixing for clarity
3. Self-defaulting fields that compute values
4. Node fields that can create instances
5. Method access on both the composite and component classes

## Field Mapping

You can control how fields are mapped between classes:

```python
@datatree
class Source:
    value_a: int = 1
    value_b: int = 2
    value_c: int = 3

@datatree
class Target:
    # Map value_a to a, value_b to b
    source: Node[Source] = Node(Source, 
        'value_a',           # Direct mapping to same name
        {'value_b': 'b'},    # Map value_b to b
        prefix='src_'        # Prefix all unmapped fields
        # Note, value_c is not mapped and will not be injected
    )

target = Target(src_value_a=10, b=20)
assert target.src_value_a == 10  # Prefixed mapping
assert target.b == 20            # Renamed mapping

source = target.source()
assert source.value_a == 10
assert source.value_b == 20
assert source.value_c == 3

source = target.source(value_b=-1) # passed parameters override injected fields
assert source.value_a == 10
assert source.value_b == -1
assert source.value_c == 3


```

## Self-Defaulting Fields

Fields can have defaults that depend on other fields:

```python
@datatree(frozen=True)
class Rectangle:
    width: int = 10
    height: int = 20
    area: int = dtfield(self_default=lambda self: self.width * self.height)

rect = Rectangle(width=5)
assert rect.area == 100  # Calculated after initialization
```

## Post-Init Chaining

The `chain_post_init` parameter allows proper initialization of inherited classes. When enabled, the `__post_init__` methods are called in reverse MRO (Method Resolution Order) order (i.e least derived class first).

In complex multiple-inheritance or “diamond” inheritance scenarios, each class in the MRO is initialized only once, so repeated classes in the inheritance graph do not result in multiple calls to the same `__post_init__`.

```python
@datatree(chain_post_init=True)
class Base:
    def __post_init__(self):
        print("Base init")

@datatree(chain_post_init=True)
class Child(Base):
    def __post_init__(self):
        print("Child init")

# Prints:
# Base init
# Child init
child = Child()
```

For multiple inheritance, the order follows Python's MRO:

```python
@datatree(chain_post_init=True)
class A:
    def __post_init__(self):
        print("A init")

@datatree(chain_post_init=True)
class B:
    def __post_init__(self):
        print("B init")

@datatree(chain_post_init=True)
class C(A, B):
    def __post_init__(self):
        print("C init")

# Prints:
# B init
# A init
# C init
c = C()
```

Here's an example of diamond inheritance where Base.post_init is called only once 
even though it is inherited by both Left and Right.

```python
@datatree
class Base:
    def __post_init__(self):
        print("Base init")

@datatree(chain_post_init=True)
class Left(Base):
    def __post_init__(self):
        print("Left init")

@datatree(chain_post_init=True)
class Right(Base):
    def __post_init__(self):
        print("Right init")

@datatree(chain_post_init=True)
class Diamond(Left, Right):
    def __post_init__(self):
        print("Diamond init")

# Prints:
# Base init
# Left init
left = Left()

# Prints:
# Base init
# Right init
right = Right()

# Prints:
# Base init    # Base.__post_init__ is called only once
# Right init
# Left init
# Diamond init
d = Diamond()
```

## Node Configuration

The Node class supports several configuration options:

```python
Node(
    class_or_func,          # Class or function to bind
    *field_names,           # Direct field mappings
    prefix='',              # Prefix for injected fields
    suffix='',              # Suffix for injected fields
    expose_all=False,       # Expose all fields
    preserve=None,          # Fields to preserve without prefix/suffix
    expose_if_avail=None,   # Fields to expose if they exist
    exclude=(),             # Fields to exclude
    node_doc=None,          # Documentation for the node
)
```

Node can only inject fields/parameters that are in the constructor of the class or function. Other dataclass fields are ignored.

class_or_func can be a class or a function. The parameters to the function or the class are injected as fields in the injected class. If it is a datatree class, those fields metadata is preserved unless overridden by a preeceeding field with the same name.

To explicitly expose a field, simply include it in the field_names or a mapping dictionary if the name is to be explicitly mapped. e.g. If no fields are nominated, all fields are injected. To inject no fields, pass an empty map.

```python
 s: Node[Source] = Node(Source, 'field_a', 'field_b', {'field_c': 'c', 'field_d': 'd'})
```

If expose_all is True, all fields are injected even if they are not nominated or mapped.

If expose_if_avail is set, and the field is available in the constructor it is injected.

If preserve is set, the field names are preserved in the injected class except if it explicitly mapped.

If exclude is set, the fields in the exclude list are not injected.


## Field Documentation

Documentation is preserved through the injection chain:

```python
@datatree
class Source:
    value: int = dtfield(1, "The source value")

@datatree
class Target:
    source: Node[Source] = Node(node_doc="Source configuration")
    
# Documentation is preserved and combined
assert field_docs(Target(), 'value') == "Source configuration: The source value"
```

## Deprecated Features

### Override Field (Deprecated)

The override field functionality is deprecated and disabled by default. If needed, it can be enabled with:

```python
@datatree(provide_override_field=True)
class Example:
    ...
```

This feature allowed runtime modification of Node parameters but is being phased out in favor of more explicit configuration through Node parameters.

## Advanced Features

### Type Safety

Datatrees Node fields can be typed using TypeVar and Generic.

```python
from typing import TypeVar, Generic

T = TypeVar('T')

@datatree
class Container(Generic[T]):
    value: T
    processor: Node[T] = Node(lambda x: x * 2)

container = Container[int](value=10, x=10)
assert container.value == 10
assert container.processor() == 20
```

### Self-Defaults

Fields can be provided a lambda or function where self is passed as the first parameter.

Self-default fields are initialized after the regular dataclass initialization has completed
and in the order of the fields in the class definition. 

```python
@datatree
class Advanced:
    base: int = 10
    computed: int = dtfield(
        self_default=lambda self: self.base * 2,
        init=False  # By default, self_default fields are init=False
    )
```

### Function Binding

Nodes can also bind to functions:

```python
def process(x: int = 1, y: int = 2):
    return x + y

@datatree
class Processor:
    x: int = 10
    processor: Node = Node(process, 'x', {'y': 'y_value'})
    
    def __post_init__(self):
        result = self.processor()  # Uses x=10, y=2
```

### Dataclass InitVar Fields

Dataclass InitVar fields are supported by datatree including with chain_post_init=True.

The InitVar fields are passed to the __post_init__ method as parameters. Chaining post_init
will require that the InitVar fields that are expected by the parent classes are passed
correctly. If IniVar fields are shadowed by non IniVar fields of the same name, the 
field will be taken from self and passed to the parent class.

Although it is allowed to override a regular field with an InitVar field, it will cause 
runtime errors when chaining post_init functions that expect the field to be an instance 
member of self.

```python
@datatree
class GrandBase:
    ga: InitVar[int]
    gb: float
    def __post_init__(self, ga):
        print(f"GrandBase ga={ga}")

@datatree
class Parent(GrandBase):
    pc: int
    def __post_init__(self, ga):
        print(f"Parent self.pc={self.pc}")

@datatree(chain_post_init=True)
class Child(Parent):
    gc: InitVar[int]
    cc: str
    def __post_init__(self, ga, gc):
        print(f"Child ga={ga}, gc={gc}, self.cc={self.cc}")

# prints:
# GrandBase ga=10
# Parent self.pc=True
# Child ga=10, gc=100, self.cc=hello
c = Child(gb=1.2, ga=10, pc=True, gc=100, cc="hello")

```

### Node and InitVar

The Node class can be used to inject InitVar fields but the InitVar fields will be
injected as non-InitVar fields otherwise it would not be possible to retrieve them
when the Node factory is called.

```python
@datatree
class Leaf:
    ga: InitVar[int]
    gb: int
    def __post_init__(self, ga):
        print(f"Leaf ga={ga}")

@datatree
class Child:
    leaf: Node[Leaf] = Node(Leaf) # ga is injected as a non-InitVar field

# prints:
# Leaf ga=10
child = Child(ga=10, gb=20)
assert child.gb == 20
assert child.ga == 10

# prints:
# Leaf ga=10
leaf = child.leaf()
assert leaf.gb == 20
# ga is not available on leaf
assert not hasattr(leaf, 'ga')
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GNU General Public License v2.1 - see the LICENSE file for details.
```
