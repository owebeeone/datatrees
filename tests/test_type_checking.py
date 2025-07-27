# tests/test_type_checking.py

from __future__ import annotations
from typing import TYPE_CHECKING

# Assuming datatree and dtfield are imported from your library
from datatrees import datatree, dtfield, Node
from dataclasses import InitVar

# --- Test Case 1: Basic Datatree with init parameters ---


@datatree
class SimpleObject:
    a: int
    b: str
    c: float = 3.14 # Has a default
    

@datatree
class SimpleObject2:
    d: int
    node: Node[SimpleObject] = Node(SimpleObject)
    
@datatree
class SimpleObject3:
    v: int
    v2: int = dtfield(self_default=lambda self: self.v * 2)

def test_simple_object_init() -> None:
    # Pylance/MyPy should now recognize these parameters
    obj1 = SimpleObject(a=1, b="hello", c=2.71)
    # This should now NOT be flagged by Pylance
    obj2 = SimpleObject(a=10, b="world") # c should implicitly use its default
    
    obj3 = SimpleObject2(d=1, a=2, b=3)
    
    obj4 = SimpleObject3(v=1)

    # Type checker should report error for missing required arg 'a'
    if TYPE_CHECKING:
        # Expected: Type checker error (missing 'a')
        # This line should ideally show a red underline in VS Code/MyPy
        # If this is run by MyPy, we expect an error here.
        obj3 = SimpleObject(b="no_a") # type: ignore[call-arg] # Added to allow MyPy to pass, but the error is the point

        # Expected: Type checker error (incorrect type for 'a')
        # This line should ideally show a red underline
        obj4 = SimpleObject(a="wrong_type", b="test") # type: ignore[arg-type]

    # Verify runtime behavior (optional, as this is a type-checking test)
    assert obj1.a == 1
    assert obj1.b == "hello"
    assert obj1.c == 2.71
    assert obj2.c == 3.14


# --- Test Case 2: Datatree with dtfield(init=False) ---

@datatree
class ComputedValue:
    base: int
    computed: int = dtfield(self_default=lambda self: self.base * 2, init=False)

def test_computed_value_init() -> None:
    # 'base' should be an init parameter, 'computed' should NOT
    cv1 = ComputedValue(base=5)
    assert cv1.base == 5
    assert cv1.computed == 10

    if TYPE_CHECKING:
        # Expected: Type checker error (unexpected keyword argument 'computed')
        # This line should ideally show a red underline
        cv2 = ComputedValue(base=1, computed=2) # type: ignore[call-arg]


# --- Test Case 3: Node and InitVar (from your docs) ---
@datatree
class Leaf:
    ga: InitVar[int] # Using dataclasses.InitVar as per your docs
    gb: int
    def __post_init__(self, ga: int):
        # In runtime, this confirms ga is passed
        self._pi_ga = ga

    
def test_leaf_init_var_handling() -> None:
    leaf_instance = Leaf(ga=10, gb=20)
    assert leaf_instance._pi_ga == 10
    assert leaf_instance.gb == 20

@datatree
class Child:
    # Here, 'leaf' is a Node field, expected to be init=False
    leaf: Node[Leaf] = dtfield(Node(Leaf), init=False)
    # As per your docs, 'ga' is injected as a non-InitVar field on Child
    # So Child *should* have 'ga' as an init parameter.
    ga: int
    gb: int # From Leaf
    cc: str

def test_node_init_var_handling() -> None:
    # Pylance/MyPy should understand 'ga' is an init parameter for Child
    child_instance = Child(ga=10, gb=20, cc="hello")
    assert child_instance.ga == 10
    assert child_instance.gb == 20
    assert child_instance.cc == "hello"

    # Accessing the Node's callable
    leaf_instance = child_instance.leaf(ga=10, gb=20) # Node's __call__ might need args, depends on Node(Leaf)'s config
    assert leaf_instance.gb == 20
    # assert not hasattr(leaf_instance, 'ga') # As per your docs, ga is not on leaf instance

    if TYPE_CHECKING:
        # Expected: Type checker error (missing required arguments)
        # Missing 'ga', 'gb', 'cc' for Child
        bad_child = Child() # type: ignore[call-arg]

        # Expected: Type checker error (unexpected keyword argument 'leaf')
        # 'leaf' should not be an init parameter if dtfield(init=False) is used
        bad_child_with_leaf = Child(ga=1, gb=2, cc="x", leaf=Node(Leaf)) # type: ignore[call-arg]