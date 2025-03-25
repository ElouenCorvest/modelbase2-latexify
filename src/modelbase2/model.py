"""Model for Metabolic System Representation.

This module provides the core Model class and supporting functionality for representing
metabolic models, including reactions, variables, parameters and derived quantities.

"""

from __future__ import annotations

import copy
import inspect
import itertools as it
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self, cast

import latexify
import latexify.exceptions
import numpy as np
import pandas as pd
import regex as re

from modelbase2 import fns
from modelbase2.types import (
    Array,
    Derived,
    Float,
    Reaction,
    Readout,
)

__all__ = ["ArityMismatchError", "Model", "ModelCache", "SortError"]

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from inspect import FullArgSpec

    from modelbase2.types import AbstractSurrogate, Callable, Param, RateFn, RetType


class SortError(Exception):
    """Raised when dependencies cannot be sorted topologically.

    This typically indicates circular dependencies in model components.
    """

    def __init__(self, unsorted: list[str], order: list[str]) -> None:
        """Initialise exception."""
        msg = (
            f"Exceeded max iterations on sorting derived. "
            "Check if there are circular references.\n"
            f"Unsorted: {unsorted}\n"
            f"Order: {order}"
        )
        super().__init__(msg)


def _get_all_args(argspec: FullArgSpec) -> list[str]:
    kwonly = [] if argspec.kwonlyargs is None else argspec.kwonlyargs
    return argspec.args + kwonly


def _check_function_arity(function: Callable, arity: int) -> bool:
    """Check if the amount of arguments given fits the argument count of the function."""
    argspec = inspect.getfullargspec(function)
    # Give up on *args functions
    if argspec.varargs is not None:
        return True

    # The sane case
    if len(argspec.args) == arity:
        return True

    # It might be that the user has set some args to default values,
    # in which case they are also ok (might be kwonly as well)
    defaults = argspec.defaults
    if defaults is not None and len(argspec.args) + len(defaults) == arity:
        return True
    kwonly = argspec.kwonlyargs
    return bool(defaults is not None and len(argspec.args) + len(kwonly) == arity)


class ArityMismatchError(Exception):
    """Mismatch between python function and model arguments."""

    def __init__(self, name: str, fn: Callable, args: list[str]) -> None:
        """Format message."""
        argspec = inspect.getfullargspec(fn)

        message = f"Function arity mismatch for {name}.\n"
        message += "\n".join(
            (
                f"{i:<8.8} | {j:<10.10}"
                for i, j in [
                    ("Fn args", "Model args"),
                    ("-------", "----------"),
                    *it.zip_longest(argspec.args, args, fillvalue="---"),
                ]
            )
        )
        super().__init__(message)


def _invalidate_cache(method: Callable[Param, RetType]) -> Callable[Param, RetType]:
    """Decorator that invalidates model cache when decorated method is called.

    Args:
        method: Method to wrap with cache invalidation

    Returns:
        Wrapped method that clears cache before execution

    """

    def wrapper(
        *args: Param.args,
        **kwargs: Param.kwargs,
    ) -> RetType:
        self = cast(Model, args[0])
        self._cache = None
        return method(*args, **kwargs)

    return wrapper  # type: ignore


def _sort_dependencies(
    available: set[str], elements: list[tuple[str, set[str]]]
) -> list[str]:
    """Sort model elements topologically based on their dependencies.

    Args:
        available: Set of available component names
        elements: List of (name, dependencies) tuples to sort

    Returns:
        List of element names in dependency order

    Raises:
        SortError: If circular dependencies are detected

    """
    from queue import Empty, SimpleQueue

    order = []
    # FIXME: what is the worst case here?
    max_iterations = len(elements) ** 2
    queue: SimpleQueue[tuple[str, set[str]]] = SimpleQueue()
    for k, v in elements:
        queue.put((k, v))

    last_name = None
    i = 0
    while True:
        try:
            new, args = queue.get_nowait()
        except Empty:
            break
        if args.issubset(available):
            available.add(new)
            order.append(new)
        else:
            if last_name == new:
                order.append(new)
                break
            queue.put((new, args))
            last_name = new
        i += 1

        # Failure case
        if i > max_iterations:
            unsorted = []
            while True:
                try:
                    unsorted.append(queue.get_nowait()[0])
                except Empty:
                    break
            raise SortError(unsorted=unsorted, order=order)
    return order


@dataclass(slots=True)
class ModelCache:
    """ModelCache is a class that stores various model-related data structures.

    Attributes:
        var_names: A list of variable names.
        parameter_values: A dictionary mapping parameter names to their values.
        derived_parameters: A dictionary mapping parameter names to their derived parameter objects.
        derived_variables: A dictionary mapping variable names to their derived variable objects.
        stoich_by_cpds: A dictionary mapping compound names to their stoichiometric coefficients.
        dyn_stoich_by_cpds: A dictionary mapping compound names to their dynamic stoichiometric coefficients.
        dxdt: A pandas Series representing the rate of change of variables.

    """

    var_names: list[str]
    all_parameter_values: dict[str, float]
    derived_parameter_names: list[str]
    derived_variable_names: list[str]
    stoich_by_cpds: dict[str, dict[str, float]]
    dyn_stoich_by_cpds: dict[str, dict[str, Derived]]
    dxdt: pd.Series


@dataclass(slots=True)
class Model:
    """Represents a metabolic model.

    Attributes:
        _ids: Dictionary mapping internal IDs to names.
        _variables: Dictionary of model variables and their initial values.
        _parameters: Dictionary of model parameters and their values.
        _derived: Dictionary of derived quantities.
        _readouts: Dictionary of readout functions.
        _reactions: Dictionary of reactions in the model.
        _surrogates: Dictionary of surrogate models.
        _cache: Cache for storing model-related data structures.

    """

    _ids: dict[str, str] = field(default_factory=dict)
    _variables: dict[str, float] = field(default_factory=dict)
    _parameters: dict[str, float] = field(default_factory=dict)
    _derived: dict[str, Derived] = field(default_factory=dict)
    _readouts: dict[str, Readout] = field(default_factory=dict)
    _reactions: dict[str, Reaction] = field(default_factory=dict)
    _math_exprs: dict[str, str] = field(default_factory=dict)
    _surrogates: dict[str, AbstractSurrogate] = field(default_factory=dict)
    _cache: ModelCache | None = None

    ###########################################################################
    # Cache
    ###########################################################################

    def _create_cache(self) -> ModelCache:
        """Creates and initializes the model cache.

        This method constructs a cache that includes parameter values, stoichiometry
        by compounds, dynamic stoichiometry by compounds, derived variables, and
        derived parameters. It processes the model's parameters, variables, derived
        elements, reactions, and surrogates to populate the cache.

        Returns:
            ModelCache: An instance of ModelCache containing the initialized cache data.

        """
        all_parameter_values: dict[str, float] = self._parameters.copy()
        all_parameter_names: set[str] = set(all_parameter_values)

        # Sanity checks
        for name, el in it.chain(
            self._derived.items(),
            self._readouts.items(),
            self._reactions.items(),
        ):
            if not _check_function_arity(el.fn, len(el.args)):
                raise ArityMismatchError(name, el.fn, el.args)

        # Sort derived
        derived_order = _sort_dependencies(
            available=set(self._parameters) | set(self._variables) | {"time"},
            elements=[(k, set(v.args)) for k, v in self._derived.items()],
        )

        # Split derived into parameters and variables
        derived_variable_names: list[str] = []
        derived_parameter_names: list[str] = []
        for name in derived_order:
            derived = self._derived[name]
            if all(i in all_parameter_names for i in derived.args):
                all_parameter_names.add(name)
                derived_parameter_names.append(name)
                all_parameter_values[name] = float(
                    derived.fn(*(all_parameter_values[i] for i in derived.args))
                )
            else:
                derived_variable_names.append(name)

        stoich_by_compounds: dict[str, dict[str, float]] = {}
        dyn_stoich_by_compounds: dict[str, dict[str, Derived]] = {}

        for rxn_name, rxn in self._reactions.items():
            for cpd_name, factor in rxn.stoichiometry.items():
                d_static = stoich_by_compounds.setdefault(cpd_name, {})

                if isinstance(factor, Derived):
                    if all(i in all_parameter_names for i in factor.args):
                        d_static[rxn_name] = float(
                            factor.fn(*(all_parameter_values[i] for i in factor.args))
                        )
                    else:
                        dyn_stoich_by_compounds.setdefault(cpd_name, {})[rxn_name] = (
                            factor
                        )
                else:
                    d_static[rxn_name] = factor

        for surrogate in self._surrogates.values():
            for rxn_name, rxn in surrogate.stoichiometries.items():
                for cpd_name, factor in rxn.items():
                    stoich_by_compounds.setdefault(cpd_name, {})[rxn_name] = factor

        var_names = self.get_variable_names()
        dxdt = pd.Series(np.zeros(len(var_names), dtype=float), index=var_names)

        self._cache = ModelCache(
            var_names=var_names,
            all_parameter_values=all_parameter_values,
            stoich_by_cpds=stoich_by_compounds,
            dyn_stoich_by_cpds=dyn_stoich_by_compounds,
            derived_variable_names=derived_variable_names,
            derived_parameter_names=derived_parameter_names,
            dxdt=dxdt,
        )
        return self._cache

    ###########################################################################
    # Ids
    ###########################################################################

    @property
    def ids(self) -> dict[str, str]:
        """Returns a copy of the _ids dictionary.

        The _ids dictionary contains key-value pairs where both keys and values are strings.

        Returns:
            dict[str, str]: A copy of the _ids dictionary.

        """
        return self._ids.copy()

    def _insert_id(self, *, name: str, ctx: str) -> None:
        """Inserts an identifier into the model's internal ID dictionary.

        Args:
            name: The name of the identifier to insert.
            ctx: The context associated with the identifier.

        Raises:
            KeyError: If the name is "time", which is a protected variable.
            NameError: If the name already exists in the model's ID dictionary.

        """
        if name == "time":
            msg = "time is a protected variable for time"
            raise KeyError(msg)

        if name in self._ids:
            msg = f"Model already contains {ctx} called '{name}'"
            raise NameError(msg)
        self._ids[name] = ctx

    def _remove_id(self, *, name: str) -> None:
        """Remove an ID from the internal dictionary.

        Args:
            name (str): The name of the ID to be removed.

        Raises:
            KeyError: If the specified name does not exist in the dictionary.

        """
        del self._ids[name]

    ##########################################################################
    # Parameters
    ##########################################################################

    @_invalidate_cache
    def add_parameter(self, name: str, value: float) -> Self:
        """Adds a parameter to the model.

        Examples:
            >>> model.add_parameter("k1", 0.1)

        Args:
            name (str): The name of the parameter.
            value (float): The value of the parameter.

        Returns:
            Self: The instance of the model with the added parameter.

        """
        self._insert_id(name=name, ctx="parameter")
        self._parameters[name] = value
        return self

    def add_parameters(self, parameters: dict[str, float]) -> Self:
        """Adds multiple parameters to the model.

        Examples:
            >>> model.add_parameters({"k1": 0.1, "k2": 0.2})

        Args:
            parameters (dict[str, float]): A dictionary where the keys are parameter names
                                           and the values are the corresponding parameter values.

        Returns:
            Self: The instance of the model with the added parameters.

        """
        for k, v in parameters.items():
            self.add_parameter(k, v)
        return self

    @property
    def parameters(self) -> dict[str, float]:
        """Returns the parameters of the model.

        Examples:
            >>> model.parameters
                {"k1": 0.1, "k2": 0.2}

        Returns:
            parameters: A dictionary where the keys are parameter names (as strings)
                  and the values are parameter values (as floats).

        """
        return self._parameters.copy()

    def get_parameter_names(self) -> list[str]:
        """Retrieve the names of the parameters.

        Examples:
            >>> model.get_parameter_names()
                ['k1', 'k2']

        Returns:
            parametes: A list containing the names of the parameters.

        """
        return list(self._parameters)

    @_invalidate_cache
    def remove_parameter(self, name: str) -> Self:
        """Remove a parameter from the model.

        Examples:
            >>> model.remove_parameter("k1")

        Args:
            name: The name of the parameter to remove.

        Returns:
            Self: The instance of the model with the parameter removed.

        """
        self._remove_id(name=name)
        self._parameters.pop(name)
        return self

    def remove_parameters(self, names: list[str]) -> Self:
        """Remove multiple parameters from the model.

        Examples:
            >>> model.remove_parameters(["k1", "k2"])

        Args:
            names: A list of parameter names to be removed.

        Returns:
            Self: The instance of the model with the specified parameters removed.

        """
        for name in names:
            self.remove_parameter(name)
        return self

    @_invalidate_cache
    def update_parameter(self, name: str, value: float) -> Self:
        """Update the value of a parameter.

        Examples:
            >>> model.update_parameter("k1", 0.2)

        Args:
            name: The name of the parameter to update.
            value: The new value for the parameter.

        Returns:
            Self: The instance of the class with the updated parameter.

        Raises:
            NameError: If the parameter name is not found in the parameters.

        """
        if name not in self._parameters:
            msg = f"'{name}' not found in parameters"
            raise KeyError(msg)
        self._parameters[name] = value
        return self

    def update_parameters(self, parameters: dict[str, float]) -> Self:
        """Update multiple parameters of the model.

        Examples:
            >>> model.update_parameters({"k1": 0.2, "k2": 0.3})

        Args:
            parameters: A dictionary where keys are parameter names and values are the new parameter values.

        Returns:
            Self: The instance of the model with updated parameters.

        """
        for k, v in parameters.items():
            self.update_parameter(k, v)
        return self

    def scale_parameter(self, name: str, factor: float) -> Self:
        """Scales the value of a specified parameter by a given factor.

        Examples:
            >>> model.scale_parameter("k1", 2.0)

        Args:
            name: The name of the parameter to be scaled.
            factor: The factor by which to scale the parameter's value.

        Returns:
            Self: The instance of the class with the updated parameter.

        """
        return self.update_parameter(name, self._parameters[name] * factor)

    def scale_parameters(self, parameters: dict[str, float]) -> Self:
        """Scales the parameters of the model.

        Examples:
            >>> model.scale_parameters({"k1": 2.0, "k2": 0.5})

        Args:
            parameters: A dictionary where the keys are parameter names
                        and the values are the scaling factors.

        Returns:
            Self: The instance of the model with scaled parameters.

        """
        for k, v in parameters.items():
            self.scale_parameter(k, v)
        return self

    @_invalidate_cache
    def make_parameter_dynamic(
        self,
        name: str,
        initial_value: float | None = None,
        stoichiometries: dict[str, float] | None = None,
    ) -> Self:
        """Converts a parameter to a dynamic variable in the model.

        Examples:
            >>> model.make_parameter_dynamic("k1")
            >>> model.make_parameter_dynamic("k2", initial_value=0.5)

        This method removes the specified parameter from the model and adds it as a variable with an optional initial value.

        Args:
            name: The name of the parameter to be converted.
            initial_value: The initial value for the new variable. If None, the current value of the parameter is used. Defaults to None.
            stoichiometries: A dictionary mapping reaction names to stoichiometries for the new variable. Defaults to None.

        Returns:
            Self: The instance of the model with the parameter converted to a variable.

        """
        value = self._parameters[name] if initial_value is None else initial_value
        self.remove_parameter(name)
        self.add_variable(name, value)

        if stoichiometries is not None:
            for rxn_name, value in stoichiometries.items():
                target = False
                if rxn_name in self._reactions:
                    target = True
                    cast(dict, self._reactions[name].stoichiometry)[name] = value
                else:
                    for surrogate in self._surrogates.values():
                        if rxn_name in surrogate.stoichiometries:
                            target = True
                            surrogate.stoichiometries[rxn_name][name] = value
                if not target:
                    msg = f"Reaction '{rxn_name}' not found in reactions or surrogates"
                    raise KeyError(msg)

        return self

    ##########################################################################
    # Variables
    ##########################################################################

    @property
    def variables(self) -> dict[str, float]:
        """Returns a copy of the variables dictionary.

        Examples:
            >>> model.variables
                {"x1": 1.0, "x2": 2.0}

        This method returns a copy of the internal dictionary that maps variable
        names to their corresponding float values.

        Returns:
            dict[str, float]: A copy of the variables dictionary.

        """
        return self._variables.copy()

    @_invalidate_cache
    def add_variable(self, name: str, initial_condition: float) -> Self:
        """Adds a variable to the model with the given name and initial condition.

        Examples:
            >>> model.add_variable("x1", 1.0)

        Args:
            name: The name of the variable to add.
            initial_condition: The initial condition value for the variable.

        Returns:
            Self: The instance of the model with the added variable.

        """
        self._insert_id(name=name, ctx="variable")
        self._variables[name] = initial_condition
        return self

    def add_variables(self, variables: dict[str, float]) -> Self:
        """Adds multiple variables to the model with their initial conditions.

        Examples:
            >>> model.add_variables({"x1": 1.0, "x2": 2.0})

        Args:
            variables: A dictionary where the keys are variable names (str)
                       and the values are their initial conditions (float).

        Returns:
            Self: The instance of the model with the added variables.

        """
        for name, y0 in variables.items():
            self.add_variable(name=name, initial_condition=y0)
        return self

    @_invalidate_cache
    def remove_variable(self, name: str) -> Self:
        """Remove a variable from the model.

        Examples:
            >>> model.remove_variable("x1")

        Args:
            name: The name of the variable to remove.

        Returns:
            Self: The instance of the model with the variable removed.

        """
        self._remove_id(name=name)
        del self._variables[name]
        return self

    def remove_variables(self, variables: Iterable[str]) -> Self:
        """Remove multiple variables from the model.

        Examples:
            >>> model.remove_variables(["x1", "x2"])

        Args:
            variables: An iterable of variable names to be removed.

        Returns:
            Self: The instance of the model with the specified variables removed.

        """
        for variable in variables:
            self.remove_variable(name=variable)
        return self

    @_invalidate_cache
    def update_variable(self, name: str, initial_condition: float) -> Self:
        """Updates the value of a variable in the model.

        Examples:
            >>> model.update_variable("x1", 2.0)

        Args:
            name: The name of the variable to update.
            initial_condition: The initial condition or value to set for the variable.

        Returns:
            Self: The instance of the model with the updated variable.

        """
        if name not in self._variables:
            msg = f"'{name}' not found in variables"
            raise KeyError(msg)
        self._variables[name] = initial_condition
        return self

    def get_variable_names(self) -> list[str]:
        """Retrieve the names of all variables.

        Examples:
            >>> model.get_variable_names()
                ["x1", "x2"]

        Returns:
            variable_names: A list containing the names of all variables.

        """
        return list(self._variables)

    def get_initial_conditions(self) -> dict[str, float]:
        """Retrieve the initial conditions of the model.

        Examples:
            >>> model.get_initial_conditions()
                {"x1": 1.0, "x2": 2.0}

        Returns:
            initial_conditions: A dictionary where the keys are variable names and the values are their initial conditions.

        """
        return self._variables

    def make_variable_static(self, name: str, value: float | None = None) -> Self:
        """Converts a variable to a static parameter.

        This removes the variable from the stoichiometries of all reactions and surrogates.
        It is not re-inserted if `Model.make_parameter_dynamic` is called.

        Examples:
            >>> model.make_variable_static("x1")
            >>> model.make_variable_static("x2", value=2.0)

        Args:
            name: The name of the variable to be made static.
            value: The value to assign to the parameter.
                   If None, the current value of the variable is used. Defaults to None.

        Returns:
            Self: The instance of the class for method chaining.

        """
        value = self._variables[name] if value is None else value
        self.remove_variable(name)
        self.add_parameter(name, value)

        # Remove from stoichiometries
        for reaction in self._reactions.values():
            if name in reaction.stoichiometry:
                cast(dict, reaction.stoichiometry).pop(name)
        for surrogate in self._surrogates.values():
            surrogate.stoichiometries = {
                k: {k2: v2 for k2, v2 in v.items() if k2 != name}
                for k, v in surrogate.stoichiometries.items()
                if k != name
            }
        return self

    ##########################################################################
    # Derived
    ##########################################################################

    @property
    def derived(self) -> dict[str, Derived]:
        """Returns a copy of the derived quantities.

        Examples:
            >>> model.derived
                {"d1": Derived(fn1, ["x1", "x2"]),
                 "d2": Derived(fn2, ["x1", "d1"])}

        Returns:
            dict[str, Derived]: A copy of the derived dictionary.

        """
        return self._derived.copy()

    @property
    def derived_variables(self) -> dict[str, Derived]:
        """Returns a dictionary of derived variables.

        Examples:
            >>> model.derived_variables()
                {"d1": Derived(fn1, ["x1", "x2"]),
                 "d2": Derived(fn2, ["x1", "d1"])}

        Returns:
            derived_variables: A dictionary where the keys are strings
            representing the names of the derived variables and the values are
            instances of DerivedVariable.

        """
        if (cache := self._cache) is None:
            cache = self._create_cache()
        derived = self._derived
        return {k: derived[k] for k in cache.derived_variable_names}

    @property
    def derived_parameters(self) -> dict[str, Derived]:
        """Returns a dictionary of derived parameters.

        Examples:
            >>> model.derived_parameters()
                {"kd1": Derived(fn1, ["k1", "k2"]),
                 "kd2": Derived(fn2, ["k1", "kd1"])}

        Returns:
            A dictionary where the keys are
            parameter names and the values are Derived.

        """
        if (cache := self._cache) is None:
            cache = self._create_cache()
        derived = self._derived
        return {k: derived[k] for k in cache.derived_parameter_names}

    @_invalidate_cache
    def add_derived(
        self,
        name: str,
        fn: RateFn,
        *,
        args: list[str],
        math: str | None = None,
    ) -> Self:
        """Adds a derived attribute to the model.

        Examples:
            >>> model.add_derived("d1", add, args=["x1", "x2"])

        Args:
            name: The name of the derived attribute.
            fn: The function used to compute the derived attribute.
            args: The list of arguments to be passed to the function.
            math: A str in LaTeX formatting that should be appointed to this Derived.

        Returns:
            Self: The instance of the model with the added derived attribute.

        """
        self._insert_id(name=name, ctx="derived")
        self._derived[name] = Derived(fn, args, math)
        return self

    def get_derived_parameter_names(self) -> list[str]:
        """Retrieve the names of derived parameters.

        Examples:
            >>> model.get_derived_parameter_names()
                ["kd1", "kd2"]

        Returns:
            A list of names of the derived parameters.

        """
        return list(self.derived_parameters)

    def get_derived_variable_names(self) -> list[str]:
        """Retrieve the names of derived variables.

        Examples:
            >>> model.get_derived_variable_names()
                ["d1", "d2"]

        Returns:
            A list of names of derived variables.

        """
        return list(self.derived_variables)

    @_invalidate_cache
    def update_derived(
        self,
        name: str,
        fn: RateFn | None = None,
        *,
        args: list[str] | None = None,
        math: str | None = None,
    ) -> Self:
        """Updates the derived function and its arguments for a given name.

        Examples:
            >>> model.update_derived("d1", add, ["x1", "x2"])

        Args:
            name: The name of the derived function to update.
            fn: The new derived function. If None, the existing function is retained. Defaults to None.
            args: The new arguments for the derived function. If None, the existing arguments are retained. Defaults to None.
            math: A str in LaTeX formatting that should be appointed to this Derived.

        Returns:
            Self: The instance of the class with the updated derived function and arguments.

        """
        der = self._derived[name]
        der.fn = der.fn if fn is None else fn
        der.args = der.args if args is None else args
        der.math = der.math if math is None else math
        return self

    @_invalidate_cache
    def remove_derived(self, name: str) -> Self:
        """Remove a derived attribute from the model.

        Examples:
            >>> model.remove_derived("d1")

        Args:
            name: The name of the derived attribute to remove.

        Returns:
            Self: The instance of the model with the derived attribute removed.

        """
        self._remove_id(name=name)
        self._derived.pop(name)
        return self

    ###########################################################################
    # Reactions
    ###########################################################################

    @property
    def reactions(self) -> dict[str, Reaction]:
        """Retrieve the reactions in the model.

        Examples:
            >>> model.reactions
                {"r1": Reaction(fn1, {"x1": -1, "x2": 1}, ["k1"]),

        Returns:
            dict[str, Reaction]: A deep copy of the reactions dictionary.

        """
        return copy.deepcopy(self._reactions)

    def get_stoichiometries(
        self, concs: dict[str, float] | None = None, time: float = 0.0
    ) -> pd.DataFrame:
        """Retrieve the stoichiometries of the model.

        Examples:
            >>> model.stoichiometries()
                v1  v2
            x1 -1   1
            x2  1  -1

        Returns:
            pd.DataFrame: A DataFrame containing the stoichiometries of the model.

        """
        if (cache := self._cache) is None:
            cache = self._create_cache()
        args = self.get_args(concs=concs, time=time)

        stoich_by_cpds = copy.deepcopy(cache.stoich_by_cpds)
        for cpd, stoich in cache.dyn_stoich_by_cpds.items():
            for rxn, derived in stoich.items():
                stoich_by_cpds[cpd][rxn] = float(
                    derived.fn(*(args[i] for i in derived.args))
                )
        return pd.DataFrame(stoich_by_cpds).T.fillna(0)

    @_invalidate_cache
    def add_reaction(
        self,
        name: str,
        fn: RateFn,
        *,
        args: list[str],
        stoichiometry: Mapping[str, float | str | Derived],
        math: str | None = None,
    ) -> Self:
        """Adds a reaction to the model.

        Examples:
            >>> model.add_reaction("v1",
            ...     fn=mass_action,
            ...     args=["x1", "kf1"],
            ...     stoichiometry={"x1": -1, "x2": 1},
            ... )

        Args:
            name: The name of the reaction.
            fn: The function representing the reaction.
            args: A list of arguments for the reaction function.
            stoichiometry: The stoichiometry of the reaction, mapping species to their coefficients.
            math: A str in LaTeX formatting that should be appointed to this reaction

        Returns:
            Self: The instance of the model with the added reaction.

        """
        self._insert_id(name=name, ctx="reaction")

        stoich: dict[str, Derived | float] = {
            k: Derived(fns.constant, [v]) if isinstance(v, str) else v
            for k, v in stoichiometry.items()
        }
        self._reactions[name] = Reaction(fn=fn, stoichiometry=stoich, args=args, math=math)
        return self

    def get_reaction_names(self) -> list[str]:
        """Retrieve the names of all reactions.

        Examples:
            >>> model.get_reaction_names()
                ["v1", "v2"]

        Returns:
            list[str]: A list containing the names of the reactions.

        """
        return list(self._reactions)

    @_invalidate_cache
    def update_reaction(
        self,
        name: str,
        fn: RateFn | None = None,
        math: str | None = None,
        *,
        args: list[str] | None = None,
        stoichiometry: Mapping[str, float | Derived | str] | None = None,
    ) -> Self:
        """Updates the properties of an existing reaction in the model.

        Examples:
            >>> model.update_reaction("v1",
            ...     fn=mass_action,
            ...     args=["x1", "kf1"],
            ...     stoichiometry={"x1": -1, "x2": 1},
            ... )

        Args:
            name: The name of the reaction to update.
            fn: The new function for the reaction. If None, the existing function is retained.
            args: The new arguments for the reaction. If None, the existing arguments are retained.
            stoichiometry: The new stoichiometry for the reaction. If None, the existing stoichiometry is retained.

        Returns:
            Self: The instance of the model with the updated reaction.

        """
        rxn = self._reactions[name]
        rxn.fn = rxn.fn if fn is None else fn
        rxn.math = rxn.math if math is None else math

        if stoichiometry is not None:
            stoich = {
                k: Derived(fns.constant, [v]) if isinstance(v, str) else v
                for k, v in stoichiometry.items()
            }
            rxn.stoichiometry = stoich
        rxn.args = rxn.args if args is None else args
        return self

    @_invalidate_cache
    def remove_reaction(self, name: str) -> Self:
        """Remove a reaction from the model by its name.

        Examples:
            >>> model.remove_reaction("v1")

        Args:
            name: The name of the reaction to be removed.

        Returns:
            Self: The instance of the model with the reaction removed.

        """
        self._remove_id(name=name)
        self._reactions.pop(name)
        return self

    # def update_stoichiometry_of_cpd(
    #     self,
    #     rate_name: str,
    #     compound: str,
    #     value: float,
    # ) -> Model:
    #     self.update_stoichiometry(
    #         rate_name=rate_name,
    #         stoichiometry=self.stoichiometries[rate_name] | {compound: value},
    #     )
    #     return self

    # def scale_stoichiometry_of_cpd(
    #     self,
    #     rate_name: str,
    #     compound: str,
    #     scale: float,
    # ) -> Model:
    #     return self.update_stoichiometry_of_cpd(
    #         rate_name=rate_name,
    #         compound=compound,
    #         value=self.stoichiometries[rate_name][compound] * scale,
    #     )

    ##########################################################################
    # Readouts
    # They are like derived variables, but only calculated on demand
    # Think of something like NADPH / (NADP + NADPH) as a proxy for energy state
    ##########################################################################

    def add_readout(self, name: str, fn: RateFn, *, args: list[str]) -> Self:
        """Adds a readout to the model.

        Examples:
            >>> model.add_readout("energy_state",
            ...     fn=div,
            ...     args=["NADPH", "NADP*_total"]
            ... )

        Args:
            name: The name of the readout.
            fn: The function to be used for the readout.
            args: The list of arguments for the function.

        Returns:
            Self: The instance of the model with the added readout.

        """
        self._insert_id(name=name, ctx="readout")
        self._readouts[name] = Readout(fn, args)
        return self

    def get_readout_names(self) -> list[str]:
        """Retrieve the names of all readouts.

        Examples:
            >>> model.get_readout_names()
                ["energy_state", "redox_state"]

        Returns:
            list[str]: A list containing the names of the readouts.

        """
        return list(self._readouts)

    def remove_readout(self, name: str) -> Self:
        """Remove a readout by its name.

        Examples:
            >>> model.remove_readout("energy_state")

        Args:
            name (str): The name of the readout to remove.

        Returns:
            Self: The instance of the class after the readout has been removed.

        """
        self._remove_id(name=name)
        del self._readouts[name]
        return self

    ##########################################################################
    # Surrogates
    ##########################################################################

    @_invalidate_cache
    def add_surrogate(
        self,
        name: str,
        surrogate: AbstractSurrogate,
        args: list[str] | None = None,
        stoichiometries: dict[str, dict[str, float]] | None = None,
    ) -> Self:
        """Adds a surrogate model to the current instance.

        Examples:
            >>> model.add_surrogate("name", surrogate)

        Args:
            name (str): The name of the surrogate model.
            surrogate (AbstractSurrogate): The surrogate model instance to be added.
            args: A list of arguments for the surrogate model.
            stoichiometries: A dictionary mapping reaction names to stoichiometries.

        Returns:
            Self: The current instance with the added surrogate model.

        """
        self._insert_id(name=name, ctx="surrogate")

        if args is not None:
            surrogate.args = args
        if stoichiometries is not None:
            surrogate.stoichiometries = stoichiometries

        self._surrogates[name] = surrogate
        return self

    def update_surrogate(
        self,
        name: str,
        surrogate: AbstractSurrogate | None = None,
        args: list[str] | None = None,
        stoichiometries: dict[str, dict[str, float]] | None = None,
    ) -> Self:
        """Update a surrogate model in the model.

        Examples:
            >>> model.update_surrogate("name", surrogate)

        Args:
            name (str): The name of the surrogate model to update.
            surrogate (AbstractSurrogate): The new surrogate model instance.
            args: A list of arguments for the surrogate model.
            stoichiometries: A dictionary mapping reaction names to stoichiometries.

        Returns:
            Self: The instance of the model with the updated surrogate model.

        """
        if name not in self._surrogates:
            msg = f"Surrogate '{name}' not found in model"
            raise KeyError(msg)

        if surrogate is None:
            surrogate = self._surrogates[name]
        if args is not None:
            surrogate.args = args
        if stoichiometries is not None:
            surrogate.stoichiometries = stoichiometries

        self._surrogates[name] = surrogate
        return self

    def remove_surrogate(self, name: str) -> Self:
        """Remove a surrogate model from the model.

        Examples:
            >>> model.remove_surrogate("name")

        Returns:
            Self: The instance of the model with the specified surrogate model removed.

        """
        self._remove_id(name=name)
        self._surrogates.pop(name)
        return self

    ##########################################################################
    # Get args
    ##########################################################################

    def _get_args(
        self,
        concs: dict[str, float],
        time: float = 0.0,
        *,
        include_readouts: bool,
    ) -> dict[str, float]:
        """Generate a dictionary of arguments for model calculations.

        Examples:
            >>> model._get_args({"x1": 1.0, "x2": 2.0}, time=0.0)
                {"x1": 1.0, "x2": 2.0, "k1": 0.1, "time": 0.0}

        Args:
            concs: A dictionary of concentrations with keys as the names of the substances
                   and values as their respective concentrations.
            time: The time point for the calculation
            include_readouts: A flag indicating whether to include readout values in the returned dictionary.

        Returns:
            dict[str, float]
                A dictionary containing parameter values, derived variables, and optionally readouts,
                with their respective names as keys and their calculated values as values.

        """
        if (cache := self._cache) is None:
            cache = self._create_cache()

        args: dict[str, float] = cache.all_parameter_values | concs
        args["time"] = time

        derived = self._derived
        for name in cache.derived_variable_names:
            dv = derived[name]
            args[name] = cast(float, dv.fn(*(args[arg] for arg in dv.args)))

        if include_readouts:
            for name, ro in self._readouts.items():
                args[name] = cast(float, ro.fn(*(args[arg] for arg in ro.args)))
        return args

    def get_args(
        self,
        concs: dict[str, float] | None = None,
        time: float = 0.0,
        *,
        include_readouts: bool = False,
    ) -> pd.Series:
        """Generate a pandas Series of arguments for the model.

        Examples:
            # Using initial conditions
            >>> model.get_args()
                {"x1": 1.0, "x2": 2.0, "k1": 0.1, "time": 0.0}

            # With custom concentrations
            >>> model.get_args({"x1": 1.0, "x2": 2.0})
                {"x1": 1.0, "x2": 2.0, "k1": 0.1, "time": 0.0}

            # With custom concentrations and time
            >>> model.get_args({"x1": 1.0, "x2": 2.0}, time=1.0)
                {"x1": 1.0, "x2": 2.0, "k1": 0.1, "time": 1.0}

        Args:
            concs: A dictionary where keys are the names of the concentrations and values are their respective float values.
            time: The time point at which the arguments are generated (default is 0.0).
            include_readouts: Whether to include readouts in the arguments (default is False).

        Returns:
            A pandas Series containing the generated arguments with float dtype.

        """
        return pd.Series(
            self._get_args(
                concs=self.get_initial_conditions() if concs is None else concs,
                time=time,
                include_readouts=include_readouts,
            ),
            dtype=float,
        )

    def get_args_time_course(
        self,
        concs: pd.DataFrame,
        *,
        include_readouts: bool = False,
    ) -> pd.DataFrame:
        """Generate a DataFrame containing time course arguments for model evaluation.

        Examples:
            >>> model.get_args_time_course(
            ...     pd.DataFrame({"x1": [1.0, 2.0], "x2": [2.0, 3.0]}
            ... )
                pd.DataFrame({
                    "x1": [1.0, 2.0],
                    "x2": [2.0, 3.0],
                    "k1": [0.1, 0.1],
                    "time": [0.0, 1.0]},
                )

        Args:
            concs: A DataFrame containing concentration data with time as the index.
            include_readouts: If True, include readout variables in the resulting DataFrame.

        Returns:
            A DataFrame containing the combined concentration data, parameter values,
            derived variables, and optionally readout variables, with time as an additional column.

        """
        if (cache := self._cache) is None:
            cache = self._create_cache()

        pars_df = pd.DataFrame(
            np.full(
                (len(concs), len(cache.all_parameter_values)),
                np.fromiter(cache.all_parameter_values.values(), dtype=float),
            ),
            index=concs.index,
            columns=list(cache.all_parameter_values),
        )

        args = pd.concat((concs, pars_df), axis=1)
        args["time"] = args.index

        derived = self._derived
        for name in cache.derived_variable_names:
            dv = derived[name]
            args[name] = dv.fn(*args.loc[:, dv.args].to_numpy().T)

        if include_readouts:
            for name, ro in self._readouts.items():
                args[name] = ro.fn(*args.loc[:, ro.args].to_numpy().T)
        return args

    ##########################################################################
    # Get full concs
    ##########################################################################

    def get_full_concs(
        self,
        concs: dict[str, float] | None = None,
        time: float = 0.0,
        *,
        include_readouts: bool = True,
    ) -> pd.Series:
        """Get the full concentrations as a pandas Series.

        Examples:
            >>> model.get_full_concs({"x1": 1.0, "x2": 2.0}, time=0.0)
                pd.Series({
                    "x1": 1.0,
                    "x2": 2.0,
                    "d1": 3.0,
                    "d2": 4.0,
                    "r1": 0.1,
                    "r2": 0.2,
                    "energy_state": 0.5,
                })

        Args:
            concs (dict[str, float]): A dictionary of concentrations with variable names as keys and their corresponding values as floats.
            time (float, optional): The time point at which to get the concentrations. Default is 0.0.
            include_readouts (bool, optional): Whether to include readout variables in the result. Default is True.

        Returns:
        pd.Series: A pandas Series containing the full concentrations for the specified variables.

        """
        names = self.get_variable_names() + self.get_derived_variable_names()
        if include_readouts:
            names.extend(self.get_readout_names())

        return self.get_args(
            concs=concs,
            time=time,
            include_readouts=include_readouts,
        ).loc[names]

    ##########################################################################
    # Get fluxes
    ##########################################################################

    def _get_fluxes(self, args: dict[str, float]) -> dict[str, float]:
        """Calculate the fluxes for the given arguments.

        Examples:
            >>> model._get_fluxes({"x1": 1.0, "x2": 2.0, "k1": 0.1, "time": 0.0})
                {"r1": 0.1, "r2": 0.2}

        Args:
            args (dict[str, float]): A dictionary where the keys are argument names and the values are their corresponding float values.

        Returns:
            dict[str, float]: A dictionary where the keys are reaction names and the values are the calculated fluxes.

        """
        fluxes: dict[str, float] = {}
        for name, rxn in self._reactions.items():
            fluxes[name] = cast(float, rxn.fn(*(args[arg] for arg in rxn.args)))

        for surrogate in self._surrogates.values():
            fluxes |= surrogate.predict(np.array([args[arg] for arg in surrogate.args]))
        return fluxes

    def get_fluxes(
        self,
        concs: dict[str, float] | None = None,
        time: float = 0.0,
    ) -> pd.Series:
        """Calculate the fluxes for the given concentrations and time.

        Examples:
            # Using initial conditions as default
            >>> model.get_fluxes()
                pd.Series({"r1": 0.1, "r2": 0.2})

            # Using custom concentrations
            >>> model.get_fluxes({"x1": 1.0, "x2": 2.0})
                pd.Series({"r1": 0.1, "r2": 0.2})

            # Using custom concentrations and time
            >>> model.get_fluxes({"x1": 1.0, "x2": 2.0}, time=0.0)
                pd.Series({"r1": 0.1, "r2": 0.2})

        Args:
            concs: A dictionary where keys are species names and values are their concentrations.
            time: The time at which to calculate the fluxes. Defaults to 0.0.

        Returns:
            Fluxes: A pandas Series containing the fluxes for each reaction.

        """
        args = self.get_args(
            concs=concs,
            time=time,
            include_readouts=False,
        )

        fluxes: dict[str, float] = {}
        for name, rxn in self._reactions.items():
            fluxes[name] = cast(float, rxn.fn(*args.loc[rxn.args]))

        for surrogate in self._surrogates.values():
            fluxes |= surrogate.predict(args.loc[surrogate.args].to_numpy())
        return pd.Series(fluxes, dtype=float)

    def get_fluxes_time_course(self, args: pd.DataFrame) -> pd.DataFrame:
        """Generate a time course of fluxes for the given reactions and surrogates.

        Examples:
            >>> model.get_fluxes_time_course(args)
                pd.DataFrame({"v1": [0.1, 0.2], "v2": [0.2, 0.3]})

        This method calculates the fluxes for each reaction in the model using the provided
        arguments and combines them with the outputs from the surrogates to create a complete
        time course of fluxes.

        Args:
            args (pd.DataFrame): A DataFrame containing the input arguments for the reactions
                                 and surrogates. Each column corresponds to a specific input
                                 variable, and each row represents a different time point.

        Returns:
            pd.DataFrame: A DataFrame containing the calculated fluxes for each reaction and
                          the outputs from the surrogates. The index of the DataFrame matches
                          the index of the input arguments.

        """
        fluxes: dict[str, Float] = {}
        for name, rate in self._reactions.items():
            fluxes[name] = rate.fn(*args.loc[:, rate.args].to_numpy().T)

        # Create df here already to avoid having to play around with
        # shape of surrogate outputs
        flux_df = pd.DataFrame(fluxes, index=args.index)
        for surrogate in self._surrogates.values():
            outputs = pd.DataFrame(
                [surrogate.predict(y) for y in args.loc[:, surrogate.args].to_numpy()],
                index=args.index,
            )
            flux_df = pd.concat((flux_df, outputs), axis=1)
        return flux_df

    ##########################################################################
    # Get rhs
    ##########################################################################

    def __call__(self, /, time: float, concs: Array) -> Array:
        """Simulation version of get_right_hand_side.

        Examples:
            >>> model(0.0, np.array([1.0, 2.0]))
                np.array([0.1, 0.2])

        Warning: Swaps t and y!
        This can't get kw-only args, as the integrators call it with pos-only

        Args:
            time: The current time point.
            concs: Array of concentrations


        Returns:
            The rate of change of each variable in the model.

        """
        if (cache := self._cache) is None:
            cache = self._create_cache()
        concsd: dict[str, float] = dict(
            zip(
                cache.var_names,
                concs,
                strict=True,
            )
        )
        args: dict[str, float] = self._get_args(
            concs=concsd,
            time=time,
            include_readouts=False,
        )
        fluxes: dict[str, float] = self._get_fluxes(args)

        dxdt = cache.dxdt
        dxdt[:] = 0
        for k, stoc in cache.stoich_by_cpds.items():
            for flux, n in stoc.items():
                dxdt[k] += n * fluxes[flux]
        for k, sd in cache.dyn_stoich_by_cpds.items():
            for flux, dv in sd.items():
                n = dv.fn(*(args[i] for i in dv.args))
                dxdt[k] += n * fluxes[flux]
        return cast(Array, dxdt.to_numpy())

    def get_right_hand_side(
        self,
        concs: dict[str, float] | None = None,
        time: float = 0.0,
    ) -> pd.Series:
        """Calculate the right-hand side of the differential equations for the model.

        Examples:
            # Using initial conditions as default
            >>> model.get_right_hand_side()
                pd.Series({"x1": 0.1, "x2": 0.2})

            # Using custom concentrations
            >>> model.get_right_hand_side({"x1": 1.0, "x2": 2.0})
                pd.Series({"x1": 0.1, "x2": 0.2})

            # Using custom concentrations and time
            >>> model.get_right_hand_side({"x1": 1.0, "x2": 2.0}, time=0.0)
                pd.Series({"x1": 0.1, "x2": 0.2})

        Args:
            concs: A dictionary mapping compound names to their concentrations.
            time: The current time point. Defaults to 0.0.

        Returns:
            The rate of change of each variable in the model.

        """
        if (cache := self._cache) is None:
            cache = self._create_cache()
        var_names = self.get_variable_names()
        args = self._get_args(
            concs=self.get_initial_conditions() if concs is None else concs,
            time=time,
            include_readouts=False,
        )
        fluxes = self._get_fluxes(args)
        dxdt = pd.Series(np.zeros(len(var_names), dtype=float), index=var_names)
        for k, stoc in cache.stoich_by_cpds.items():
            for flux, n in stoc.items():
                dxdt[k] += n * fluxes[flux]

        for k, sd in cache.dyn_stoich_by_cpds.items():
            for flux, dv in sd.items():
                n = dv.fn(*(args[i] for i in dv.args))
                dxdt[k] += n * fluxes[flux]
        return dxdt

    ##########################################################################
    # Get latex
    ##########################################################################

    @property
    def math_exprs(self) -> dict[str, str]:
        """Returns a copy of the _math_exprs dictionary.

        The _math_exprs dictionary contains key-value pairs where both keys and values are strings.

        Returns:
            dict[str, str]: A copy of the _math_exprs dictionary.

        """
        return self._math_exprs.copy()

    def insert_math_expr(self, *, name: str, math: str) -> None:
        """Inserts a math expression into the model's internal dictionary.

        Args:
            name: The name of the identifier to add a math expression.
            math: The math expression associated to the identifier.

        Raises:
            NameError: If the name does not exist in the model's ID dictionary.

        """
        if name not in self._ids:
            msg = f"Model does not contain {name}"
            raise NameError(msg)

        self._math_exprs[name] = math

    def insert_math_exprs(self, math_exprs: dict[str, str]) -> None:
        """Inserts several math expressions into the model's internal dictionary.

        Args:
            math_exprs: A dictionary of a name and math expression pair

        Raises:
            NameError: If the name does not exist in the model's ID dictionary.

        """
        for name, math_expr in math_exprs.items():
            self.insert_math_expr(name=name, math=math_expr)

    def remove_math_expr(self, *, name: str) -> None:
        """Remove a math expression from the internal dictionary.

        Args:
            name (str): The name of the ID to be removed.

        Raises:
            KeyError: If the specified name does not exist in the dictionary.

        """
        del self._math_exprs[name]

    ##########################################################################
    # Get latex
    ##########################################################################

    def latex_func(
            self,
            func: Callable,
            func_args: Iterable,
            math_expr: dict | None = None,
            *,
            reduce_assignment: bool = True
    ) -> str:
        """Helper function to 'latexify' model function given.

        Args:
            func (Callable): Function to 'latexify'.
            func_args (Iterable): Math arguments to replace arguments of given function.
            math_expr (dict | None, optional): Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to None.
            reduce_assignment (bool, optional): Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True.

        Returns:
            str: Function with replaced values if applicable. Only the right hand side of the function!

        """
        if math_expr is None:
            math_expr = {}
        try:
            ltx = latexify.get_latex(func, reduce_assignments=reduce_assignment)
            if ltx.count(r"\\") > 0:
                for i in [r"\begin{array}{l} ", r" \end{array}"]:
                    ltx = ltx.replace(i, "")
                line_split = ltx.split(r"\\")
            else:
                line_split = [ltx]

            final = line_split[-1]

            for i in line_split[:-1]:
                lhs = i.split(" = ")[0].replace(" ", "")
                rhs = i.split(" = ")[1]
                final = final.replace(lhs, rhs)

            for old, new in zip(
                (
                    r"\mathopen{}",
                    r"\mathclose{}",
                ),
                ("", ""),
                strict=False,
            ):
                final = final.replace(old, new)
            lhs = final.split("=")[0]
            rhs = final.split(" = ")[1]
            func_a_list = lhs[lhs.find("(") + 1 : -2].split(", ")

            for arg_model, arg_ltx in zip(func_args, func_a_list, strict=False):
                if math_expr.get(arg_model) is not None: # Use supplied math expressions
                    arg_model = math_expr[arg_model]  # noqa: PLW2901
                elif arg_model in self._ids:
                    if self._ids[arg_model] == "reaction" and self._reactions[arg_model].math is not None:
                        arg_model = self._reactions[arg_model].math
                    if self._ids[arg_model] == "derived" and self._derived[arg_model].math is not None:
                        arg_model = self._derived[arg_model].math
                # Escape literal characters
                arg_model = arg_model.replace("\\", r"\\") # Cant use re.escape() because some latex characters should not be escaped  # noqa: PLW2901
                arg_ltx = re.escape(arg_ltx)  # noqa: PLW2901
                rhs = re.sub(rf"{arg_ltx}(?=( |$|}}))", arg_model, rhs)
                # rhs = rhs.replace(to_replace, f" {arg_model} ")
        except latexify.exceptions.LatexifyError:
            rhs = f'ERROR because of function "{func.__name__}"'

        return rhs

    def export_as_txt(
            self,
            inp: str,
            txt_path: Path
    ) -> None:
        """Helper function to export changes made to information as a text-file.

        Args:
            inp (str): Input to be compared if changed and inserted into file
            txt_path (Path): Path to txt-file.

        """
        if not Path.is_file(txt_path):
            with Path.open(txt_path, "w") as f:
                f.write(f"------- Start on {datetime.now()} -------\n\n")  # noqa: DTZ005
                f.write(inp)
                print(f'Created "{txt_path.name}"!')  # noqa: T201
                return
        else:
            with Path.open(txt_path) as f_tmp:
                read = f_tmp.read()
            flag_idxs = [m.start() for m in re.finditer("-------", read)]

            try:
                compare_block = read[flag_idxs[1] + 9 : flag_idxs[2]]
            except:  # noqa: E722
                compare_block = read[flag_idxs[1] + 9 :]

            if compare_block == inp:
                print(f'"{txt_path.name}" still up to date!')  # noqa: T201
                return
            with Path.open(txt_path, "r+") as f:
                f.seek(0, 0)
                f.write(f"------- Update on {datetime.now()} -------\n\n" + inp + read)  # noqa: DTZ005
                print(f'Updated "{txt_path.name}"')  # noqa: T201
            return

    def get_latex_single(
            self,
            name: str,
            math_expr: dict | None = None,
            *,
            align: bool = True,
            reduce_assignment: bool = True
    ) -> str:
        """Extract the LaTeX information of the given variable, reaction, or derived.

        Args:
            name (str): Name of variable, reaction, or derived. Has to be in model!
            math_expr (dict | None, optional): Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var and the stored math expression should not be used. Defaults to dict().
            align (bool, optional): Boolean value if the information should be exported with '&=' or '='. Defaults to True.
            reduce_assignment (bool, optional): Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True.

        Returns:
            str: _description_

        """
        if math_expr is None:
            math_expr = {}
        math_expr = self._math_exprs | math_expr
        if self._ids[name] == "derived":
            var = self._derived[name]

            if math_expr.get(name) is not None:
                lhs = math_expr[name]
            elif var.math is not None:
                lhs = var.math
            else:
                lhs = name

            rhs = self.latex_func(
                func=var.fn,
                func_args=var.args,
                math_expr=math_expr
            )
        elif self._ids[name] == "reaction":
            var = self._reactions[name] # type: ignore

            if math_expr.get(name) is not None:
                lhs = math_expr[name]
            elif var.math is not None:
                lhs = var.math
            else:
                lhs = name

            rhs = self.latex_func(
                func=var.fn,
                func_args=var.args,
                math_expr=math_expr
            )
        elif self._ids[name] == "variable":
            comp = math_expr[name] if math_expr.get(name) is not None else name

            lhs = rf"\frac{{\mathrm{{d}}{comp}}}{{\mathrm{{d}}t}}"
            stoics = self.get_stoichiometries().T[name]
            clean_stoics = stoics[stoics != 0.0]

            rhs = ""

            for rate in clean_stoics.index:
                stoic = self._reactions[rate].stoichiometry[name]
                rate = self._reactions[rate].math if self._reactions[rate].math is not None else rate
                bridge = r" \cdot "
                if isinstance(stoic, Derived):
                    stoic = self.latex_func(stoic.fn, stoic.args, math_expr, reduce_assignment=reduce_assignment) # type: ignore
                elif abs(stoic) == 1:
                    stoic = str(stoic).replace("1", "") # type: ignore
                    bridge = "" if rhs == "" else " "
                else:
                    stoic = str(stoic) # type: ignore

                if rhs != "" and (stoic == "" or stoic[0] != "-"): # type: ignore
                    stoic = f"+{stoic}" # type: ignore

                rhs += rf"{stoic}{bridge}{rate} "

            rhs = rhs[:-1]
        else:
            print(f'"{name}" is not a reaction or derived. It is a "{self._ids[name]}"')  # noqa: T201

        if align:
            return f"{lhs} &= {rhs}" # type: ignore
        else:
            return f"{lhs} = {rhs}" # type: ignore



    def get_latex_reactions(
            self,
            math_expr: dict | None = None,
            txt_path: Path | None = None,
            *,
            align: bool = True,
            reduce_assignment: bool = True
    ) -> str | None:
        """Extract the LaTeX information of all reactions of the model as a txt-file or a str.

        Args:
            math_expr (dict | None, optional): Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict().
            txt_path (Path | None, optional): Path to txt-file.. Defaults to None.
            align (bool, optional): Boolean value if the information should be exported with '&=' or '='. Defaults to True.
            reduce_assignment (bool, optional): Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True.

        Returns:
            str | None: Depending if txt_path is given, export LaTeX information of all reactions of the model to a txt-file or a str

        """
        res = ""

        for reac in self._reactions:
            res += self.get_latex_single(reac, math_expr, align=align, reduce_assignment=reduce_assignment)
            res += r" \\"
            res += " \n"

        res = res[:-2]

        if txt_path is None:
            return res
        txt_path = txt_path.with_suffix(".txt")
        self.export_as_txt(res, txt_path)
        return None


    def get_latex_odes(
            self,
            math_expr: dict | None = None,
            txt_path: Path | None = None,
            *,
            align: bool = True,
            reduce_assignment: bool = True
    ) -> str | None:
        """Extract the LaTeX information of the ODE system of the model as a txt-file or a str.

        Args:
            math_expr (dict | None, optional): Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict().
            txt_path (Path | None, optional): Path to txt-file.. Defaults to None.
            align (bool, optional): Boolean value if the information should be exported with '&=' or '='. Defaults to True.
            reduce_assignment (bool, optional): Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True.

        Returns:
            str | None: Depending if txt_path is given, export LaTeX information of the ODE system of the model to a txt-file or a str

        """
        res = ""

        for variable in self._variables:
            res += self.get_latex_single(variable, math_expr, align=align,reduce_assignment=reduce_assignment)
            res += r" \\"
            res += " \n"

        res = res[:-2]

        if txt_path is None:
            return res
        txt_path = txt_path.with_suffix(".txt")
        self.export_as_txt(res, txt_path)
        return None

    def get_latex_derived(
            self,
            math_expr: dict | None = None,
            txt_path: Path | None = None,
            *,
            align: bool = True,
            reduce_assignment: bool = True
    ) -> str | None:
        """Extract the LaTeX information of all derived of the model as a txt-file or a str.

        Args:
            math_expr (dict | None, optional): Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict().
            txt_path (Path | None, optional): Path to txt-file.. Defaults to None.
            align (bool, optional): Boolean value if the information should be exported with '&=' or '='. Defaults to True.
            reduce_assignment (bool, optional): Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True.

        Returns:
            str | None: Depending if txt_path is given, export LaTeX information of all derived of the model to a txt-file or a str

        """
        res = ""

        for derived in self._derived:
            res += self.get_latex_single(derived, math_expr, align=align, reduce_assignment=reduce_assignment)
            res += r" \\"
            res += " \n"

        res = res[:-2]

        if txt_path is None:
            return res
        txt_path = txt_path.with_suffix(".txt")
        self.export_as_txt(res, txt_path)
        return None

    def get_latex_custom(
            self,
            names: list[str],
            math_expr: dict | None = None,
            txt_path: Path | None = None,
            *,
            align: bool = True,
            reduce_assignment: bool = True
    ) -> str | None:
        """Extract the LaTeX information of a custom list of information from the model as a txt-file or a str.

        Args:
            names (list[str]): List of infromation to be extracted from the model.
            math_expr (dict | None, optional): Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict().
            txt_path (Path | None, optional): Path to txt-file.. Defaults to None.
            align (bool, optional): Boolean value if the information should be exported with '&=' or '='. Defaults to True.
            reduce_assignment (bool, optional): Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True.

        Returns:
            str | None: Depending if txt_path is given, export LaTeX information of a custom list of information from the model to a txt-file or a str

        """
        res = ""

        for var in names:
            res += self.get_latex_single(var, math_expr, align=align, reduce_assignment=reduce_assignment)
            res += r" \\"
            res += " \n"

        res = res[:-2]

        if txt_path is None:
            return res
        txt_path = txt_path.with_suffix(".txt")
        self.export_as_txt(res, txt_path)
        return None

    def get_latex_all(
            self,
            math_expr: dict | None = None,
            txt_path: Path | None = None,
            *,
            align: bool = True,
            reduce_assignment: bool = True,
            combine: bool = False
    ) -> str | None | tuple[str | None, str | None, str | None]:
        """Extract the LaTeX information of all reactions, ODEs, and derived from the model as a txt-file or a str.

        Args:
            math_expr (dict | None, optional): Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict().
            txt_path (Path | None, optional): Path to txt-file.. Defaults to None.
            align (bool, optional): Boolean value if the information should be exported with '&=' or '='. Defaults to True.
            reduce_assignment (bool, optional): Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True.
            combine (bool, optional): Boolean value if the exported infromation should be combined inside one txt-file. Defaults to False.

        Returns:
            str | None: Depending if txt_path is given, export LaTeX information of all reactions, ODEs, and derived from the model to a txt-file or a str

        """
        odes = self.get_latex_odes(math_expr, align=align, reduce_assignment=reduce_assignment)
        reacs = self.get_latex_reactions(math_expr, align=align, reduce_assignment=reduce_assignment)
        derived = self.get_latex_derived(math_expr, align=align, reduce_assignment=reduce_assignment)
        if txt_path is None:
            if combine:
                return f"{odes}\n\n{reacs}\n\n{derived}"
            return odes, reacs, derived
        if combine:
            inp = "ODE System:\n"
            inp += odes # type: ignore
            inp += "\n\n"
            inp += "Reactions:\n"
            inp += reacs # type: ignore
            inp += "\n\n"
            inp += "Derived:\n"
            inp += derived # type: ignore

            txt_path = txt_path.with_suffix(".txt")
            self.export_as_txt(inp, txt_path)
            return None
        self.get_latex_odes(math_expr, txt_path.with_stem(txt_path.stem + "_ODEs"), align=align, reduce_assignment=reduce_assignment)
        self.get_latex_reactions(math_expr, txt_path.with_stem(txt_path.stem + "_reactions"), align=align, reduce_assignment=reduce_assignment)
        self.get_latex_derived(math_expr, txt_path.with_stem(txt_path.stem + "_derived"), align=align, reduce_assignment=reduce_assignment)
        return None

