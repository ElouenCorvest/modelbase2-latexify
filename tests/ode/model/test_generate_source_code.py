# type: ignore

from __future__ import annotations

import pytest
from modelbase.ode import Model


def module(x, y):
    return [x / y]


def rate(s, z, k_fwd):
    return k_fwd * s / z


def generate_model():
    model = Model()
    model.add_parameters({"k1": 1, "p1": 1}, meta_info={"k1": {"unit": "mM"}})
    model.add_compounds(
        compounds=("x", "y", "z"), meta_info={"x": {"common_name": "cpd1"}}
    )
    model.add_algebraic_module(
        module_name="mod1",
        function=module,
        compounds=["x", "y"],
        derived_compounds=["A1"],
        modifiers=["z"],
        parameters=["p1"],
        **{"common_name": "a module"},
    )
    model.add_algebraic_module(
        module_name="mod2",
        function=module,
        compounds=["x", "y"],
        derived_compounds=["A2"],
        modifiers=["z"],
        parameters=["p1"],
    )
    model.add_rate(
        rate_name="v1",
        function=rate,
        substrates=["x"],
        products=["y"],
        modifiers=["z"],
        parameters=["k1"],
        **{"common_name": "a rate"},
    )
    model.add_rate(
        rate_name="v2",
        function=rate,
        substrates=["x"],
        products=["y"],
        modifiers=["z"],
        parameters=["k1"],
    )
    model.add_stoichiometry(rate_name="v1", stoichiometry={"x": -1, "y": 1})
    return model


def test_not_linted_no_meta_info(multiline_comparison):
    model = generate_model()
    multiline_comparison(
        [
            "import math",
            "import numpy as np",
            "from modelbase.ode import Model, Simulator",
            "def module(x, y):",
            "    return [x / y]",
            "def rate(s, z, k_fwd):",
            "    return k_fwd * s / z",
            "m = Model()",
            "m.add_parameters(parameters={'k1': 1, 'p1': 1})",
            "m.add_compounds(compounds=['x', 'y', 'z'])",
            "m.add_algebraic_module(",
            "    module_name='mod1',",
            "    function=module,",
            "    compounds=['x', 'y'],",
            "    derived_compounds=['A1'],",
            "    modifiers=['z'],",
            "    parameters=['p1'],",
            "    args=['x', 'y', 'z', 'p1'],",
            ")",
            "m.add_algebraic_module(",
            "    module_name='mod2',",
            "    function=module,",
            "    compounds=['x', 'y'],",
            "    derived_compounds=['A2'],",
            "    modifiers=['z'],",
            "    parameters=['p1'],",
            "    args=['x', 'y', 'z', 'p1'],",
            ")",
            "m.add_rate(",
            "    rate_name='v1',",
            "    function=rate,",
            "    substrates=['x'],",
            "    products=['y'],",
            "    modifiers=['z'],",
            "    parameters=['k1'],",
            "    reversible=False,",
            "    args=['x', 'z', 'k1'],",
            ")",
            "m.add_rate(",
            "    rate_name='v2',",
            "    function=rate,",
            "    substrates=['x'],",
            "    products=['y'],",
            "    modifiers=['z'],",
            "    parameters=['k1'],",
            "    reversible=False,",
            "    args=['x', 'z', 'k1'],",
            ")",
            "m.add_stoichiometries(rate_stoichiometries={'v1': {'x': -1, 'y': 1}})",
        ],
        model.generate_model_source_code(linted=False, include_meta_info=False).strip(),
    )


def test_not_linted_with_meta_info(multiline_comparison):
    model = generate_model()
    multiline_comparison(
        [
            "import math",
            "import numpy as np",
            "from modelbase.ode import Model, Simulator",
            "def module(x, y):",
            "    return [x / y]",
            "def rate(s, z, k_fwd):",
            "    return k_fwd * s / z",
            "m = Model()",
            "m.add_parameters(parameters={'k1': 1, 'p1': 1}, meta_info={'k1': {'unit': 'mM'}})",
            "m.add_compounds(compounds=['x', 'y', 'z'], meta_info={'x': {'common_name': 'cpd1', 'compartment': 'c'}, 'y': {'compartment': 'c'}, 'z': {'compartment': 'c'}})",
            "m.add_algebraic_module(",
            "    module_name='mod1',",
            "    function=module,",
            "    compounds=['x', 'y'],",
            "    derived_compounds=['A1'],",
            "    modifiers=['z'],",
            "    parameters=['p1'],",
            "    args=['x', 'y', 'z', 'p1'],",
            "**{'common_name': 'a module'})",
            "m.add_algebraic_module(",
            "    module_name='mod2',",
            "    function=module,",
            "    compounds=['x', 'y'],",
            "    derived_compounds=['A2'],",
            "    modifiers=['z'],",
            "    parameters=['p1'],",
            "    args=['x', 'y', 'z', 'p1'],",
            ")",
            "m.add_rate(",
            "    rate_name='v1',",
            "    function=rate,",
            "    substrates=['x'],",
            "    products=['y'],",
            "    modifiers=['z'],",
            "    parameters=['k1'],",
            "    reversible=False,",
            "    args=['x', 'z', 'k1'],",
            "    **{'common_name': 'a rate'}",
            ")",
            "m.add_rate(",
            "    rate_name='v2',",
            "    function=rate,",
            "    substrates=['x'],",
            "    products=['y'],",
            "    modifiers=['z'],",
            "    parameters=['k1'],",
            "    reversible=False,",
            "    args=['x', 'z', 'k1'],",
            ")",
            "m.add_stoichiometries(rate_stoichiometries={'v1': {'x': -1, 'y': 1}})",
        ],
        model.generate_model_source_code(linted=False, include_meta_info=True).strip(),
    )


def test_linted_no_meta_info(multiline_comparison):
    model = generate_model()
    multiline_comparison(
        [
            "import math",
            "import numpy as np",
            "from modelbase.ode import Model, Simulator",
            "",
            "",
            "def module(x, y):",
            "    return [x / y]",
            "",
            "",
            "def rate(s, z, k_fwd):",
            "    return k_fwd * s / z",
            "",
            "",
            "m = Model()",
            'm.add_parameters(parameters={"k1": 1, "p1": 1})',
            'm.add_compounds(compounds=["x", "y", "z"])',
            "m.add_algebraic_module(",
            '    module_name="mod1",',
            "    function=module,",
            '    compounds=["x", "y"],',
            '    derived_compounds=["A1"],',
            '    modifiers=["z"],',
            '    parameters=["p1"],',
            '    args=["x", "y", "z", "p1"],',
            ")",
            "m.add_algebraic_module(",
            '    module_name="mod2",',
            "    function=module,",
            '    compounds=["x", "y"],',
            '    derived_compounds=["A2"],',
            '    modifiers=["z"],',
            '    parameters=["p1"],',
            '    args=["x", "y", "z", "p1"],',
            ")",
            "m.add_rate(",
            '    rate_name="v1",',
            "    function=rate,",
            '    substrates=["x"],',
            '    products=["y"],',
            '    modifiers=["z"],',
            '    parameters=["k1"],',
            "    reversible=False,",
            '    args=["x", "z", "k1"],',
            ")",
            "m.add_rate(",
            '    rate_name="v2",',
            "    function=rate,",
            '    substrates=["x"],',
            '    products=["y"],',
            '    modifiers=["z"],',
            '    parameters=["k1"],',
            "    reversible=False,",
            '    args=["x", "z", "k1"],',
            ")",
            'm.add_stoichiometries(rate_stoichiometries={"v1": {"x": -1, "y": 1}})',
        ],
        model.generate_model_source_code(linted=True, include_meta_info=False).strip(),
    )


def test_linted_with_meta_info(multiline_comparison):
    model = generate_model()
    multiline_comparison(
        [
            "import math",
            "import numpy as np",
            "from modelbase.ode import Model, Simulator",
            "",
            "",
            "def module(x, y):",
            "    return [x / y]",
            "",
            "",
            "def rate(s, z, k_fwd):",
            "    return k_fwd * s / z",
            "",
            "",
            "m = Model()",
            'm.add_parameters(parameters={"k1": 1, "p1": 1}, meta_info={"k1": {"unit": "mM"}})',
            "m.add_compounds(",
            '    compounds=["x", "y", "z"],',
            "    meta_info={",
            '        "x": {"common_name": "cpd1", "compartment": "c"},',
            '        "y": {"compartment": "c"},',
            '        "z": {"compartment": "c"},',
            "    },",
            ")",
            "m.add_algebraic_module(",
            '    module_name="mod1",',
            "    function=module,",
            '    compounds=["x", "y"],',
            '    derived_compounds=["A1"],',
            '    modifiers=["z"],',
            '    parameters=["p1"],',
            '    args=["x", "y", "z", "p1"],',
            '    **{"common_name": "a module"},',
            ")",
            "m.add_algebraic_module(",
            '    module_name="mod2",',
            "    function=module,",
            '    compounds=["x", "y"],',
            '    derived_compounds=["A2"],',
            '    modifiers=["z"],',
            '    parameters=["p1"],',
            '    args=["x", "y", "z", "p1"],',
            ")",
            "m.add_rate(",
            '    rate_name="v1",',
            "    function=rate,",
            '    substrates=["x"],',
            '    products=["y"],',
            '    modifiers=["z"],',
            '    parameters=["k1"],',
            "    reversible=False,",
            '    args=["x", "z", "k1"],',
            '    **{"common_name": "a rate"},',
            ")",
            "m.add_rate(",
            '    rate_name="v2",',
            "    function=rate,",
            '    substrates=["x"],',
            '    products=["y"],',
            '    modifiers=["z"],',
            '    parameters=["k1"],',
            "    reversible=False,",
            '    args=["x", "z", "k1"],',
            ")",
            'm.add_stoichiometries(rate_stoichiometries={"v1": {"x": -1, "y": 1}})',
        ],
        model.generate_model_source_code(linted=True, include_meta_info=True).strip(),
    )
