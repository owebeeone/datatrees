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

- **datatree**: The decorator for creating datatrees akin to dataclasses.dataclass(). It accepts all standard `dataclasses.dataclass` arguments (e.g., `init`, `repr`, `eq`, `order`, `frozen`, `unsafe_hash`, `match_args`, `kw_only`, `slots`, `weakref_slot`) in addition to datatrees-specific parameters like `chain_post_init`.
- **dtfield**: The decorator for creating fields akin to dataclasses.field()
- **Node**: The class for creating node factories. **IMPORTANT**: When accessed on an instance, a Node field is itself a callable factory that produces new instances of the target type on each invocation. For example, if `obj.node_field` is a Node[SomeClass], then `obj.node_field()` creates and returns a new `SomeClass` instance each time it's called.
- **field_docs**: The function for getting the documentation for a datatree field
- **get_injected_fields**: Produces documentation on how fields are injected and bound

## Datatrees as a Domain-Specific Composition API

### The Challenge of Complex Object Composition

Traditional Python object composition often leads to verbose, error-prone boilerplate code. Consider a typical manual approach:

```python
# Without datatrees - verbose and error-prone
class DatabaseConfig:
    def __init__(self, host="localhost", port=5432, database="mydb", 
                 username="user", password="pass", timeout_ms=5000):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.timeout_ms = timeout_ms

class RetryPolicy:
    def __init__(self, max_attempts=3, delay_ms=1000, exponential_backoff=True):
        self.max_attempts = max_attempts
        self.delay_ms = delay_ms
        self.exponential_backoff = exponential_backoff

class ConnectionPool:
    def __init__(self, host="localhost", port=5432, database="mydb",
                 username="user", password="pass", timeout_ms=5000,
                 max_attempts=3, delay_ms=1000, exponential_backoff=True,
                 min_connections=5, max_connections=20):
        # Manually forwarding all parameters - error prone!
        self.config = DatabaseConfig(host, port, database, username, password, timeout_ms)
        self.retry = RetryPolicy(max_attempts, delay_ms, exponential_backoff)
        self.min_connections = min_connections
        self.max_connections = max_connections
```

This approach has several problems:
- Parameter duplication across constructors
- Manual parameter forwarding is error-prone
- No clear visual hierarchy of composition
- Difficult to maintain as requirements change

### Datatrees: A Predictable Pattern for Composition

Datatrees provides a declarative, consistent pattern that acts as a **Domain-Specific API (DSAPI)** for object composition:

```python
# With datatrees - declarative and maintainable
@datatree
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "mydb"
    username: str = "user"
    password: str = "pass"
    timeout_ms: int = 5000

@datatree
class RetryPolicy:
    max_attempts: int = 3
    delay_ms: int = 1000
    exponential_backoff: bool = True

@datatree
class ConnectionPool:
    config: Node[DatabaseConfig] = Node(DatabaseConfig, prefix="db_")
    retry: Node[RetryPolicy]
    min_connections: int = 5
    max_connections: int = 20
```

### Benefits for Developers

1. **Reduced Boilerplate**: No manual `__init__` methods or parameter forwarding
2. **Clear Composition Hierarchy**: Visual structure shows how components relate
3. **Automatic Parameter Management**: Fields are automatically injected and managed
4. **Consistent Patterns**: Every datatree class follows the same predictable structure
5. **Self-Documenting**: The structure itself documents the composition relationships

### Benefits for AI and LLMs

The predictable patterns created by datatrees are particularly valuable for AI-assisted development:

1. **Pattern Recognition**: LLMs excel at recognizing and replicating consistent patterns. Datatrees provides a clear, repeatable structure that LLMs can easily learn and apply.

2. **Reduced Ambiguity**: The declarative syntax limits the "search space" for code generation, leading to more accurate outputs:
   ```python
   # LLMs can reliably predict this pattern:
   pool = ConnectionPool(
       db_host="prod.example.com",     # Prefix clearly indicates origin
       db_port=5432,                   # Consistent naming pattern
       max_attempts=5,                 # Direct injection from RetryPolicy
       min_connections=10              # Local field
   )
   ```

3. **Inferrable Usage**: The structure makes it clear how to interact with objects:
   ```python
   # LLMs can infer this usage from the pattern:
   config = pool.config()          # Node fields are callable factories
   retry_policy = pool.retry()     # Consistent access pattern
   ```

4. **Fewer Hallucinations**: The well-defined structure reduces the likelihood of LLMs generating incorrect boilerplate or inventing non-existent parameters.

5. **Composition Understanding**: LLMs can easily understand and suggest appropriate compositions based on the Node field patterns.

By adopting datatrees, you're not just writing cleaner code for humans – you're creating a codebase that's inherently more understandable and predictable for AI tools, leading to better code suggestions, more accurate refactoring, and reduced errors in AI-generated code.

## Basic Usage

The "Node[T]" annotation is used to indicate that the field is used to inject fields from a class or parameters from a function. **Crucially, Node fields become callable factories after initialization - you must call them with parentheses `()` to get a new instance of the wrapped type.** The default value (an instance of a Node) contains options on how the fields are injected, namely prefix, suffix etc. If the default value is not specified, the a Node object will be created with the T parameter used as the class or function to inject e.g. the following are equivalent:

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
# Note: 'connection' and 'retry' Node fields are not in the constructor (init=False by default)

# Access injected fields
assert pool.db_host == "db.example.com"
assert pool.max_attempts == 5

# Access the Node directly to create a ConnectionConfig instance
# IMPORTANT: Each call to pool.connection() creates a NEW ConnectionConfig instance
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

### Understanding Node Fields as Factories

A critical aspect of Node fields is that they are callable factories that create new instances on each invocation. Here's a demonstration:

```python
@datatree
class Counter:
    count: int = 0
    
    def increment(self):
        self.count += 1

@datatree
class Container:
    counter: Node[Counter] = Node(Counter)

# Create a container
container = Container()

# Each call to counter() creates a NEW Counter instance
counter1 = container.counter()
counter2 = container.counter()

# They are different objects
assert counter1 is not counter2

# Modifying one doesn't affect the other
counter1.increment()
assert counter1.count == 1
assert counter2.count == 0  # Still 0!

# You can pass overrides when calling the factory
counter3 = container.counter(count=10)
assert counter3.count == 10
assert counter1.count == 1  # Unchanged
assert counter2.count == 0  # Unchanged
```

This factory behavior is essential to understand: Node fields don't store a single instance; they store a factory that creates new instances with the injected parameters.

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
        # Note, value_c is not mapped and will not be injected because it is not nominated.
    )

target = Target(src_value_a=10, b=20)
assert target.src_value_a == 10  # Prefixed mapping
assert target.b == 20            # Renamed mapping

# IMPORTANT: Call source() to create a Source instance
source = target.source()
assert source.value_a == 10
assert source.value_b == 20
assert source.value_c == 3

# You can override values when calling the factory
source = target.source(value_b=-1)  # passed parameters override injected fields
assert source.value_a == 10
assert source.value_b == -1
assert source.value_c == 3

# You can still provide `value_c` when calling the Node factory even though it was not injected:
source = target.source(value_c=4)
assert source.value_c == 4
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

**Note**: Self-default fields are initialized in a separate phase after regular initialization. They can access any regular fields or Node fields, but can only access other self_default fields defined before them. See the [Self-Defaults](#self-defaults) section for detailed ordering rules.

## Post-Init Chaining

The `chain_post_init` parameter allows proper initialization of inherited classes. When enabled, the `__post_init__` methods are called in reverse MRO (Method Resolution Order) order (i.e least derived class first).

In complex multiple-inheritance or "diamond" inheritance scenarios, each class in the MRO is initialized only once, so repeated classes in the inheritance graph do not result in multiple calls to the same `__post_init__`.

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

For multiple inheritance, the order follows Python's MRO (in reverse):

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
# Base init    <-- Base.__post_init__ is called only once
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
    use_defaults=True,      # Use defaults from the source class/function
    prefix='',              # Prefix for injected fields
    suffix='',              # Suffix for injected fields
    expose_all=False,       # Expose all fields
    preserve=None,          # Fields to preserve without prefix/suffix
    expose_if_avail=None,   # Fields to expose if they exist
    exclude=(),             # Fields to exclude
    node_doc=None,          # Documentation for the node
    default_if_missing=MISSING # Default value if an injected field lacks one (e.g. None)
)
```

Node can only inject fields/parameters that are in the constructor of the class or function. Other dataclass fields are ignored.

class_or_func can be a class or a function. The parameters to the function or the class are injected as fields in the injected class. If it is a datatree class, those fields metadata is preserved unless overridden by a preeceeding field with the same name.

To explicitly expose a field, simply include it in the field_names or a mapping dictionary if the name is to be explicitly mapped. e.g. If no fields are nominated, all fields are injected. To inject no fields, pass an empty map.

```python
 s: Node[Source] = Node(Source, 'field_a', 'field_b', {'field_c': 'c', 'field_d': 'd'})
```

If `use_defaults` is `True` (the default), default values from the source class or function are used for injected fields. If `False`, these defaults are ignored (unless a value is provided via `default_if_missing` or the field is explicitly initialized).

If expose_all is True, all fields are injected even if they are not nominated or mapped.

If expose_if_avail is set, and the field is available in the constructor it is injected.

If preserve is set, the field names are preserved in the injected class except if it explicitly mapped.

If exclude is set, the fields in the exclude list are not injected.

If `default_if_missing` is set (e.g. to `None`), injected fields that do not have a default value will be assigned this value. This is useful for ensuring that all injected fields have a defined value, even if the source class or function does not provide a default. Furthermore, this feature helps to avoid errors reported by dataclasses regarding the order of fields (fields without default values must precede fields with default values). When injecting fields from multiple classes, it can be impossible to satisfy this ordering requirement without duplicating and manually defaulting each field; `default_if_missing` provides a cleaner solution to this problem.

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

### Default init=False for Self-Default and Node Fields

By default, both self_default fields and Node fields have `init=False`, meaning they don't appear as parameters in the generated `__init__` method. This is an intentional safety feature.

**Why this default exists:**
- Self-default fields depend on other fields in their defining class
- Node fields are factories that bind to fields in their defining class
- When these fields are injected into a composing class via Node:
  - The fields they depend on might have different names (due to prefixes/mappings)
  - The fields they depend on might not be injected at all
  - The dependencies become fragile and can break with seemingly unrelated changes

**Living Dangerously - Overriding init=False:**

You can override this default with `dtfield(init=True)`, but this should be done with caution:

```python
@datatree
class Config:
    base_value: int = 10
    # This self_default depends on base_value
    computed: int = dtfield(
        self_default=lambda self: self.base_value * 2,
        init=True  # Living dangerously! This field can now be injected
    )

@datatree
class SafeComposer:
    config_node: Node[Config] = Node(Config)  # All fields injected with same names
    
# This works because base_value is injected with the same name
safe = SafeComposer(base_value=20)
assert safe.config_node().computed == 40

@datatree  
class DangerousComposer:
    # Injecting with prefix - computed field will be injected but broken!
    config_node: Node[Config] = Node(Config, prefix="cfg_")
    
# This will fail! The injected computed field looks for self.base_value
# but only self.cfg_base_value exists
dangerous = DangerousComposer(cfg_base_value=20)
# dangerous.cfg_computed  # This self_default will fail with AttributeError

@datatree
class ExtraDangerous:
    # Only injecting computed, not base_value
    config_node: Node[Config] = Node(Config, 'computed')
    
# The computed field is injected but will fail when evaluated
extra = ExtraDangerous()
# extra.computed.self_default(extra)  # AttributeError: no base_value!
```

**When it might be safe to use init=True:**
- The self_default only depends on fields that are guaranteed to be injected with the same names
- You control all composing classes and can ensure the dependencies remain valid
- The Node field itself doesn't have complex internal dependencies

**Best Practice:** Keep the default `init=False` for self_default and Node fields unless you have a specific need and understand the risks. If you need to initialize these fields, it's often safer to do so explicitly in `__post_init__` or by calling the Node factory directly.

### Understanding __post_init__ in Datatrees

Datatrees overrides the `__post_init__` method to perform its own initialization before calling your user-defined `__post_init__`. This ensures proper initialization order for all datatree features.

**Initialization Order:**

1. **Regular field initialization** (handled by dataclasses)
2. **Datatrees __post_init__ override**:
   - Converts Node fields to BoundNode factories
   - Evaluates self_default fields in definition order
   - Parent user defined `__post_init__` functions in reverse MRO order (if `chain_post_init=True`)
   - User-defined `__post_init__` (if provided)
   (Note how the parent datatrees `__post_init__` functions are not called.)

```python
@datatree
class Example:
    regular_field: int = 10
    node_field: Node[Config] = Node(Config)
    computed: int = dtfield(self_default=lambda self: self.regular_field * 2)
    
    def __post_init__(self):
        # At this point:
        # - regular_field is initialized (value: 10)
        # - node_field is a BoundNode factory (callable)
        # - computed has been evaluated (value: 20)
        
        print(f"Regular field: {self.regular_field}")
        print(f"Computed field: {self.computed}")
        print(f"Node field is callable: {callable(self.node_field)}")
        
        # You can safely use Node fields here
        config = self.node_field()
        print(f"Created config: {config}")

# When Example() is instantiated:
# 1. regular_field = 10 (dataclass init)
# 2. datatrees converts node_field to BoundNode
# 3. datatrees evaluates computed = 20
# 4. User's __post_init__ runs and prints values
```

**Important Implications:**

1. **Node fields are ready to use in __post_init__**: They've already been converted to callable factories
2. **Self-default fields are already evaluated**: Their values are set before your __post_init__ runs
3. **You can't prevent datatrees initialization**: Even if you define __post_init__, datatrees will still do its initialization first

**With chain_post_init=True:**

```python
@datatree
class Base:
    def __post_init__(self):
        print("Base __post_init__")
        self.calls = ["Base"]

@datatree(chain_post_init=True)
class Child(Base):
    child_node: Node[Config] = Node(Config)
    
    def __post_init__(self):
        print("Child __post_init__")
        # self.calls already exists from Base.__post_init__
        self.calls.append("Child")
        
# Initialization order:
# 1. All fields initialized
# 2. Datatrees initialization (Node binding, self_defaults)
# 3. Base.__post_init__() 
# 4. Child.__post_init__()

child = Child()
print(child.calls)  # ["Base", "Child"]
```

**Technical Note:** Datatrees achieves this by renaming your `__post_init__` to another name and creating its own `__post_init__` that calls yours after completing its initialization tasks.

### Type Safety

Datatrees Node fields can be typed using TypeVar and Generic.

```python
from typing import TypeVar, Generic

T = TypeVar('T')

@datatree
class Container(Generic[T]):
    value: T
    processor: Node[T] = Node(lambda x: x * 2)  # Injects field x

container = Container[int](value=10, x=10)
assert container.value == 10
assert container.processor() == 20  # Note the () call!
```

### Self-Defaults

Fields can be provided a lambda or function where self is passed as the first parameter.

Self-default fields are initialized in a separate phase **after** all regular fields and Node fields have been initialized. They are then initialized in the order of their definition in the class.

**Important Ordering Rules**:
- Self-default fields can access **any** regular fields or Node fields, regardless of definition order
- Self-default fields can only access **other self-default fields** that are defined before them
- When calling a Node field from within a self-default, if that Node's class contains self-default fields, those will be initialized following the same rules (transitive closure constraint)

```python
@datatree
class Advanced:
    base: int = 10
    computed: int = dtfield(
        self_default=lambda self: self.base * 2,
        init=False  # By default, self_default fields are init=False
    )
    
@datatree
class OrderingExample:
    # Regular fields - all initialized first
    a: int = 1
    z: int = 100  # Defined last but accessible to all self_defaults
    
    # Self-default fields - initialized in order after regular fields
    b: int = dtfield(self_default=lambda self: self.a + self.z)  # Can access any regular field
    c: int = dtfield(self_default=lambda self: self.b + 1)       # Can access b (defined before)
    # d: int = dtfield(self_default=lambda self: self.e)         # Would fail! e is a self_default defined later
    e: int = dtfield(self_default=lambda self: self.z * 2)       # Can access z (regular field)
    
@datatree
class Config:
    value: int = 10
    formatted: str = dtfield(self_default=lambda self: f"Value: {self.value}")

@datatree  
class NodeOrderingExample:
    # Regular and Node fields - all initialized first
    multiplier: int = 2
    config: Node[Config] = Node(Config)
    
    # Self-default fields - can access any regular/Node field
    result: int = dtfield(
        self_default=lambda self: self.config().value * self.multiplier,
        init=False  # This is implied for self_default fields - shown here for illustration.
    )
    
    # When config() is called above, Config's self_default fields are initialized
    # following the same ordering rules within that instance
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
        result = self.processor()  # Uses x=10, y=2 - Note the () call!
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
leaf = child.leaf()  # Note the () call!
assert leaf.gb == 20
# ga is not available on leaf
assert not hasattr(leaf, 'ga')
```

## Serializing

### Json

`datatrees` is compatible with the popular `dataclasses-json` library for easy serialization to and from JSON.

- [dataclasses-json on PyPI](https://pypi.org/project/dataclasses-json/)
- [dataclasses-json on GitHub](https://github.com/lidatong/dataclasses-json)

### XML

For robust XML serialization and deserialization, `datatrees` integrates with `xdatatrees`, a library from the same author designed for this purpose.

- [xdatatrees on PyPI](https://pypi.org/project/xdatatrees/)
- [xdatatrees on GitHub](https://github.com/owebeeone/xdatatrees)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GNU General Public License v2.1 - see the LICENSE file for details.

## Advanced Example: A Composable LLM Prompt Builder

The following example demonstrates how `datatrees` can be used to build a sophisticated, maintainable system. It shows how to create a "Domain-Specific API" for generating Large Language Model (LLM) prompts by composing smaller, reusable components.

This approach elegantly solves the problem of managing dozens of prompt parameters by organizing them into a clear, hierarchical structure, which `datatrees` then presents as a simple, flat API to the end-user.

<details>
<summary>Click to see the full LLM Prompt Builder example</summary>

```python
# To run this example:
# 1. Install the datatrees library: pip install datatrees
# 2. Save this code as a Python file (e.g., prompt_builder.py) and execute it.

import textwrap
from datatrees import datatree, Node, dtfield

# --- 1. Define Reusable Prompt Component Classes ---
# Each class represents a logical part of the prompt and knows how to build
# its own text block.

@datatree
class Persona:
    """Defines the persona the LLM should adopt."""
    role: str = dtfield(
        "an expert assistant",
        doc="The role the LLM should play (e.g., 'a senior Python developer')."
    )
    tone: str = dtfield(
        "helpful and concise",
        doc="The desired tone for the response (e.g., 'formal', 'casual')."
    )

    def build(self) -> str:
        """Builds the persona text block."""
        return f"Your role is {self.role}. Respond with a {self.tone} tone."

@datatree
class TaskDefinition:
    """Defines the core task for the LLM."""
    objective: str = dtfield(
        None,
        doc="A clear and specific goal for the task."
    )
    context: str = dtfield(
        "",  # Optional context
        "Any relevant background information or context."
    )

    def build(self) -> str:
        """Builds the task definition text block."""
        if self.objective is None:
            raise ValueError("objective is a required field.")
        text = f"Objective: {self.objective}"
        if self.context:
            text += f"\nContext: {self.context}"
        return text

@datatree
class FormatInstructions:
    """Defines the output format."""
    output_style: str = dtfield(
        "a well-structured markdown document",
        "The desired style of the output (e.g., 'JSON', 'a bulleted list')."
    )
    constraints: str = dtfield(
        "do not use jargon",
        "Any constraints or negative constraints."
    )

    def build(self) -> str:
        """Builds the formatting instructions text block."""
        return f"Provide the response as {self.output_style}.\nConstraint: {self.constraints}."


# --- 2. Define the Master Prompt Composer Class ---
# This class uses `Node` to compose the components. Its `build` method
# orchestrates the final prompt assembly.

@datatree
class GeneratedPrompt:
    """
    A fully parameterized prompt class that composes persona,
    task, and formatting components.
    """
    # Node fields inject parameters from the component classes and become
    # callable factories for creating instances of those components.
    persona_setup: Node[Persona] = Node(Persona)
    task_setup: Node[TaskDefinition] = Node(TaskDefinition)
    format_setup: Node[FormatInstructions] = Node(FormatInstructions)

    def build(self) -> str:
        """
        Builds the final prompt by calling the build() method
        on each configured component instance.
        """
        # Create instances of each component by calling the Node factories.
        # The parameters provided to GeneratedPrompt's constructor are
        # automatically passed to the correct factory.
        persona = self.persona_setup()
        task = self.task_setup()
        formatting = self.format_setup()

        # Assemble the final prompt from the built components.
        prompt = f"""
        ### Persona ###
        {persona.build()}

        ### Task ###
        {task.build()}

        ### Output Format ###
        {formatting.build()}
        """
        # textwrap.dedent removes common leading whitespace from multiline strings.
        return textwrap.dedent(prompt).strip()


# --- 3. Main Execution Block ---
# Demonstrates how to use the GeneratedPrompt class.

if __name__ == "__main__":
    print("--- Example 1: Designing a Database Schema ---")

    # Instantiate the master prompt class. Parameters from all components
    # are provided directly to the constructor.
    db_design_prompt = GeneratedPrompt(
        role="a senior database architect",
        tone="professional and direct",
        objective="Design a schema for a multi-tenant application.",
        context="The application needs to support up to 10,000 tenants.",
        output_style="a SQL script with comments",
        constraints="use PostgreSQL syntax and include foreign key constraints"
    )

    # Call the build() method to get the final, formatted prompt string.
    final_prompt_string = db_design_prompt.build()
    print(final_prompt_string)

    print("\n" + "="*50 + "\n")

    print("--- Example 2: Writing a Python Function ---")

    # Create another prompt with completely different parameters.
    python_function_prompt = GeneratedPrompt(
        role="a senior Python developer specializing in data processing",
        tone="clear and educational",
        objective="Write a Python function that takes a list of strings and returns a list of unique, sorted strings.",
        context="The function should be efficient and handle an empty list as input.",
        output_style="a single Python code block with a docstring",
        constraints="do not use any external libraries like pandas"
    )

    final_prompt_string_2 = python_function_prompt.build()
    print(final_prompt_string_2)
```
</details>

### How This Example Shows the Power of Datatrees

*   **Creates a Simple API for a Complex Task**: The `GeneratedPrompt` class is a Domain-Specific API. An end-user only needs to instantiate it with a flat list of parameters. They don't need to know how the final prompt is assembled or that `Persona` or `TaskDefinition` classes even exist.
*   **Encapsulation**: Each component class (`Persona`, etc.) is responsible for its own logic and can be tested or modified in isolation.
*   **Predictability and Discoverability**: A user (or an LLM) can inspect the `GeneratedPrompt` class and immediately understand all the available parameters for building a prompt, making the system highly predictable and easy to use.
*   **Maintainability**: If you need to add a new part to the prompt (e.g., an `ExampleOutput` section), you simply create a new component class and add it as a `Node` to `GeneratedPrompt`. The existing code remains unchanged.


## To Dos

- The default_if_missing feature of Node would not be needed if we could move parameter order with inherited classes. Unfortunately dataclass traps this issue and we can't get around it without reimplementing dataclass. Maybe we need proposal here. TBD

- Rather than overriding the user's `__post_init__` function, it would be better if we could have dataclass call a `__pre_post_init__` function. Needs a proposal.
