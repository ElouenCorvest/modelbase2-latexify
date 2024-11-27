from __future__ import annotations

__all__ = [
    "AtomicUnit",
    "Compartment",
    "CompositeUnit",
    "Compound",
    "Derived",
    "Function",
    "Parameter",
    "Reaction",
]

from dataclasses import dataclass


@dataclass
class AtomicUnit:
    kind: str
    exponent: int
    scale: int
    multiplier: float


@dataclass
class CompositeUnit:
    sbml_id: str
    units: list


@dataclass
class Parameter:
    value: float
    is_constant: bool


@dataclass
class Compartment:
    name: str
    dimensions: int
    size: float
    units: str
    is_constant: bool


@dataclass
class Compound:
    compartment: str | None
    initial_amount: float
    substance_units: str | None
    has_only_substance_units: bool
    has_boundary_condition: bool
    is_constant: bool
    is_concentration: bool


@dataclass
class Derived:
    body: str
    args: list[str]


@dataclass
class Function:
    body: str
    args: list[str]


@dataclass
class Reaction:
    body: str
    stoichiometry: dict
    args: list[str]
