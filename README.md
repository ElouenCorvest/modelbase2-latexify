# modelbase

## modelbase2-latexify

This fork adds several new methods to the `Model` class. These `methods` enables the "automatic" conversion of the model infromation into a LaTeX format. The ODE system, the reactions, and the derived components of the model can easily be extracted into a string, or a seperate txt-file to further transfer to a LaTeX generator. With this addition, I hope to fascilitate the publishing and sharing of each model created by modelbase, as a pseudo-bridge is created between the actual model code and the text summary of it. With adding these methods into your pipeline, you should in theory make the conversion from Python to LaTeX much quicker and eliminate many "copying" issues that may come by doing it manually.

### Summary

The entie docs of each added new method is to be found in the file [`latexify.md`](/docs/latexify.md). This doc file has been created using the package [`lazydocs`](https://github.com/ml-tooling/lazydocs) and the corresponding running script can be found [here](api-docs/gen.py).

Additionally an example file has been created to showcase the methods in action, and provide proof to the potential of these new features. These examples can be found in [`latexify.ipynb`](docs/latexify.ipynb).

## Installation

You can install modelbase using pip: `pip install modelbase2`

If you want access to the sundials solver suite via the [assimulo](https://jmodelica.org/assimulo/) package, we recommend setting up a virtual environment via [pixi](https://pixi.sh/) or [mamba / conda](https://mamba.readthedocs.io/en/latest/) using the [conda-forge](https://conda-forge.org/) channel.

```bash
pixi init
pixi add python assimulo
pixi add --pypi modelbase2
```


## Development setup

You have two choices here, using `uv` (pypi-only) or using `pixi` (conda-forge, including assimulo)

### uv

- Install `uv` as described in [the docs](https://docs.astral.sh/uv/getting-started/installation/).
- Run `uv sync --extra dev --extra torch` to install dependencies locally

### pixi

- Install `pixi` as described in [the docs](https://pixi.sh/latest/#installation)
- Run `pixi install --frozen`


## Notes

- `uv add $package`
- `uv add --optional dev $package`
