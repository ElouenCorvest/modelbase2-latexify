from pathlib import Path

from lazydocs import MarkdownGenerator
from lazydocs.generation import to_md_file

from modelbase2 import Model

generator = MarkdownGenerator()


docs = """
# modelbase2-latexify

This addon to the package is there to automatically extract infromation from a model and export it in a LaTeX format. This fascilitates the publishing of the model, as a pseudo-bridge is created between the Python-code and the Latex formatting

## Added methods to the `Model` class
"""

for i in [
    Model.get_latex_single,
    Model.get_latex_reactions,
    Model.get_latex_odes,
    Model.get_latex_derived,
    Model.get_latex_custom,
    Model.get_latex_all
]:
    docs += generator.func2md(i)

docs += """
## Added support of `math` argument

The `Reaction` and `Derived` class already support the argument `math`. This addon assumes this argument to be a LaTeX conversion of the appropriate identifier. Therefore support was added to the `add_` and `update_` methods of both classes.
"""

docs += """
## Added `property` to the `Model` class

This addon adds a new `property` to the `Model` class that stores explicity given LaTeX math expressions paired to the appropriate ids in the model. This is especially useful for Variables and Parameters, but can also be used to overwrite `Reaction` and `Derived` math expressions.

This addon would be even easier to use, if the math expressions could be directly supplied when adding the Variables and Parameters to the model. However, how modelbase2 is constructed right would mean to change a lot of things to support this idea. Which is why, it is not included at this instant.

### <kbd>property</kbd> `math_exprs`

```python
math_exprs() → dict[str, str]
```

Returns a copy of the _math_exprs dictionary.
The _math_exprs dictionary contains key-value pairs where both keys and values are strings.



**Returns:**
 
 - <b>`dict[str, str]`</b>:  A copy of the _math_exprs dictionary.

"""

for i in [
    # Model.math_exprs,
    Model.insert_math_expr,
    Model.insert_math_exprs,
    Model.remove_math_expr
]:
    docs += generator.func2md(i)

docs += '## Helper Functions'

for i in [
    Model.latex_func,
    Model.export_as_txt
]:
    docs += generator.func2md(i)

to_md_file(
    docs,
    str(Path(__file__).parents[1] / 'docs/latexify.md'),
    watermark=False
)
