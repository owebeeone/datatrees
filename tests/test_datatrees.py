"""
Created on 8 Dec 2021

@author: gianni
"""

import unittest
from datatrees import datatree, dtargs, override, Node, dtfield, field_docs, get_injected_fields
from dataclasses import dataclass, field, Field
import builtins
from typing import Any, ClassVar


@datatree
class LeafType1:
    leaf_a: float = 1
    leaf_b: float = 2


@datatree(provide_override_field=True)
class LeafType2:
    leaf_a: float = 10
    leaf_b: float = 20


@datatree
class LeafType3:
    leaf_a: float = 11
    leaf_b: float = 22


@datatree
class LeafType4:
    leaf_a: float = 111
    leaf_b: float = 222


# Check for support of non dataclass/datatree types.
class LeafType5:
    def __init__(self, a=1111, b=2222):
        self.a = a
        self.b = b

    def __eq__(self, other):
        if isinstance(other, LeafType5):
            return self.a == other.a and self.b == other.b
        return False


@datatree(provide_override_field=True)
class Overridable:
    leaf_a: float = 53  # Overrides the default value for all classes.

    # Only the nominated fields are mapped and leaf1_b
    leaf1: Node[LeafType1] = Node(LeafType1, "leaf_a", {"leaf_b": "leaf1_b"})
    leaf1a: Node[LeafType1] = Node(LeafType1, "leaf_a", {"leaf_b": "leaf1a_b"})

    leaf2: Node[LeafType2] = Node(LeafType2)  # All fields are mapped.
    leaf3: Node[LeafType3] = Node(LeafType3, {})  # No fields are mapped.
    leaf4: Node[LeafType4] = Node(LeafType4, use_defaults=False)  # Default values are mapped from this.
    leaf5: Node[LeafType5] = Node(LeafType5)

    def __post_init__(self):
        self.l1 = self.leaf1(leaf_a=99)
        self.l1a = self.leaf1a()
        self.l2 = self.leaf2()
        self.l3 = self.leaf3()
        self.l4 = self.leaf4()
        self.l5 = self.leaf5(b=3333)


OVERRIDER1 = Overridable(
    leaf_a=3,
    leaf1_b=44,
    override=override(leaf1=dtargs(leaf_b=7)),
)


class Test(unittest.TestCase):
    def test_l1(self):
        self.assertEqual(OVERRIDER1.l1, LeafType1(leaf_a=99, leaf_b=7))

    def test_l1a(self):
        self.assertEqual(OVERRIDER1.l1a, LeafType1(leaf_a=3, leaf_b=2))

    def test_l2(self):
        self.assertEqual(OVERRIDER1.l2, LeafType2(leaf_a=3, leaf_b=20))

    def test_l3(self):
        self.assertEqual(OVERRIDER1.l3, LeafType3(leaf_a=11, leaf_b=22))

    def test_l4(self):
        self.assertEqual(OVERRIDER1.l4, LeafType4(leaf_a=3, leaf_b=20))

    def test_l5(self):
        self.assertEqual(OVERRIDER1.l5, LeafType5(a=1111, b=3333))

    def test_inherits(self):
        @dataclass
        class A:
            a: int = 1

        @datatree
        class B(A):
            b: int = 2

        ab = B(10, 20)
        self.assertEqual(ab.a, 10)
        self.assertEqual(ab.b, 20)

    def test_name_map(self):
        @datatree
        class A:
            anode: Node = dtfield(Node(LeafType1, {"leaf_a": "aa"}, expose_all=True), init=True)

            def __post_init__(self):
                self.lt1 = self.anode()

        ao = A()
        self.assertEqual(ao.lt1, LeafType1())
        self.assertEqual(ao.aa, LeafType1().leaf_a)
        self.assertEqual(ao.leaf_b, LeafType1().leaf_b)

    def test_ignore_default_bad(self):
        try:

            @datatree
            class A:
                anode: Node = dtfield(Node(LeafType1, use_defaults=False), init=True)

            self.fail("Expected field order issue.")
        except TypeError:
            pass

    def test_additive_default(self):
        @datatree
        class A:
            anode: Node = dtfield(Node(LeafType1), init=True)
            leaf_a: float = 51
            leaf_b: float

        lt1 = A().anode()

        self.assertEqual(lt1, LeafType1(51, 2))

    def test_inheritance(self):
        @datatree
        class A:
            a: float = 1
            leaf: Node = dtfield(Node(LeafType2), init=True)
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A")

        @datatree(chain_post_init=True)
        class B(A):
            b: float = 1
            leaf: Node = dtfield(Node(LeafType2), init=True)
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("B")

        self.assertEqual(B().s, ["A", "B"])
        self.assertEqual(B().leaf(), LeafType2(leaf_a=10, leaf_b=20, override=None))

    def test_multiple_inheritance(self):
        @datatree(chain_post_init=True)
        class A1:
            a1: float = 1
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A1")

        @datatree(chain_post_init=True)
        class A2:
            a2: float = 1
            leaf: Node = dtfield(Node(LeafType2), init=True)
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A2")

        @datatree(chain_post_init=True)
        class B(A1, A2):
            b: float = 1
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("B")

        self.assertEqual(B().s, ["A2", "A1", "B"])
        self.assertEqual(B().leaf(), LeafType2(leaf_a=10, leaf_b=20, override=None))

    def test_multiple_inheritance_mix_dataclass_datatree(self):
        @datatree(chain_post_init=True)
        class A1:
            a1: float = 1
            leaf: Node = dtfield(Node(LeafType2), init=True)
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A1")

        @datatree(chain_post_init=True)
        class A2:
            a2: float = 1
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A2")

        @datatree(chain_post_init=True)
        class B(A1, A2):
            b: float = 1
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("B")

        self.assertEqual(B().s, ["A2", "A1", "B"])
        self.assertEqual(B().leaf(), LeafType2(leaf_a=10, leaf_b=20, override=None))

    def test_multiple_inheritance_mix_dataclass_datatree_no_pi(self):
        @datatree(chain_post_init=True)
        class A1:
            a1: float = 1
            leaf: Node[LeafType2] = dtfield(Node(LeafType2), init=True)
            s: list[Any] = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A1")

        @datatree(chain_post_init=True)
        class A2:
            a2: float = 1
            s: list[Any] = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A2")

        @datatree(chain_post_init=True)
        class B(A1, A2):
            bx: float = 1
            s: list[Any] = field(default_factory=lambda: list())
        
        @datatree(chain_post_init=True)
        class C(B):
            bx: float = 1

            def __post_init__(self):
                self.s.append("C")

        self.assertEqual(C().s, ["A2", "A1", "C"])
        self.assertEqual(C().leaf(), LeafType2(leaf_a=10, leaf_b=20, override=None))

    def test_multiple_inheritance_no_post_init_no_chain(self):
        class A:
            def do_thing(self, s: list[Any], v: str):
                s.append(v)

        @dataclass
        class B(A):
            b: float = 1
            s: list[Any] = field(default_factory=lambda: list())

            def __post_init__(self):
                self.do_thing(self.s, "B")

        @datatree
        class C(B):
            b: float = 1

        self.assertEqual(C().s, ["B"])

    def test_function(self):
        al: list[str] = []
        bl: list[str] = []

        def func(a: str = "a", b: str = "b"):
            al.append(a)
            bl.append(b)

        @datatree
        class A:
            b: str = "clzA-b"
            funcNode: Node[None] = dtfield(Node(func), init=True)

        A().funcNode()
        self.assertEqual(al, ["a"])
        self.assertEqual(bl, ["clzA-b"])

    def test_prefix_node(self):
        al: list[str] = []
        bl: list[str] = []

        def func(a: str = "a", b: str = "b"):
            al.append(a)
            bl.append(b)

        @datatree
        class A:
            fb: str = "clzA-b"
            funcNode: Node[None] = dtfield(Node(func, prefix="f"), init=True)

        A().funcNode()
        self.assertEqual(al, ["a"])
        self.assertEqual(bl, ["clzA-b"])

    def test_nested_node(self):
        @datatree
        class A:
            a1: float = 1
            leaf: Node = dtfield(Node(LeafType2), init=True)
            s: list = field(default_factory=lambda: list())

            def __post_init__(self):
                self.s.append("A")

        @datatree
        class B:
            node_A: Node[A] = dtfield(Node(A), init=True)

            def __post_init__(self):
                self.s.append("B")

        @datatree
        class C:
            node_B: Node = Node(B)

            def __post_init__(self):
                self.s.append("C")

        c = C()
        self.assertEqual(c.leaf(), LeafType2(leaf_a=10, leaf_b=20, override=None))
        self.assertEqual(c.s, ["C"])
        c.node_B()
        self.assertEqual(c.s, ["C", "B"])
        c.node_A()
        self.assertEqual(c.s, ["C", "B", "A"])

    def test_preserve(self):
        @datatree
        class A:
            a: int = 1
            b: int = 2
            keep1: int = 3
            keep2: int = 4

        # Names keep1 and keep2 are preserved.
        @datatree
        class B:
            nodeA: Node = Node(A, prefix="aa_", preserve={"keep1", "keep2"})
            a_obj: A = None

            def __post_init__(self):
                self.a_obj = self.nodeA()

        self.assertEqual(B(), B(aa_a=1, aa_b=2, keep1=3, keep2=4))

    def test_if_avail(self):
        @datatree
        class A:
            a: int = 1
            b: int = 2
            keep1: int = 3
            keep2: int = 4

        # Name keep1 is exposed even if not specified.
        @datatree
        class B:
            nodeA: Node = Node(
                A, "a", {"b": "bb"}, prefix="aa_", expose_if_avail={"keep1", "NotThere"}
            )
            a_obj: A = None

            def __post_init__(self):
                self.a_obj = self.nodeA()

        self.assertEqual(B(), B(aa_a=1, bb=2, aa_keep1=3))
        self.assertEqual(A(a=11, b=44, keep1=33), B(aa_a=11, bb=44, aa_keep1=33).a_obj)
        self.assertFalse(hasattr(B(), "aa_b"))
        self.assertFalse(hasattr(B(), "aa_keep2"))

    def test_exposed_node(self):
        s = []

        def f(a: int = 3):
            s.append(a)

        @datatree
        class A:
            a: int = 1
            f_node: Node = dtfield(Node(f), init=True)

            def thing(self):
                self.f_node()

        @datatree
        class B:
            nodeA: Node = dtfield(Node(A, "f_node"), init=True)
            a_obj: A = None

            def __post_init__(self):
                self.a_obj = self.nodeA()

        b = B()
        b.a_obj.f_node()
        self.assertEqual(b.a_obj, A(a=1))

        b.f_node(a=4)
        self.assertEqual(s, [1, 4])

    def test_exposed_node_different_names(self):
        s = []

        def f(a: int = 3):
            s.append(a)

        @datatree
        class A:
            a: int = 1
            f_node: Node = dtfield(Node(f), init=True)

            def thing(self):
                self.f_node()

        @datatree
        class B:
            nodeA: Node = dtfield(Node(A, "f_node", {"a": "a1"}, expose_all=True), init=True)
            a_obj: A = None

            def __post_init__(self):
                self.a_obj = self.nodeA()

        b = B()
        b.a_obj.f_node()
        self.assertEqual(b.a_obj, A(a=1))

        b.f_node(a=b.a1)  # TODO: Use mapping to automatically find a in b.
        self.assertEqual(s, [1, 1])

    def test_other_bound_nodes(self):
        s1 = []

        def f1(a: int = 3):
            s1.append(a)

        s2 = []

        def f2(a: int = 3):
            s2.append(a)

        @datatree
        class A:
            a: int = 1
            f1_node: Node = dtfield(Node(f1), init=True)

            def thing(self):
                self.f1_node()

        A().thing()
        self.assertEqual(s1, [1])
        self.assertEqual(s2, [])

        # If neither a Node or a BoundNode is passed as a node, it is just called.
        A(f1_node=f2).thing()
        self.assertEqual(s1, [1])
        self.assertEqual(s2, [3])

    def test_document_field(self):
        @datatree
        class A:
            a: int = dtfield(1, "the a field")
            ax: int = dtfield(1, "the ax field")

        @datatree
        class B:
            b: int = dtfield(1, "the b field")
            a_node: Node = Node(A, node_doc="A node doc")
            a_node2: Node = dtfield(
                Node(A, node_doc="A node2 doc", prefix="a2_", expose_all=True), "the a_node2 field"
            )

        b_value = B(a=2, ax=3, b=4)

        self.assertEqual(b_value.a, 2)
        self.assertEqual(b_value.ax, 3)
        self.assertEqual(b_value.b, 4)

        self.assertEqual(field_docs(b_value, "a"), "A node doc: the a field")
        self.assertEqual(field_docs(b_value, "ax"), "A node doc: the ax field")
        self.assertEqual(field_docs(b_value, "b"), "the b field")
        self.assertEqual(field_docs(b_value, "a_node"), None)
        self.assertEqual(field_docs(b_value, "a2_a"), "A node2 doc: the a field")
        self.assertEqual(field_docs(b_value, "a2_ax"), "A node2 doc: the ax field")
        self.assertEqual(field_docs(b_value, "a_node2"), "the a_node2 field")

    def test_binding_field(self):
        @datatree
        class A:
            a: int = 1
            c: int = dtfield(self_default=lambda s: s.a + s.b, init=True)
            b: int = 2

        self.assertEqual(A().c, 3)
        self.assertEqual(A(a=3).c, 5)
        self.assertEqual(A(a=3, b=4).c, 7)
        self.assertEqual(A(c=77).c, 77)

    def test_inherited_binding_field(self):
        @datatree
        class A:
            a: int = 1
            c: int = dtfield(self_default=lambda s: s.a + s.b, init=True)
            b: int = 2

        @datatree
        class B(A):
            a: int = 2

        self.assertEqual(B().c, 4)

    def test_injected_binding_field(self):
        @datatree
        class A:
            a: int = 1
            c: int = dtfield(self_default=lambda s: s.a + s.b, init=True)
            b: int = 2

        @datatree
        class B(A):
            a: int = 3
            node: Node = Node(A)

        self.assertEqual(B().c, 5)
        self.assertEqual(B().node().c, 5)
        self.assertEqual(B(c=44).node().c, 44)

    def test_injected_binding_field_init_false(self):
        @datatree
        class A:
            a: int = 1
            c: int = dtfield(self_default=lambda s: s.a + s.b, init=False)
            b: int = 2

        self.assertEqual(A().c, 3)

    def test_bound_node_self_default_order(self):
        @datatree
        class A:
            a: int = 7
            c: int = dtfield(self_default=lambda s: s.b(), init=False)
            b: Node = Node(lambda a: a * 2)

        self.assertEqual(A().c, 14)

    def test_self_default_with_injected(self):
        @datatree
        class A:
            a: int = 7
            c: int = dtfield(self_default=lambda s: s.a * 2, init=True)

        @datatree
        class B:
            a_node: Node = Node(A, prefix="prefix_")

        self.assertEqual(B().a_node().c, 14)
        self.assertEqual(A().c, 14)
        self.assertEqual(B().prefix_a, 7)
        self.assertEqual(B().prefix_c.self_default(B().a_node()), 14)

    def test_get_injected_fields(self):
        @datatree
        class A:
            a: int = 7
            c: int = 5

        @datatree
        class B:
            a_node: Node = Node(A, prefix="prefix_")

        @datatree
        class C:
            a_node: Node = Node(A, {"a": "a", "c": "a"})

        def f(x: int = 0, y: int = 1):
            return x + y

        @datatree
        class D:
            a_node: Node = Node(A)
            b_node: Node = Node(B)
            c_node: Node = Node(C)
            f_node: Node = Node(f)

        injected_a = get_injected_fields(A)
        injected_b = get_injected_fields(B)
        injected_c = get_injected_fields(C)
        injected_d = get_injected_fields(D)

        self.assertEqual(len(injected_a.injections), 0)
        self.assertEqual(len(injected_b.injections), 2)

        self.assertEqual(injected_b.injections.keys(), {"prefix_a", "prefix_c"})

        self.assertEqual(injected_c.injections.keys(), {"a"})

        self.assertEqual(len(injected_c.injections["a"].sources), 2)

        self.assertEqual(str(injected_b), "prefix_a:\n    a: A\nprefix_c:\n    c: A")

        self.assertEqual(str(injected_c), "a:\n    a: A\n    c: A")

        self.assertEqual(
            str(injected_d),
            "a:\n    a: A\n    a: C\nc:\n    c: A\n"
            "prefix_a:\n    prefix_a: B\nprefix_c:\n    prefix_c: B\n"
            "x:\n    x: f\ny:\n    y: f",
        )

        self.assertEqual(
            injected_d.deep_str(),
            "a: D\n    a: A\n    a: C\n        a: A\n        c: A\n"
            "c: D\n    c: A\n"
            "prefix_a: D\n    prefix_a: B\n        a: A\n"
            "prefix_c: D\n    prefix_c: B\n        c: A\n"
            "x: D\n    x: f\n"
            "y: D\n    y: f",
        )

    def test_equal(self):
        @datatree(frozen=True)
        class A:
            value: tuple = dtfield(default=(0, 0, 0, 1), compare=True)

            def __init__(self, value: tuple) -> None:
                builtins.object.__setattr__(self, "value", value)

        self.assertNotEqual(A((1, 2, 3, 6)), A((1, 2, 3, 4)))

    def test_short_hand_node_annotation(self):
        @datatree
        class A:
            a: int = 2

        @datatree
        class B:
            a_node: Node[A]  # This should be equivalent to a: Node[A] = Node(A)

        self.assertEqual(B().a_node(), A(a=2))

    def test_short_hand_node_annotation_with_default_value(self):
        @datatree
        class A:
            a: int = 2

        @datatree
        class B:
            a_node: Node[A] = Node("a")  # Equivalent to: Node[A] = Node(A, 'a')

    def test_short_hand_node_annotation_with_field_with_no_default_value(self):
        @datatree
        class A:
            a: int = 4

        @datatree
        class B:
            a_node: Node[A] = dtfield(Node("a"))  # Equivalent to: Node[A] = dtfield(Node(A, 'a'))

        self.assertEqual(B().a_node(), A(a=4))


class TestClassVar(unittest.TestCase):
    def test_class_var_basic(self):
        """Test basic ClassVar functionality - ClassVars should remain class variables"""
        
        @datatree
        class A:
            class_attr: ClassVar[int] = 100
            instance_attr: int = 200
        
        a1 = A()
        a2 = A(instance_attr=300)
        
        # ClassVar should be a class attribute
        self.assertEqual(A.class_attr, 100)
        self.assertEqual(a1.class_attr, 100)
        self.assertEqual(a2.class_attr, 100)
        
        # Changing class attribute affects all instances
        A.class_attr = 150
        self.assertEqual(A.class_attr, 150)
        self.assertEqual(a1.class_attr, 150)
        self.assertEqual(a2.class_attr, 150)
        
        # Instance attr works normally
        self.assertEqual(a1.instance_attr, 200)
        self.assertEqual(a2.instance_attr, 300)
    
    def test_class_var_not_in_init(self):
        """ClassVar fields should not be included in __init__ parameters"""
        
        @datatree
        class A:
            class_attr: ClassVar[int] = 100
            instance_attr: int = 200
        
        # This should not raise an error - class_attr should not be an init parameter
        a = A(instance_attr=300)
        self.assertEqual(a.instance_attr, 300)
        
        # Trying to initialize a ClassVar should raise TypeError
        with self.assertRaises(TypeError):
            A(class_attr=400, instance_attr=300)
    
    def test_class_var_not_injected(self):
        """ClassVar fields should not be injected by Nodes"""
        
        @datatree
        class A:
            class_attr: ClassVar[int] = 100
            instance_attr: int = 200
        
        @datatree
        class B:
            a_node: Node[A] = Node(A)
        
        b = B()
        
        # B should not have class_attr injected as an instance attribute
        self.assertFalse(hasattr(B, 'class_attr'))
        
        # But B instances can access A's class_attr through the class
        self.assertEqual(b.a_node().class_attr, 100)
        
        # instance_attr should be injected normally
        self.assertEqual(b.instance_attr, 200)
        
        # Modifying injected instance_attr affects created instances
        b.instance_attr = 300
        self.assertEqual(b.a_node().instance_attr, 300)
        
        # Class attributes should not be affected by injection
        A.class_attr = 150
        self.assertEqual(b.a_node().class_attr, 150)
    
    def test_class_var_with_annotations(self):
        """Test ClassVar with different types of annotations"""
        
        @datatree
        class A:
            int_class_attr: ClassVar[int] = 100
            list_class_attr: ClassVar[list] = [1, 2, 3]
            dict_class_attr: ClassVar[dict] = {"key": "value"}
            simple_class_attr: ClassVar = "no type parameter"
            instance_attr: int = 200
        
        a = A()
        
        # All ClassVar types should be handled correctly
        self.assertEqual(A.int_class_attr, 100)
        self.assertEqual(A.list_class_attr, [1, 2, 3])
        self.assertEqual(A.dict_class_attr, {"key": "value"})
        self.assertEqual(A.simple_class_attr, "no type parameter")
        
        # Instance attribute works normally
        self.assertEqual(a.instance_attr, 200)

    def test_class_var_inheritance_and_node_boundaries(self):
        """Test ClassVar fields with inheritance and across Node boundaries"""
        
        @datatree
        class Parent:
            parent_class_attr: ClassVar[int] = 100
            parent_instance_attr: int = 200
        
        @datatree
        class Child(Parent):
            child_class_attr: ClassVar[int] = 300
            child_instance_attr: int = 400
        
        @datatree
        class Container:
            child_node: Node[Child] = Node(Child)
            # This should not inject parent_class_attr or child_class_attr
        
        container = Container()
        child = container.child_node()
        
        # Verify class attributes
        self.assertEqual(Parent.parent_class_attr, 100)
        self.assertEqual(Child.parent_class_attr, 100)
        self.assertEqual(Child.child_class_attr, 300)
        
        # ClassVar fields should not be injected into Container
        self.assertFalse(hasattr(Container, 'parent_class_attr'))
        self.assertFalse(hasattr(Container, 'child_class_attr'))
        
        # But instance attributes should be injected
        self.assertEqual(container.parent_instance_attr, 200)
        self.assertEqual(container.child_instance_attr, 400)
        
        # Child should have both instance attributes
        self.assertEqual(child.parent_instance_attr, 200)
        self.assertEqual(child.child_instance_attr, 400)
        
        # Modifying Container instance attrs should affect created Child instances
        container.parent_instance_attr = 250
        container.child_instance_attr = 450
        new_child = container.child_node()
        self.assertEqual(new_child.parent_instance_attr, 250)
        self.assertEqual(new_child.child_instance_attr, 450)
        
    def test_class_var_default_if_missing(self):
        @datatree
        class A:
            v1: int
            v2: int = dtfield(default_factory=lambda: 100)
            v3: int = dtfield(self_default=lambda s: s.v1 + s.v2)
            v4: int = 4
            class_attr: ClassVar[int] = 100
            
        with self.assertRaises(TypeError):
            @datatree
            class B:
                bv1: int
                bv2: int = 2
                a_node: Node[A]

        @datatree
        class B:
            bv1: int
            bv2: int = 2
            a_node: Node[A] = Node(A, default_if_missing=42)

        b = B(bv1=22)
        a = b.a_node()
        self.assertEqual(b.bv1, 22)
        self.assertEqual(b.v2, 100)
        self.assertFalse(hasattr(b, 'v3'))
        self.assertEqual(b.v4, 4)
        self.assertFalse(hasattr(b, 'class_attr'))
        self.assertEqual(a.v1, 42)
        self.assertEqual(a.v3, 142)
            


if __name__ == "__main__":
    unittest.main()
