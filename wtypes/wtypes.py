#!/usr/bin/env python
# coding: utf-8

"""extended python types for the web and json

Notes
-----
Attributes
----------
simpleTypes : list
    The limited set of base types provide by jsonschema.

Todo
---
* Configuration Files
* Observable Pattern
* You have to also use ``sphinx.ext.todo`` extension

.. ``jsonschema`` documentation:
   https://json-schema.org/
"""
__version__ = "0.0.1"
import abc
import copy
import dataclasses
import functools
import inspect
import re
import typing

import jsonschema
import munch

simpleTypes = jsonschema.Draft7Validator.META_SCHEMA["definitions"]["simpleTypes"][
    "enum"
]
ValidationError = jsonschema.ValidationError


def istype(object, cls):
    """instance(object, type) and issubclass(object, cls)
    
Examples
--------

    >>> assert istype(int, int)
    >>> assert not istype(10, int)
    
"""
    if isinstance(object, type):
        return issubclass(object, cls)
    return False


class _NoTitle:
    """A subclass suppresses the class name when combining schema"""


class _NoInit:
    """A subclass to restrict initializing an object from the type."""

    def __new__(cls, *args, **kwargs):
        raise TypeError(f"Cannot initialize the type : {cls.__name__}")


# ## `webtypes` meta schema


class _SchemaMeta(abc.ABCMeta):
    """Meta operations for wtypes.
    
The ``_SchemaMeta`` ensures that a type's extended schema is validate.
Types cannot be generated with invalid schema.

Attributes
----------
_meta_schema : dict
    The schema the type system validates against.
    
_schema : dict
    The schema the object validates against.

_type
    The resource type.

"""

    _meta_schema = jsonschema.Draft7Validator.META_SCHEMA
    _schema = None
    _type = "http://json-schema.org/draft-07/schema#/properties/"

    def _merge_annotations(cls):
        """Merge annotations from the module resolution order."""
        if not hasattr(cls, "__annotations__"):
            cls.__annotations__ = {}
        for module in reversed(type(cls).__mro__):
            cls.__annotations__.update(getattr(module, "__annotations__", {}))

    def _merge_schema(cls):
        """Merge schema from the module resolution order."""
        schema = munch.Munch()
        for self in reversed(cls.__mro__):
            schema.update(munch.Munch.fromDict(getattr(self, "_schema", {}) or {}))
        cls._schema = schema

    def __new__(cls, name, base, kwargs, **schema):
        global simpleTypes

        cls = super().__new__(cls, name, base, kwargs)
        cls._type = schema.pop("type", None) or cls._type
        # Combine metadata across the module resolution order.
        cls._merge_annotations(), cls._merge_schema()
        cls._schema.update(schema)

        jsonschema.validate(
            cls._schema,
            cls._meta_schema,
            format_checker=jsonschema.draft7_format_checker,
        )
        """Validate the proposed schema against the jsonschema schema."""
        return cls

    def create(cls, name: str, **schema):
        """Create a new schema type.
        

Parameters
----------
name: str
    The title of the new type/schema
**schema: dict
    Extra features to add include in the schema.
    
Returns
-------
type
    
        """
        return type(name, (cls,), {"_schema": copy.deepcopy(cls._schema)}, **schema)

    def __neg__(cls):
        """The Not version of a type."""
        return Not[cls]

    def __pos__(cls):
        """The type."""
        return cls

    def __add__(cls, object):
        """Add types together"""
        return cls.create(
            _construct_title(cls) + _construct_title(_python_to_wtype(object)),
            **_get_schema_from_typeish(object),
        )

    def __and__(cls, object):
        """AllOf the conditions"""
        return AllOf[cls, object]

    def __sub__(cls, object):
        """AnyOf the conditions"""
        return AnyOf[cls, object]

    def __or__(cls, object):
        """OneOf the conditions"""
        return OneOf[cls, object]

    def validate(cls, object):
        """Validate an object against type's schema.
        
        
Note
----
``isinstance`` can used for validation, too.

Parameters
----------
object
    An object to validate.
        
Raises
------
jsonschema.ValidationError
    The ``jsonschema`` module validation throws an exception on failure,
    otherwise the returns a None type.
"""
        jsonschema.validate(
            object, cls._schema, format_checker=jsonschema.draft7_format_checker
        )

    def __instancecheck__(cls, object):
        try:
            return cls.validate(object) or True
        except:
            return False


class _ConstType(_SchemaMeta):
    """ConstType permits bracketed syntax for defining complex types.
            
Note
----
The bracketed notebook should differeniate actions on types versus those on objects.
"""

    def __getitem__(cls, object):
        object = _get_schema_from_typeish(object)
        if isinstance(object, tuple):
            object = list(object)
        return cls.create(
            cls.__name__, **{_lower_key(cls.__name__): _get_schema_from_typeish(object)}
        )


class _ContainerType(_ConstType):
    """ContainerType extras schema from bracketed arguments to define complex types."""

    def __getitem__(cls, object):
        schema_key = _lower_key(cls.__name__)
        schema = _get_schema_from_typeish(object)
        if isinstance(object, dict):
            object = {**cls._schema.get(schema_key, {}), **schema}
        if isinstance(object, tuple):
            object = cls._schema.get(schema_key, []) + schema
        return cls + Trait.create(schema_key, **{schema_key: schema})


def _python_to_wtype(object):
    if isinstance(object, typing.Hashable):
        if object == str:
            object = String
        elif object == tuple:
            object = List
        elif object == list:
            object = List
        elif object == dict:
            object = Dict
        elif object == int:
            object = Integer
        elif object == tuple:
            object = Tuple
        elif object == float:
            object = Float
        elif object == None:
            object = None
        elif object == bool:
            object = Bool
    return object


def _get_schema_from_typeish(object):
    """infer a schema from an object."""
    if isinstance(object, dict):
        return {k: _get_schema_from_typeish(v) for k, v in object.items()}
    if isinstance(object, (list, tuple)):
        return list(map(_get_schema_from_typeish, object))
    object = _python_to_wtype(object)
    if hasattr(object, "_schema"):
        return object._schema
    return object


def _lower_key(str):
    return str[0].lower() + str[1:]


def _object_to_webtype(object):
    if isinstance(object, typing.Mapping):
        return Dict
    if isinstance(object, str):
        return String
    if isinstance(object, tuple):
        return Tuple

    if isinstance(object, typing.Sequence):
        return List
    if isinstance(object, bool):
        return Bool
    if isinstance(object, (int, float)):
        return Float
    if object == None:
        return Null
    if isinstance(object, Trait):
        return type(object)
    return Trait


def _construct_title(cls):
    if istype(cls, _NoTitle):
        return ""
    return cls._schema.get("title", cls.__name__)


class Trait(metaclass=_SchemaMeta):
    """A trait is an object validated by a validate ``jsonschema``.
    """

    _schema = None
    _type = "http://www.w3.org/2000/01/rdf-schema#Resource"

    def __new__(cls, *args, **kwargs):
        """__new__ validates an object against the type schema and dispatches different values in return.
        
        
        
Parameters
----------
*args
    The arguments for the base object class.
**kwargs
    The keyword arguments for the base object class.
    
Returns
-------
object
    Return an instance of the object and carry along the schema information.
"""
        args = cls._resolve_defaults(*args, **kwargs)
        args and cls.validate(args[0])
        if dataclasses.is_dataclass(cls):
            self = super().__new__(cls, *args, **kwargs)
            cls.validate(vars(self))
        elif isinstance(cls, _ConstType) or issubclass(cls, Tuple):
            if args:
                return _object_to_webtype(args[0])(args[0])
        else:
            self = super().__new__(cls, *args, **kwargs)
            self.__init__(*args, **kwargs)
        args or cls.validate(self)
        return self

    @classmethod
    def _resolve_defaults(cls, *args, **kwargs):
        if not args and not kwargs:
            if "default" in cls._schema:
                return (cls._schema.default,)
            elif "properties" in cls._schema:
                return (
                    {
                        k: v["default"]
                        for k, v in cls._schema["properties"].items()
                        if "default" in v
                    },
                )
        return args


class Description(_NoInit, Trait, _NoTitle, metaclass=_ConstType):
    """An empty type with a description
    
    
Examples
--------

    >>> yo = Description['yo']
    >>> yo._schema.toDict()
    {'description': 'yo'}

    """


class Examples(_NoInit, Trait, metaclass=_ConstType):
    """"""


class Default(_NoInit, Trait, metaclass=_ConstType):
    """"""


class Title(_NoInit, Trait, _NoTitle, metaclass=_ConstType):
    """An empty type with a title
    
    
Examples
--------

    >>> holla = Title['holla']
    >>> holla._schema.toDict()
    {'title': 'holla'}
    """


class Const(_NoInit, Trait, metaclass=_ConstType):
    """A constant
    
Examples
--------

    >>> Const[10]._schema.toDict()
    {'const': 10}
    
    
    >>> assert isinstance('thing', Const['thing'])
    >>> assert not isinstance('jawn', Const['thing']), "Because the compiler is from Philly."
    
"""


# ## Logical Types


class Bool(Trait, metaclass=_SchemaMeta):
    """Boolean type
        
Examples
--------

    >>> Bool(), Bool(True), Bool(False)
    (False, True, False)
    >>> assert (Bool + Default[True])()
    
Note
----
It is not possible to base class ``bool`` so object creation is customized.
    
"""

    _schema = dict(type="boolean")

    def __new__(cls, *args):
        args = cls._resolve_defaults(*args)
        args = args or (bool(),)
        args and cls.validate(args[0])
        return args[0]


class Null(Trait, metaclass=_SchemaMeta):
    """nil, none, null type
        
Examples
--------

    >>> Null(None)
    >>> assert (Null + Default[None])() is None
    
.. Null Type:
    https://json-schema.org/understanding-json-schema/reference/null.html
    
"""

    _schema = dict(type="null")

    def __new__(cls, *args):
        args = cls._resolve_defaults(*args)
        args and cls.validate(args[0])


# ## Numeric Types


class _NumericSchema(_SchemaMeta):
    """Meta operations for numerical types"""

    def __ge__(cls, object):
        """Inclusive minimum"""
        return cls + Minimum[object]

    def __gt__(cls, object):
        """Exclusive minimum"""
        return cls + ExclusiveMinimum[object]

    def __le__(cls, object):
        """Inclusive maximum"""
        return cls + Maximum[object]

    def __lt__(cls, object):
        """Exclusive maximum"""
        return cls + ExclusiveMaximum[object]

    __rgt__ = __lt__
    __rge__ = __le__
    __rlt__ = __gt__
    __rle__ = __ge__

    def __truediv__(cls, object):
        """multiple of a number"""
        return cls + MultipleOf[object]


class Integer(Trait, int, metaclass=_NumericSchema):
    """integer type
    
    
Examples
--------

    >>> assert isinstance(10, Integer)
    >>> assert not isinstance(10.1, Integer)
    >>> (Integer+Default[9])(9)
    9


    >>> bounded = (10< Integer)< 100
    >>> bounded._schema.toDict()
    {'type': 'integer', 'exclusiveMinimum': 10, 'exclusiveMaximum': 100}

    >>> assert isinstance(12, bounded)
    >>> assert not isinstance(0, bounded)
    >>> assert (Integer/3)(9) == 9
    
    """

    _schema = dict(type="integer")


class Float(Trait, float, metaclass=_NumericSchema):
    """float type
    
    
    >>> assert isinstance(10, Float)
    >>> assert isinstance(10.1, Float)

Symbollic conditions.

    >>> bounded = (10< Float)< 100
    >>> bounded._schema.toDict()
    {'type': 'number', 'exclusiveMinimum': 10, 'exclusiveMaximum': 100}

    >>> assert isinstance(12.1, bounded)
    >>> assert not isinstance(0.1, bounded)

Multiples

    >>> assert (Float+MultipleOf[3])(9) == 9


.. Numeric Types:
    https://json-schema.org/understanding-json-schema/reference/numeric.html
    
    """

    _schema = dict(type="number")


class MultipleOf(_NoInit, Trait, metaclass=_ConstType):
    """A multipleof constraint for numeric types."""


class Minimum(_NoInit, Trait, metaclass=_ConstType):
    """A minimum constraint for numeric types."""


class ExclusiveMinimum(_NoInit, Trait, metaclass=_ConstType):
    """A exclusive minimum constraint for numeric types."""


class Maximum(_NoInit, Trait, metaclass=_ConstType):
    """A exclusive maximum constraint for numeric types."""


class ExclusiveMaximum(_NoInit, Trait, metaclass=_ConstType):
    """A exclusive maximum constraint for numeric types."""


# ## Mapping types


class Properties(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    """Object properties."""


class _ObjectSchema(_SchemaMeta):
    """Meta operations for the object schema."""

    def __getitem__(cls, object):
        if isinstance(object, dict):
            return cls + Properties[object]
        if not isinstance(object, tuple):
            object = (object,)
        return cls + AdditionalProperties[AnyOf[object]]


class _Object(metaclass=_ObjectSchema):
    """Base class for validating object types."""

    _schema = dict(type="object")

    def __init_subclass__(cls, **kwargs):
        cls._schema = copy.deepcopy(cls._schema)
        cls._schema.update(kwargs)
        if "properties" in cls._schema:
            cls._schema.properties.update(
                Properties[cls.__annotations__]._schema.properties
            )
        else:
            cls._schema.update(Properties[cls.__annotations__]._schema)
        required = []
        for key in cls.__annotations__:
            if hasattr(cls, key):
                ...  # cls._schema.properties[key]['default'] = getattr(cls, key)
            else:
                required.append(key)
        if required:
            cls._schema["required"] = required

    @classmethod
    def from_config_file(cls, *object):
        args = __import__("anyconfig").load(object)
        return cls(args)


class Dict(Trait, dict, _Object):
    """dict type
    
Examples
--------

    >>> assert istype(Dict, __import__('collections').abc.MutableMapping)
    >>> assert (Dict + Default[{'b': 'foo'}])() == {'b': 'foo'}
    >>> assert (Dict + Default[{'b': 'foo'}])({'a': 'bar'}) == {'a': 'bar'}


    >>> assert isinstance({}, Dict)
    >>> assert not isinstance([], Dict)
    
    >>> assert isinstance({'a': 1}, Dict + Required['a',])
    >>> assert not isinstance({}, Dict + Required['a',])

    >>> assert not isinstance({'a': 'b'}, Dict[Integer, Float])
    >>> assert Dict[Integer]({'a': 1}) == {'a': 1}
    

    >>> Dict[{'a': int}]._schema.toDict()
    {'type': 'object', 'properties': {'a': {'type': 'integer'}}}
    >>> Dict[{'a': int}]({'a': 1})
    {'a': 1}

    
.. Object Type
    https://json-schema.org/understanding-json-schema/reference/object.html
    """

    def __new__(cls, *args, **kwargs):
        if not (args or kwargs):
            args = cls._resolve_defaults()
        else:
            args = (dict(*args, **kwargs),)
        return super().__new__(cls, *args)

    def _validate(self):
        type(self).validate(self)

    def __setitem__(self, key, object):
        """Only test the key being set to avoid invalid state."""
        properties = self._schema.get("properties", {})
        if key in properties:
            jsonschema.validate(
                object,
                self._schema.get("properties", {}).get(key, {}),
                format_checker=jsonschema.draft7_format_checker,
            )
        else:
            jsonschema.validate(
                {key: object},
                {**self._schema, "required": []},
                format_checker=jsonschema.draft7_format_checker,
            )
        super().__setitem__(key, object)

    def update(self, *args, **kwargs):
        jsonschema.validate(
            dict(*args, **kwargs),
            {**self._schema, "required": []},
            format_checker=jsonschema.draft7_format_checker,
        )
        super().update(*args, **kwargs)


class Bunch(Dict, munch.Munch):
    """Bunch type
    
Examples
--------

    >>> Bunch[{'a': int}]._schema.toDict()
    {'type': 'object', 'properties': {'a': {'type': 'integer'}}}
    >>> Bunch[{'a': int}]({'a': 1}).toDict()
    {'a': 1}

    
.. Munch Documentation
    https://pypi.org/project/munch/
    
"""


class DataClass(Trait, _Object):
    """Validating dataclass type
    
Examples
--------

    >>> class q(DataClass): a: int
    >>> q._schema.toDict()
    {'type': 'object', 'properties': {'a': {'type': 'integer'}}, 'required': ['a']}

    >>> q(a=10)
    q(a=10)
    
    >>> assert not isinstance({}, q)
    
    """

    def __new__(cls, *args, **kwargs):
        self = super(Trait, cls).__new__(cls)
        # dataclass instantiates the defaults for us.
        self.__init__(*args, **kwargs)
        return self

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        dataclasses.dataclass(cls)

    def __setattr__(self, key, object):
        """Only test the attribute being set to avoid invalid state."""
        if isinstance(object, dict):
            object = object.get(key)
        properties = self._schema.get("properties", {})
        (
            jsonschema.validate(
                object,
                self._schema.get("properties", {}).get(key, {}),
                format_checker=jsonschema.draft7_format_checker,
            )
            if key in properties
            else jsonschema.validate(
                {key: object},
                {**self._schema, "required": []},
                format_checker=jsonschema.draft7_format_checker,
            )
        )
        super().__setattr__(key, object)
        # trigger change here.


class AdditionalProperties(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    """Additional object properties."""


class Required(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    """Required properties."""


class minProperties(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Minimum number of properties."""


class maxProperties(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Maximum number of properties."""


class PropertyNames(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Propery name constraints."""


class Dependencies(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Properties dependencies."""


class PatternProperties(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    """Pattern properties names."""


# ## String Type


class _StringSchema(_SchemaMeta):
    """Meta operations for strings types.
    """

    def __mod__(cls, object):
        """A pattern string type."""
        return cls + Pattern[object]

    def __gt__(cls, object):
        """Minumum string length"""
        return cls + MinLength[object]

    def __lt__(cls, object):
        """Maximum string length"""
        return cls + MaxLength[object]

    __rgt__ = __rge__ = __le__ = __lt__
    __rlt__ = __rle__ = __ge__ = __gt__


class String(Trait, str, metaclass=_StringSchema):
    """string type.
    
    
Examples
--------

    >>> assert isinstance('abc', String)
    >>> assert (String+Default['abc'])() == 'abc'
    
String patterns

    >>> assert isinstance('abc', String%"^a")
    >>> assert not isinstance('abc', String%"^b")
    
String constraints
    
    >>> assert isinstance('abc', (2<String)<10) 
    >>> assert not isinstance('a', (2<String)<10)
    >>> assert not isinstance('a'*100, (2<String)<10)
    """

    _schema = dict(type="string")


class MinLength(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Minimum length of a string type."""


class MaxLength(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Maximum length of a string type."""


class ContentMediaType(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Content type of a string."""


class Pattern(Trait, _NoInit, metaclass=_ConstType):
    """A regular expression pattern."""


# ## Array Type


class _ListSchema(_SchemaMeta):
    """Meta operations for list types."""

    def __getitem__(cls, object):
        if istype(cls, Tuple) and isinstance(object, (tuple, list)):
            return cls + Items[list(object)]
        elif isinstance(object, tuple):
            return cls + Items[AnyOf[object]]
        return cls + Items[object]

    def __gt__(cls, object):
        """Minumum array length"""
        return cls + MinItems[object]

    def __lt__(cls, object):
        """Maximum array length"""
        return cls + MaxItems[object]

    __rgt__ = __rge__ = __le__ = __lt__
    __rlt__ = __rle__ = __ge__ = __gt__


class List(Trait, list, metaclass=_ListSchema):
    """List type
    
    
Examples
--------

List

    >>> assert isinstance([], List)
    >>> assert not isinstance({}, List)
    
Typed list

    >>> assert List[Integer]([1, 2, 3])
    >>> assert isinstance([1], List[Integer])
    >>> assert not isinstance([1.1], List[Integer])
    
    >>> List[Integer, String]._schema.toDict()
    {'type': 'array', 'items': {'anyOf': [{'type': 'integer'}, {'type': 'string'}]}}

    
Tuple        
    
    >>> assert List[Integer, String]([1, 'abc', 2])
    >>> assert isinstance([1, '1'], List[Integer, String])
    >>> assert not isinstance([1, {}], List[Integer, String])
    """

    _schema = dict(type="array")

    def __new__(cls, *args, **kwargs):
        args = cls._resolve_defaults(*args)
        if args and isinstance(args[0], tuple):
            args = (list(args[0]) + list(args[1:]),)
        return super().__new__(cls, *args, **kwargs)

    def _verify_item(self, object, id=None):
        items = self._schema.get("items", None)
        if items:
            if isinstance(items, dict):
                if isinstance(id, slice):
                    List[items].validate(object)
                else:
                    jsonschema.validate(
                        object, items, format_checker=jsonschema.draft7_format_checker
                    )
            elif isinstance(items, list):
                if isinstance(id, slice):
                    # condition for negative slices
                    Tuple[tuple(items[id])].validate(object)
                elif isinstance(id, int):
                    # condition for negative integers
                    jsonschema.validate(
                        object,
                        items[id],
                        format_checker=jsonschema.draft7_format_checker,
                    )

    def __setitem__(self, id, object):
        self._verify_item(object, id)
        super().__setitem__(id, object)

    def append(self, object):
        self._verify_item(object, len(self) + 1)
        super().append(object)

    def insert(self, id, object):
        self._verify_item(object, id)
        super().insert(id, object)

    def extend(self, object):
        id = slice(len(self), len(self) + 3)
        self._verify_item(object, id)
        super().extend(object)

    def pop(self, index=-1, default=None):
        value = super().pop(index, default)
        try:
            type(self).validate(self)
        except ValidationError:
            self.insert(index, value)


class Unique(List, uniqueItems=True):
    """Unique list type
    
    
Examples
--------

    >>> assert Unique(list('abc'))
    >>> assert isinstance([1,2], Unique)
    >>> assert not isinstance([1,1], Unique)
    
    """


class Tuple(List):
    """tuple type
    
Note
----
There are no tuples in json, they are typed lists.

    >>> assert Tuple._schema == List._schema
    
    
Examples
--------

    >>> assert isinstance([1,2], Tuple)
    >>> assert Tuple[Integer, String]([1, 'abc'])
    >>> Tuple[Integer, String]._schema.toDict()
    {'type': 'array', 'items': [{'type': 'integer'}, {'type': 'string'}]}

    >>> assert isinstance([1,'1'], Tuple[[Integer, String]])
    >>> assert not isinstance([1,1], Tuple[[Integer, String]])
    
    """


class UniqueItems(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Schema for unique items in a list."""


class Contains(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    ...


class Items(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    ...


class AdditionalItems(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    ...


class MinItems(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Minimum length of an array."""


class MaxItems(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    """Maximum length of an array."""


# ## Combining Schema


class Not(Trait, metaclass=_ContainerType):
    """not schema.
    

Examples
--------
    
    >>> assert Not[String](100) == 100   
    >>> assert not isinstance('abc', Not[String])
    
Note
----
See the __neg__ method for symbollic not composition.

.. Not
    https://json-schema.org/understanding-json-schema/reference/combining.html#not
"""


class AnyOf(Trait, _NoInit, metaclass=_ContainerType):
    """anyOf combined schema.
    
Examples
--------

    >>> assert AnyOf[Integer, String]('abc')
    >>> assert isinstance(10, AnyOf[Integer, String])
    >>> assert not isinstance([], AnyOf[Integer, String])
    
.. anyOf
    https://json-schema.org/understanding-json-schema/reference/combining.html#anyof
"""


class AllOf(Trait, _NoInit, metaclass=_ContainerType):
    """allOf combined schema.
    
Examples
--------

    >>> assert AllOf[Float>0, Integer/3](9)
    >>> assert isinstance(9, AllOf[Float>0, Integer/3])
    >>> assert not isinstance(-9, AllOf[Float>0, Integer/3])
    
.. allOf
    https://json-schema.org/understanding-json-schema/reference/combining.html#allof
"""


class OneOf(Trait, _NoInit, metaclass=_ContainerType):
    """oneOf combined schema.

Examples
--------

    >>> assert OneOf[Float>0, Integer/3](-9)
    >>> assert isinstance(-9, OneOf[Float>0, Integer/3])
    >>> assert not isinstance(9, OneOf[Float>0, Integer/3])

    
.. oneOf
    https://json-schema.org/understanding-json-schema/reference/combining.html#oneof
"""


class Enum(Trait, metaclass=_ConstType):
    """An enumerate type that is restricted to its inputs.
    
    
Examples
--------

    >>> assert Enum['cat', 'dog']('cat')
    >>> assert isinstance('cat', Enum['cat', 'dog'])
    >>> assert not isinstance('🐢', Enum['cat', 'dog'])

    
    """


# ## String Formats

_formats = "color date-time time date email idn-email hostname idn-hostname ipv4 ipv6 uri uri-reference iri iri-reference uri-template json-pointer relative-json-pointer regex".split()


class ContentEncoding(
    Enum["7bit 8bit binary quoted-printable base64".split()], _NoInit, _NoTitle
):
    """Content encodings for a string.
    
.. Json schema media:
    https://json-schema.org/understanding-json-schema/reference/non_json_data.html
"""


class Format(Trait, _NoInit, _NoTitle, metaclass=_ConstType):
    ...


for key in _formats:
    locals()[key.capitalize()] = String + Format[key]
Regex.compile = re.compile
del key


class If(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    """if condition type
    
.. Conditions:
    https://json-schema.org/understanding-json-schema/reference/conditionals.html
    """


class Then(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    """then condition type"""


class Else(Trait, _NoInit, _NoTitle, metaclass=_ContainerType):
    """else condition type"""


class Link:
    _registered_links = None
    _registered_id = None
    _deferred_changed = None
    _deferred_prior = None
    _depth = 0

    def __enter__(self):
        self._depth += 1

    def __exit__(self, *e):
        self._depth -= 1
        self._deferred_changed and e == (None, None, None) and self._propagate()

    def link(this, source, that, target):
        this.dlink(source, that, target)
        that.dlink(target, this, source)
        return this

    def dlink(self, source, that, target, callable=None):
        self._registered_links = self._registered_links or {}
        self._registered_id = self._registered_id or {}
        self._registered_links[source] = self._registered_links.get(source, {})
        if id(that) not in self._registered_links[source]:
            self._registered_links[source][id(that)] = {}
        if target not in self._registered_links[source][id(that)]:
            self._registered_links[source][id(that)][target] = None
        if id(that) not in self._registered_id:
            self._registered_id[id(that)] = that
        self._registered_links[source][id(that)][target] = callable
        return self

    def observe(self, source, callable=None):
        """The callable has to define a signature."""
        self._registered_links = self._registered_links or {}
        self._registered_id = self._registered_id or {}
        self._registered_links[source] = self._registered_links.get(source, {})
        if id(self) not in self._registered_links[source]:
            self._registered_links[source][id(self)] = []
        if id(self) not in self._registered_id:
            self._registered_id[id(self)] = self
        self._registered_links[source][id(self)].append(callable)
        return self

    def _propagate(self, *changed, **prior):
        self._deferred_changed = list(self._deferred_changed or changed)
        self._deferred_prior = {**prior, **(self._deferred_prior or {})}

        if self._depth > 0:
            return
        with self:
            while self._deferred_changed:
                key = self._deferred_changed.pop(-1)
                old = self._deferred_prior.pop(key, None)
                for hash in (
                    self._registered_links[key] if self._registered_links else []
                ):
                    thing = self._registered_id[hash]
                    if hash == id(self):
                        for func in self._registered_links[key][hash]:
                            func(
                                self,
                                dict(
                                    new=getattr(self, key, None),
                                    old=old,
                                    object=self,
                                    name=key,
                                ),
                            )
                    else:
                        for to, value in self._registered_links[key][hash].items():
                            if callable(value):
                                thing.update({to: callable(self[key])})
                            else:
                                if thing.get(to, None) is not self.get(
                                    key, inspect._empty
                                ):
                                    thing.update({to: self[key]})

    def __setitem__(self, key, object):
        with self:
            prior = self.get(key, None)
            super().__setitem__(key, object)
            if object is not prior:
                self._propagate(key, **{key: prior})

    def update(self, *args, **kwargs):
        with self:
            args = dict(*args, **kwargs)
            prior = {x: self[x] for x in args if x in self}
            super().update(args)
            prior = {
                k: v for k, v in prior.items() if v is not self.get(k, inspect._empty)
            }
            prior and self._propagate(*prior, **prior)


class Evented(Link, Bunch):
    """An evented dictionary/bunch

Examples
--------

    >>> e, f = Evented(), Evented()
    >>> e.link('a', f, 'b')
    Evented({})
    >>> e['a'] = 1
    >>> f.toDict()
    {'b': 1}
    >>> e.update(a=100)
    >>> f.toDict()
    {'b': 100}
    
    >>> f['b'] = 2
    >>> assert e['a'] == f['b']
    >>> e = Evented().observe('a', print)
    >>> e['a'] = 2
    Evented({'a': 2}) {'new': 2, 'old': None, 'object': Evented({'a': 2}), 'name': 'a'}
    
    """


# ## Configuration classes


class Configurable(DataClass):
    """A configurable classs that is create with dataclass syntax."""