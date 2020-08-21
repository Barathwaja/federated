# Copyright 2018, The TensorFlow Federated Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Defines functions and classes for building and manipulating TFF types."""

import abc
import collections
import typing
from typing import Any, Dict, Optional, Type as TypingType, TypeVar
import weakref

import attr
import tensorflow as tf

from tensorflow_federated.python.common_libs import py_typecheck
from tensorflow_federated.python.common_libs import structure
from tensorflow_federated.python.core.impl.types import placement_literals
from tensorflow_federated.python.tensorflow_libs import tensor_utils

C = TypeVar('C')


class UnexpectedTypeError(TypeError):

  def __init__(self, expected: TypingType['Type'], actual: 'Type'):
    message = f'Expected type of kind {expected}, found type {actual}'
    super().__init__(message)
    self.actual = actual
    self.expected = expected


class Type(object, metaclass=abc.ABCMeta):
  """An abstract interface for all classes that represent TFF types."""

  def compact_representation(self):
    """Returns the compact string representation of this type."""
    return _string_representation(self, formatted=False)

  def formatted_representation(self):
    """Returns the formatted string representation of this type."""
    return _string_representation(self, formatted=True)

  @abc.abstractmethod
  def children(self):
    """Returns a generator yielding immediate child types."""
    raise NotImplementedError

  def check_abstract(self):
    """Check that this is a `tff.AbstractType`."""
    if not self.is_abstract():
      raise UnexpectedTypeError(AbstractType, self)

  def is_abstract(self) -> bool:
    """Returns whether or not this type is a `tff.AbstractType`."""
    return False

  def check_federated(self):
    """Check that this is a `tff.FederatedType`."""
    if not self.is_federated():
      raise UnexpectedTypeError(FederatedType, self)

  def is_federated(self) -> bool:
    """Returns whether or not this type is a `tff.FederatedType`."""
    return False

  def check_function(self):
    """Check that this is a `tff.FunctionType`."""
    if not self.is_function():
      raise UnexpectedTypeError(FunctionType, self)

  def is_function(self) -> bool:
    """Returns whether or not this type is a `tff.FunctionType`."""
    return False

  def check_placement(self):
    """Check that this is a `tff.PlacementType`."""
    if not self.is_placement():
      raise UnexpectedTypeError(PlacementType, self)

  def is_placement(self) -> bool:
    """Returns whether or not this type is a `tff.PlacementType`."""
    return False

  def check_sequence(self):
    """Check that this is a `tff.SequenceType`."""
    if not self.is_sequence():
      raise UnexpectedTypeError(SequenceType, self)

  def is_sequence(self) -> bool:
    """Returns whether or not this type is a `tff.SequenceType`."""
    return False

  def check_struct(self):
    """Check that this is a `tff.StructType`."""
    if not self.is_struct():
      raise UnexpectedTypeError(StructType, self)

  def is_struct(self):
    """Returns whether or not this type is a `tff.StructType`."""
    return False

  def check_struct_with_python(self):
    """Check that this is a `tff.StructWithPythonType`."""
    if not self.is_struct_with_python():
      raise UnexpectedTypeError(StructWithPythonType, self)

  def is_struct_with_python(self):
    """Returns whether or not this type is a `tff.StructWithPythonType`."""
    return False

  def check_tensor(self):
    """Check that this is a `tff.TensorType`."""
    if not self.is_tensor():
      UnexpectedTypeError(TensorType, self)

  def is_tensor(self) -> bool:
    """Returns whether or not this type is a `tff.TensorType`."""
    return False

  @abc.abstractmethod
  def __repr__(self):
    """Returns a full-form representation of this type."""
    raise NotImplementedError

  def __str__(self):
    """Returns a concise representation of this type."""
    return self.compact_representation()

  @abc.abstractmethod
  def __hash__(self):
    """Produces a hash value for this type."""
    raise NotImplementedError

  @abc.abstractmethod
  def __eq__(self, other):
    """Determines whether two type definitions are identical.

    Note that this notion of equality is stronger than equivalence. Two types
    with equivalent definitions may not be identical, e.g., if they represent
    templates with differently named type variables in their definitions.

    Args:
      other: The other type to compare against.

    Returns:
      `True` iff type definitions are syntatically identical (as defined above),
      or `False` otherwise.

    Raises:
      NotImplementedError: If not implemented in the derived class.
    """
    raise NotImplementedError

  def __ne__(self, other):
    return not self == other

  def check_assignable_from(self, source_type: 'Type'):
    """Raises if values of `source_type` cannot be cast to this type."""
    if not self.is_assignable_from(source_type):
      raise TypeError('Values of type {} cannot be cast to type {}.'.format(
          source_type, self))

  @abc.abstractmethod
  def is_assignable_from(self, source_type: 'Type') -> bool:
    """Returns whether values of `source_type` can be cast to this type."""
    raise NotImplementedError

  def check_equivalent_to(self, other: 'Type'):
    """Raises if values of 'other' cannot be cast to and from this type."""
    if not self.is_equivalent_to(other):
      raise TypeError('Types {} and {} are not equivalent.'.format(self, other))

  def is_equivalent_to(self, other: 'Type') -> bool:
    """Returns whether values of `other` can be cast to and from this type."""
    return self.is_assignable_from(other) and other.is_assignable_from(self)


class _ValueWithHash():
  """A wrapper for a value which combines it with a hashcode."""

  def __init__(self, value, hashcode):
    self._value = value
    self._hashcode = hashcode

  def __eq__(self, other):
    return self._value == other._value

  def __hash__(self):
    return self._hashcode


# A per-`typing.Type` map from `__init__` arguments to object instances.
#
# This is used by the `_Intern` metaclass to allow reuse of object instances
# when new objects are requested with the same `__init__` arguments as
# existing object instances.
#
# A `WeakValueDictionary` is used here so that interned instances are not
# stored for any longer than their usual lifetimes.
#
# Implementation note: this double-map is used rather than a single map
# stored as a field of each class because some class objects themselves would
# begin destruction before the map fields of other classes, causing errors
# during destruction.
_intern_pool: Dict[typing.Type[Any], Dict[Any, Any]] = (
    collections.defaultdict(lambda: weakref.WeakValueDictionary({})))


class _Intern(abc.ABCMeta):
  """A metaclass which interns instances.

  This is used to create classes where the following predicate holds:
  `MyClass(some_args) is MyClass(some_args)`

  That is, objects of the class with the same constructor parameters result
  in values with the same object identity. This can make comparison of deep
  structures much cheaper, since a shallow equality check can short-circuit
  comparison.

  Classes which set `_Intern` as a metaclass must have a
  `_normalize_init_args` static method which takes in the arguments passed
  to `Your_InternedClass(...)` and returns a tuple of arguments to be passed
  to the `__init__` method. Note that keyword arguments must be flattened.

  If any of the normalized `__init__` arguments are unhashable, the class
  must implement a static method `_hash_normalized_args`.

  Note also that this must only be used with *immutable* values, as mutation
  would cause all similarly-constructed instances to be mutated together.

  Inherits from `abc.ABCMeta` to prevent subclass conflicts.
  """

  @staticmethod
  def _hash_normalized_args(*args):
    """Default implementation of `_hash_normalized_args`."""
    return hash(args)

  def __call__(cls, *args, **kwargs):
    normalized_args = cls._normalize_init_args(*args, **kwargs)  # pytype: disable=attribute-error
    hashable_args = _ValueWithHash(normalized_args,
                                   cls._hash_normalized_args(*normalized_args))
    intern_pool_for_cls = _intern_pool[cls]
    interned = intern_pool_for_cls.get(hashable_args, None)
    if interned is None:
      new_instance = super().__call__(*normalized_args)
      intern_pool_for_cls[hashable_args] = new_instance
      return new_instance
    else:
      return interned


def _hash_dtype_and_shape(dtype: tf.DType, shape: tf.TensorShape) -> int:
  return hash((dtype.name, tuple(shape.as_list())))


class TensorType(Type, metaclass=_Intern):
  """An implementation of `tff.Type` representing types of tensors in TFF."""

  @staticmethod
  def _normalize_init_args(dtype, shape=None):
    """Checks init arguments and converts to a normalized representation."""
    py_typecheck.check_type(dtype, tf.DType)
    # TODO(b/123764922): If we are passed a shape of `TensorShape(None)`, which
    # does happen along some codepaths, we have slightly violated the
    # assumptions of `TensorType` (see the special casing in `repr` and `str`
    # below. This is related to compatibility checking,
    # and there are a few options. For now, simply adding a case in
    # `is_assignable_from` to catch. We could alternatively
    # treat this case the same as if we have been passed a shape of `None` in
    # this constructor.
    if shape is None:
      shape = tf.TensorShape([])
    elif not isinstance(shape, tf.TensorShape):
      shape = tf.TensorShape(shape)
    return (dtype, shape)

  @staticmethod
  def _hash_normalized_args(dtype, shape):
    return _hash_dtype_and_shape(dtype, shape)

  def __init__(self, dtype, shape=None):
    """Constructs a new instance from the given `dtype` and `shape`.

    Args:
      dtype: An instance of `tf.DType`.
      shape: An optional instance of `tf.TensorShape` or an argument that can be
        passed to its constructor (such as a `list` or a `tuple`), or `None` for
        the default scalar shape. TensorShapes with unknown rank are not
        supported.

    Raises:
      TypeError: if arguments are of the wrong types.
    """
    self._dtype = dtype
    self._shape = shape
    self._hash = None
    _check_well_formed(self)

  def children(self):
    return iter(())

  def is_tensor(self):
    return True

  @property
  def dtype(self):
    return self._dtype

  @property
  def shape(self):
    return self._shape

  def __repr__(self):
    if self._shape.ndims is None:
      return 'TensorType({!r}, {})'.format(self._dtype, None)
    elif self._shape.ndims > 0:
      values = [dim.value for dim in self._shape.dims]
      return 'TensorType({!r}, {!r})'.format(self._dtype, values)
    else:
      return 'TensorType({!r})'.format(self._dtype)

  def __hash__(self):
    if self._hash is None:
      self._hash = _hash_dtype_and_shape(self._dtype, self._shape)
    return self._hash

  def __eq__(self, other):
    return ((self is other) or
            (isinstance(other, TensorType) and self._dtype == other.dtype and
             tensor_utils.same_shape(self._shape, other.shape)))

  def is_assignable_from(self, source_type: 'Type') -> bool:
    if self is source_type:
      return True
    if (not isinstance(source_type, TensorType) or
        self.dtype != source_type.dtype):
      return False
    target_shape = self.shape
    source_shape = source_type.shape
    # TODO(b/123764922): See if we can pass to TensorShape's
    # `is_compatible_with`.
    if target_shape.ndims is None:
      return True
    if target_shape.ndims != source_shape.ndims:
      return False
    if target_shape.dims is None:
      return True

    def _dimension_is_assignable_from(target_dim, source_dim):
      return ((target_dim.value is None) or
              (target_dim.value == source_dim.value))

    return all(
        _dimension_is_assignable_from(target_shape.dims[k],
                                      source_shape.dims[k])
        for k in range(target_shape.ndims))


def _format_struct_type_members(struct_type: 'StructType') -> str:

  def _element_repr(element):
    name, value = element
    if name is not None:
      return '(\'{}\', {!r})'.format(name, value)
    return repr(value)

  return ', '.join(
      _element_repr(e) for e in structure.iter_elements(struct_type))


class StructType(structure.Struct, Type, metaclass=_Intern):
  """An implementation of `tff.Type` representing structural types in TFF.

  Elements initialized by name can be accessed as `foo.name`, and otherwise by
  index, `foo[index]`.
  """

  @staticmethod
  def _normalize_init_args(elements, convert=True):
    py_typecheck.check_type(elements, collections.Iterable)
    if convert:
      if py_typecheck.is_named_tuple(elements):
        elements = typing.cast(Any, elements)
        elements = elements._asdict()
      if isinstance(elements, collections.OrderedDict):
        elements = elements.items()

      def _is_full_element_spec(e):
        return py_typecheck.is_name_value_pair(e, name_required=False)

      def _map_element(e):
        if isinstance(e, Type):
          return (None, e)
        elif _is_full_element_spec(e):
          return (e[0], to_type(e[1]))
        else:
          return (None, to_type(e))

      if _is_full_element_spec(elements):
        elements = [(elements[0], to_type(elements[1]))]
      else:
        elements = [_map_element(e) for e in elements]
    return (elements,)

  @staticmethod
  def _hash_normalized_args(elements):
    return hash(tuple(elements))

  def __init__(self, elements, enable_wf_check=True):
    """Constructs a new instance from the given element types.

    Args:
      elements: An iterable of element specifications. Each element
        specification is either a type spec (an instance of `tff.Type` or
        something convertible to it via `tff.to_type`) for the element, or a
        (name, spec) for elements that have defined names. Alternatively, one
        can supply here an instance of `collections.OrderedDict` mapping element
        names to their types (or things that are convertible to types).
      enable_wf_check: This flag exists only so that `StructWithPythonType` can
        disable the well-formedness check, as the type won't be well-formed
        until the subclass has finished its own initialization.
    """
    structure.Struct.__init__(self, elements)
    if enable_wf_check:
      _check_well_formed(self)

  def children(self):
    return (element for _, element in structure.iter_elements(self))

  @property
  def python_container(self) -> Optional[TypingType[Any]]:
    return None

  def is_struct(self):
    return True

  def __repr__(self):
    members = _format_struct_type_members(self)
    return 'StructType([{}])'.format(members)

  def __hash__(self):
    # Salt to avoid overlap.
    return hash((structure.Struct.__hash__(self), 'NTT'))

  def __eq__(self, other):
    return (self is other) or (isinstance(other, StructType) and
                               structure.Struct.__eq__(self, other))

  def is_assignable_from(self, source_type: 'Type') -> bool:
    if self is source_type:
      return True
    if not isinstance(source_type, StructType):
      return False
    target_elements = structure.to_elements(self)
    source_elements = structure.to_elements(source_type)
    return ((len(target_elements) == len(source_elements)) and all(
        ((source_elements[k][0] in [target_elements[k][0], None]) and
         target_elements[k][1].is_assignable_from(source_elements[k][1]))
        for k in range(len(target_elements))))


class StructWithPythonType(StructType, metaclass=_Intern):
  """A representation of a structure paired with a Python container type."""

  @staticmethod
  def _normalize_init_args(elements, container_type):
    py_typecheck.check_type(container_type, type)
    # TODO(b/161561250): check the `container_type` for validity.
    elements = StructType._normalize_init_args(elements)[0]
    return (elements, container_type)

  @staticmethod
  def _hash_normalized_args(elements, container_type):
    return hash((tuple(elements), container_type))

  def __init__(self, elements, container_type):
    # We don't want to check our type for well-formedness until after we've
    # set `_container_type`.
    super().__init__(elements, enable_wf_check=False)
    self._container_type = container_type
    _check_well_formed(self)

  def is_struct_with_python(self):
    return True

  @property
  def python_container(self) -> TypingType[Any]:
    return self._container_type

  def __repr__(self):
    members = _format_struct_type_members(self)
    return 'StructType([{}]) as {}'.format(members,
                                           self._container_type.__name__)

  def __hash__(self):
    # Salt to avoid overlap.
    return hash((structure.Struct.__hash__(self), 'NTTWPCT'))

  def __eq__(self, other):
    return ((self is other) or
            (isinstance(other, StructWithPythonType) and
             (self._container_type == other._container_type) and
             structure.Struct.__eq__(self, other)))

  @classmethod
  def get_container_type(cls, value):
    return value._container_type  # pylint: disable=protected-access


class SequenceType(Type, metaclass=_Intern):
  """An implementation of `tff.Type` representing types of sequences in TFF."""

  @staticmethod
  def _normalize_init_args(element):
    return (to_type(element),)

  def __init__(self, element):
    """Constructs a new instance from the given `element` type.

    Args:
      element: A specification of the element type, either an instance of
        `tff.Type` or something convertible to it by `tff.to_type`.
    """
    self._element = element
    _check_well_formed(self)

  def children(self):
    yield self._element

  def is_sequence(self):
    return True

  @property
  def element(self) -> Type:
    return self._element

  def __repr__(self):
    return 'SequenceType({!r})'.format(self._element)

  def __hash__(self):
    return hash(self._element)

  def __eq__(self, other):
    return ((self is other) or (isinstance(other, SequenceType) and
                                self._element == other.element))

  def is_assignable_from(self, source_type: 'Type') -> bool:
    if self is source_type:
      return True
    return ((isinstance(source_type, SequenceType) and
             self.element.is_assignable_from(source_type.element)))


class FunctionType(Type, metaclass=_Intern):
  """An implementation of `tff.Type` representing functional types in TFF."""

  @staticmethod
  def _normalize_init_args(parameter, result):
    return (to_type(parameter), to_type(result))

  def __init__(self, parameter, result):
    """Constructs a new instance from the given `parameter` and `result` types.

    Args:
      parameter: A specification of the parameter type, either an instance of
        `tff.Type` or something convertible to it by `tff.to_type`. Multiple
        input arguments can be specified as a single `tff.StructType`.
      result: A specification of the result type, either an instance of
        `tff.Type` or something convertible to it by `tff.to_type`.
    """
    self._parameter = parameter
    self._result = result
    _check_well_formed(self)

  def children(self):
    if self._parameter is not None:
      yield self._parameter
    yield self._result

  def is_function(self):
    return True

  @property
  def parameter(self):
    return self._parameter

  @property
  def result(self):
    return self._result

  def __repr__(self):
    return 'FunctionType({!r}, {!r})'.format(self._parameter, self._result)

  def __hash__(self):
    return hash((self._parameter, self._result))

  def __eq__(self, other):
    return ((self is other) or (isinstance(other, FunctionType) and
                                self._parameter == other.parameter and
                                self._result == other.result))

  def is_assignable_from(self, source_type: 'Type') -> bool:
    if self is source_type:
      return True
    if not isinstance(source_type, FunctionType):
      return False
    if (self.parameter is None) != (source_type.parameter is None):
      return False
    # Note that function parameters are contravariant, so we invert the check.
    if (self.parameter is not None and
        not source_type.parameter.is_assignable_from(self.parameter)):
      return False
    return self.result.is_assignable_from(source_type.result)


class AbstractType(Type, metaclass=_Intern):
  """An implementation of `tff.Type` representing abstract types in TFF."""

  @staticmethod
  def _normalize_init_args(label):
    py_typecheck.check_type(label, str)
    return (str(label),)

  def __init__(self, label):
    """Constructs a new instance from the given string `label`.

    Args:
      label: A string label of an abstract type. All occurences of the label
        within a computation's type signature refer to the same concrete type.
    """
    self._label = label
    _check_well_formed(self)

  def children(self):
    return iter(())

  def is_abstract(self):
    return True

  @property
  def label(self):
    return self._label

  def __repr__(self):
    return 'AbstractType(\'{}\')'.format(self._label)

  def __hash__(self):
    return hash(self._label)

  def __eq__(self, other):
    return (self is other) or (isinstance(other, AbstractType) and
                               self._label == other.label)

  def is_assignable_from(self, _source_type: 'Type') -> bool:
    # TODO(b/113112108): Revise this to extend the relation of assignability to
    # abstract types.
    raise TypeError('Abstract types are not comparable.')


class PlacementType(Type, metaclass=_Intern):
  """An implementation of `tff.Type` representing the placement type in TFF.

  There is only one placement type, a TFF built-in, just as there is only one
  `int` or `str` type in Python. All instances of this class represent the same
  built-in TFF placement type.
  """

  @staticmethod
  def _normalize_init_args():
    return ()

  def __init__(self):
    _check_well_formed(self)

  def children(self):
    return iter(())

  def is_placement(self):
    return True

  def __repr__(self):
    return 'PlacementType()'

  def __hash__(self):
    return 0

  def __eq__(self, other):
    return (self is other) or isinstance(other, PlacementType)

  def is_assignable_from(self, source_type: 'Type') -> bool:
    if self is source_type:
      return True
    return isinstance(source_type, PlacementType)


class FederatedType(Type, metaclass=_Intern):
  """An implementation of `tff.Type` representing federated types in TFF."""

  @staticmethod
  def _normalize_init_args(member, placement, all_equal=None):
    py_typecheck.check_type(placement, placement_literals.PlacementLiteral)
    member = to_type(member)
    if all_equal is None:
      all_equal = placement.default_all_equal
    return (member, placement, all_equal)

  def __init__(self, member, placement, all_equal=None):
    """Constructs a new federated type instance.

    Args:
      member: An instance of `tff.Type` (or something convertible to it) that
        represents the type of the member components of each value of this
        federated type.
      placement: The specification of placement that the member components of
        this federated type are hosted on. Must be either a placement literal
        such as `tff.SERVER` or `tff.CLIENTS` to refer to a globally defined
        placement, or a placement label to refer to a placement defined in other
        parts of a type signature. Specifying placement labels is not
        implemented yet.
      all_equal: A `bool` value that indicates whether all members of the
        federated type are equal (`True`), or are allowed to differ (`False`).
        If `all_equal` is `None`, the value is selected as the default for the
        placement, e.g., `True` for `tff.SERVER` and `False` for `tff.CLIENTS`.
    """
    self._member = member
    self._placement = placement
    self._all_equal = all_equal
    _check_well_formed(self)

  # TODO(b/113112108): Extend this to support federated types parameterized
  # by abstract placement labels, such as those used in generic types of
  # federated operators.

  def children(self):
    yield self._member

  def is_federated(self):
    return True

  @property
  def member(self):
    return self._member

  @property
  def placement(self):
    return self._placement

  @property
  def all_equal(self) -> bool:
    return self._all_equal

  def __repr__(self):
    return 'FederatedType({!r}, {!r}, {!r})'.format(self._member,
                                                    self._placement,
                                                    self._all_equal)

  def __hash__(self):
    return hash((self._member, self._placement, self._all_equal))

  def __eq__(self, other):
    return ((self is other) or (isinstance(other, FederatedType) and
                                self._member == other.member and
                                self._placement == other.placement and
                                self._all_equal == other.all_equal))

  def is_assignable_from(self, source_type: 'Type') -> bool:
    if self is source_type:
      return True
    return (isinstance(source_type, FederatedType) and
            self.member.is_assignable_from(source_type.member) and
            (not self.all_equal or source_type.all_equal) and
            self.placement is source_type.placement)


def to_type(spec) -> Type:
  """Converts the argument into an instance of `tff.Type`.

  Examples of arguments convertible to tensor types:

  ```python
  tf.int32
  (tf.int32, [10])
  (tf.int32, [None])
  ```

  Examples of arguments convertible to flat named tuple types:

  ```python
  [tf.int32, tf.bool]
  (tf.int32, tf.bool)
  [('a', tf.int32), ('b', tf.bool)]
  ('a', tf.int32)
  collections.OrderedDict([('a', tf.int32), ('b', tf.bool)])
  ```

  Examples of arguments convertible to nested named tuple types:

  ```python
  (tf.int32, (tf.float32, tf.bool))
  (tf.int32, (('x', tf.float32), tf.bool))
  ((tf.int32, [1]), (('x', (tf.float32, [2])), (tf.bool, [3])))
  ```

  Args:
    spec: Either an instance of `tff.Type`, or an argument convertible to
      `tff.Type`.

  Returns:
    An instance of `tff.Type` corresponding to the given `spec`.
  """
  # TODO(b/113112108): Add multiple examples of valid type specs here in the
  # comments, in addition to the unit test.
  if spec is None or isinstance(spec, Type):
    return spec
  elif isinstance(spec, tf.DType):
    return TensorType(spec)
  elif isinstance(spec, tf.TensorSpec):
    return TensorType(spec.dtype, spec.shape)
  elif (isinstance(spec, tuple) and (len(spec) == 2) and
        isinstance(spec[0], tf.DType) and
        (isinstance(spec[1], tf.TensorShape) or
         (isinstance(spec[1], (list, tuple)) and all(
             (isinstance(x, int) or x is None) for x in spec[1])))):
    # We found a 2-element tuple of the form (dtype, shape), where dtype is an
    # instance of tf.DType, and shape is either an instance of tf.TensorShape,
    # or a list, or a tuple that can be fed as argument into a tf.TensorShape.
    # We thus convert this into a TensorType.
    return TensorType(spec[0], spec[1])
  elif isinstance(spec, (list, tuple)):
    if any(py_typecheck.is_name_value_pair(e) for e in spec):
      # The sequence has a (name, value) elements, the whole sequence is most
      # likely intended to be a `Struct`, do not store the Python
      # container.
      return StructType(spec)
    else:
      return StructWithPythonType(spec, type(spec))
  elif isinstance(spec, collections.OrderedDict):
    return StructWithPythonType(spec, type(spec))
  elif py_typecheck.is_attrs(spec):
    return _to_type_from_attrs(spec)
  elif isinstance(spec, collections.Mapping):
    # This is an unsupported mapping, likely a `dict`. StructType adds an
    # ordering, which the original container did not have.
    raise TypeError(
        'Unsupported mapping type {}. Use collections.OrderedDict for '
        'mappings.'.format(py_typecheck.type_string(type(spec))))
  else:
    raise TypeError(
        'Unable to interpret an argument of type {} as a type spec.'.format(
            py_typecheck.type_string(type(spec))))


def _to_type_from_attrs(spec) -> Type:
  """Converts an `attr.s` class or instance to a `tff.Type`."""
  if isinstance(spec, type):
    # attrs class type, introspect the attributes for their type annotations.
    elements = [(a.name, a.type) for a in attr.fields(spec)]
    missing_types = [n for (n, t) in elements if not t]
    if missing_types:
      raise TypeError((
          "Cannot infer tff.Type for attr.s class '{}' because some attributes "
          'were missing type specifications: {}').format(
              spec.__name__, missing_types))
    the_type = spec
  else:
    # attrs class instance, inspect the field values for instances convertible
    # to types.
    elements = attr.asdict(
        spec, dict_factory=collections.OrderedDict, recurse=False)
    the_type = type(spec)

  return StructWithPythonType(elements, the_type)


@attr.s(auto_attribs=True, slots=True)
class _PossiblyDisallowedChildren:
  """A set of possibly disallowed types contained within a type.

  These kinds of types may be banned in one or more contexts, so
  `_possibly_disallowed_members` and its cache record which of these type kinds
  appears inside a type, allowing for quick well-formedness checks.
  """
  federated: Optional[Type]
  function: Optional[Type]
  sequence: Optional[Type]


# Manual cache used rather than `cachetools.cached` due to incompatibility
# with `WeakKeyDictionary`. We want to use a `WeakKeyDictionary` so that
# cache entries are destroyed once the types they index no longer exist.
_possibly_disallowed_children_cache = weakref.WeakKeyDictionary({})


def _possibly_disallowed_children(
    type_signature: Type,) -> _PossiblyDisallowedChildren:
  """Returns possibly disallowed child types appearing in `type_signature`."""
  cached = _possibly_disallowed_children_cache.get(type_signature, None)
  if cached:
    return cached
  disallowed = _PossiblyDisallowedChildren(None, None, None)
  for child_type in type_signature.children():
    if child_type.is_federated():
      disallowed = attr.evolve(disallowed, federated=child_type)
    elif child_type.is_function():
      disallowed = attr.evolve(disallowed, function=child_type)
    elif child_type.is_sequence():
      disallowed = attr.evolve(disallowed, sequence=child_type)
    from_grandchildren = _possibly_disallowed_children(child_type)
    disallowed = _PossiblyDisallowedChildren(
        federated=disallowed.federated or from_grandchildren.federated,
        function=disallowed.function or from_grandchildren.function,
        sequence=disallowed.sequence or from_grandchildren.sequence,
    )
  _possibly_disallowed_children_cache[type_signature] = disallowed
  return disallowed


_FEDERATED_TYPES = 'federated types (types placed @CLIENT or @SERVER)'
_FUNCTION_TYPES = 'function types'
_SEQUENCE_TYPES = 'sequence types'


def _check_well_formed(type_signature: Type):
  """Checks `type_signature`'s validity. Assumes that child types are valid."""

  def _check_disallowed(disallowed_type, disallowed_kind, context):
    if disallowed_type is None:
      return
    raise TypeError(
        f'{disallowed_type} has been encountered in the type {type_signature}. '
        f'{disallowed_kind} are disallowed inside of {context}.')

  children = _possibly_disallowed_children(type_signature)

  if type_signature.is_federated():
    # Federated types cannot have federated or functional children.
    for (child_type, kind) in ((children.federated, _FEDERATED_TYPES),
                               (children.function, _FUNCTION_TYPES)):
      _check_disallowed(child_type, kind, _FEDERATED_TYPES)
  elif type_signature.is_sequence():
    # Sequence types cannot have federated, functional, or sequence children.
    for (child_type, kind) in ((children.federated, _FEDERATED_TYPES),
                               (children.function, _FUNCTION_TYPES),
                               (children.sequence, _SEQUENCE_TYPES)):
      _check_disallowed(child_type, kind, _SEQUENCE_TYPES)


def _string_representation(type_spec, formatted: bool) -> str:
  """Returns the string representation of a TFF `Type`.

  This function creates a `list` of strings representing the given `type_spec`;
  combines the strings in either a formatted or un-formatted representation; and
  returns the resulting string representation.

  Args:
    type_spec: An instance of a TFF `Type`.
    formatted: A boolean indicating if the returned string should be formatted.

  Raises:
    TypeError: If `type_spec` has an unexpected type.
  """
  py_typecheck.check_type(type_spec, Type)

  def _combine(components):
    """Returns a `list` of strings by combining `components`.

    This function creates and returns a `list` of strings by combining a `list`
    of `components`. Each `component` is a `list` of strings representing a part
    of the string of a TFF `Type`. The `components` are combined by iteratively
    **appending** the last element of the result with the first element of the
    `component` and then **extending** the result with remaining elements of the
    `component`.

    For example:

    >>> _combine([['a'], ['b'], ['c']])
    ['abc']

    >>> _combine([['a', 'b', 'c'], ['d', 'e', 'f']])
    ['abcd', 'ef']

    This function is used to help track where new-lines should be inserted into
    the string representation if the lines are formatted.

    Args:
      components: A `list` where each element is a `list` of strings
        representing a part of the string of a TFF `Type`.
    """
    lines = ['']
    for component in components:
      lines[-1] = '{}{}'.format(lines[-1], component[0])
      lines.extend(component[1:])
    return lines

  def _indent(lines, indent_chars='  '):
    """Returns an indented `list` of strings."""
    return ['{}{}'.format(indent_chars, e) for e in lines]

  def _lines_for_named_types(named_type_specs, formatted):
    """Returns a `list` of strings representing the given `named_type_specs`.

    Args:
      named_type_specs: A `list` of named comutations, each being a pair
        consisting of a name (either a string, or `None`) and a
        `ComputationBuildingBlock`.
      formatted: A boolean indicating if the returned string should be
        formatted.
    """
    lines = []
    for index, (name, type_spec) in enumerate(named_type_specs):
      if index != 0:
        if formatted:
          lines.append([',', ''])
        else:
          lines.append([','])
      element_lines = _lines_for_type(type_spec, formatted)
      if name is not None:
        element_lines = _combine([
            ['{}='.format(name)],
            element_lines,
        ])
      lines.append(element_lines)
    return _combine(lines)

  def _lines_for_type(type_spec, formatted):
    """Returns a `list` of strings representing the given `type_spec`.

    Args:
      type_spec: An instance of a TFF `Type`.
      formatted: A boolean indicating if the returned string should be
        formatted.
    """
    if type_spec.is_abstract():
      return [type_spec.label]
    elif type_spec.is_federated():
      member_lines = _lines_for_type(type_spec.member, formatted)
      placement_line = '@{}'.format(type_spec.placement)
      if type_spec.all_equal:
        return _combine([member_lines, [placement_line]])
      else:
        return _combine([['{'], member_lines, ['}'], [placement_line]])
    elif type_spec.is_function():
      if type_spec.parameter is not None:
        parameter_lines = _lines_for_type(type_spec.parameter, formatted)
      else:
        parameter_lines = ['']
      result_lines = _lines_for_type(type_spec.result, formatted)
      return _combine([['('], parameter_lines, [' -> '], result_lines, [')']])
    elif type_spec.is_struct():
      if len(type_spec) == 0:  # pylint: disable=g-explicit-length-test
        return ['<>']
      elements = structure.to_elements(type_spec)
      elements_lines = _lines_for_named_types(elements, formatted)
      if formatted:
        elements_lines = _indent(elements_lines)
        lines = [['<', ''], elements_lines, ['', '>']]
      else:
        lines = [['<'], elements_lines, ['>']]
      return _combine(lines)
    elif type_spec.is_placement():
      return ['placement']
    elif type_spec.is_sequence():
      element_lines = _lines_for_type(type_spec.element, formatted)
      return _combine([element_lines, ['*']])
    elif type_spec.is_tensor():
      if type_spec.shape.ndims is None:
        return ['{!r}[{}]'.format(type_spec.dtype, None)]
      elif type_spec.shape.ndims > 0:

        def _value_string(value):
          return str(value) if value is not None else '?'

        value_strings = [_value_string(e.value) for e in type_spec.shape.dims]
        values_strings = ','.join(value_strings)
        return ['{}[{}]'.format(type_spec.dtype.name, values_strings)]
      else:
        return [type_spec.dtype.name]
    else:
      raise NotImplementedError('Unexpected type found: {}.'.format(
          type(type_spec)))

  lines = _lines_for_type(type_spec, formatted)
  lines = [line.rstrip() for line in lines]
  if formatted:
    return '\n'.join(lines)
  else:
    return ''.join(lines)
