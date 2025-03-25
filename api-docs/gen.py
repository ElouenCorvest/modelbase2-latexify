from pathlib import Path

from lazydocs import MarkdownGenerator
from lazydocs.generation import to_md_file

from modelbase2 import Model

generator = MarkdownGenerator()


docs = """
# modelbase2-latexify

This addon to the package is there to automatically extract infromation from a model and export it in a LaTeX format. This fascilitates the publishing of the model, as a pseudo-bridge is created between the Python-code and the Latex formatting

## Actual functions
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
