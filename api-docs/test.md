<!-- markdownlint-disable -->

# modelbase2-latexify

This addon to the package is there to automatically extract infromation from a model and export it in a LaTeX format. This fascilitates the publishing of the model, as a pseudo-bridge is created between the Python-code and the Latex formatting

## Actual functions

### <kbd>method</kbd> `get_latex_single`

```python
get_latex_single(
    name: 'str',
    math_expr: 'dict | None' = None,
    align: 'bool' = True,
    reduce_assignment: 'bool' = True
) → str
```

Extract the LaTeX information of the given variable, reaction, or derived. 



**Args:**
 
 - <b>`name`</b> (str):  Name of variable, reaction, or derived. Has to be in model! 
 - <b>`math_expr`</b> (dict | None, optional):  Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict(). 
 - <b>`align`</b> (bool, optional):  Boolean value if the information should be exported with '&=' or '='. Defaults to True. 
 - <b>`reduce_assignment`</b> (bool, optional):  Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True. 



**Returns:**
 
 - <b>`str`</b>:  _description_ 

### <kbd>method</kbd> `get_latex_reactions`

```python
get_latex_reactions(
    math_expr: 'dict | None' = None,
    txt_path: 'Path | None' = None,
    align: 'bool' = True,
    reduce_assignment: 'bool' = True
) → str | None
```

Extract the LaTeX information of all reactions of the model as a txt-file or a str. 



**Args:**
 
 - <b>`math_expr`</b> (dict | None, optional):  Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict(). 
 - <b>`txt_path`</b> (Path | None, optional):  Path to txt-file.. Defaults to None. 
 - <b>`align`</b> (bool, optional):  Boolean value if the information should be exported with '&=' or '='. Defaults to True. 
 - <b>`reduce_assignment`</b> (bool, optional):  Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True. 



**Returns:**
 
 - <b>`str | None`</b>:  Depending if txt_path is given, export LaTeX information of all reactions of the model to a txt-file or a str 

### <kbd>method</kbd> `get_latex_odes`

```python
get_latex_odes(
    math_expr: 'dict | None' = None,
    txt_path: 'Path | None' = None,
    align: 'bool' = True,
    reduce_assignment: 'bool' = True
) → str | None
```

Extract the LaTeX information of the ODE system of the model as a txt-file or a str. 



**Args:**
 
 - <b>`math_expr`</b> (dict | None, optional):  Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict(). 
 - <b>`txt_path`</b> (Path | None, optional):  Path to txt-file.. Defaults to None. 
 - <b>`align`</b> (bool, optional):  Boolean value if the information should be exported with '&=' or '='. Defaults to True. 
 - <b>`reduce_assignment`</b> (bool, optional):  Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True. 



**Returns:**
 
 - <b>`str | None`</b>:  Depending if txt_path is given, export LaTeX information of the ODE system of the model to a txt-file or a str 

### <kbd>method</kbd> `get_latex_derived`

```python
get_latex_derived(
    math_expr: 'dict | None' = None,
    txt_path: 'Path | None' = None,
    align: 'bool' = True,
    reduce_assignment: 'bool' = True
) → str | None
```

Extract the LaTeX information of all derived of the model as a txt-file or a str. 



**Args:**
 
 - <b>`math_expr`</b> (dict | None, optional):  Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict(). 
 - <b>`txt_path`</b> (Path | None, optional):  Path to txt-file.. Defaults to None. 
 - <b>`align`</b> (bool, optional):  Boolean value if the information should be exported with '&=' or '='. Defaults to True. 
 - <b>`reduce_assignment`</b> (bool, optional):  Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True. 



**Returns:**
 
 - <b>`str | None`</b>:  Depending if txt_path is given, export LaTeX information of all derived of the model to a txt-file or a str 

### <kbd>method</kbd> `get_latex_custom`

```python
get_latex_custom(
    names: 'list[str]',
    math_expr: 'dict | None' = None,
    txt_path: 'Path | None' = None,
    align: 'bool' = True,
    reduce_assignment: 'bool' = True
) → str | None
```

Extract the LaTeX information of a custom list of information from the model as a txt-file or a str. 



**Args:**
 
 - <b>`names`</b> (list[str]):  List of infromation to be extracted from the model. 
 - <b>`math_expr`</b> (dict | None, optional):  Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict(). 
 - <b>`txt_path`</b> (Path | None, optional):  Path to txt-file.. Defaults to None. 
 - <b>`align`</b> (bool, optional):  Boolean value if the information should be exported with '&=' or '='. Defaults to True. 
 - <b>`reduce_assignment`</b> (bool, optional):  Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True. 



**Returns:**
 
 - <b>`str | None`</b>:  Depending if txt_path is given, export LaTeX information of a custom list of information from the model to a txt-file or a str 

### <kbd>method</kbd> `get_latex_all`

```python
get_latex_all(
    math_expr: 'dict | None' = None,
    txt_path: 'Path | None' = None,
    align: 'bool' = True,
    reduce_assignment: 'bool' = True,
    combine: 'bool' = False
) → str | None | tuple[str | None, str | None, str | None]
```

Extract the LaTeX information of all reactions, ODEs, and derived from the model as a txt-file or a str. 



**Args:**
 
 - <b>`math_expr`</b> (dict | None, optional):  Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to dict(). 
 - <b>`txt_path`</b> (Path | None, optional):  Path to txt-file.. Defaults to None. 
 - <b>`align`</b> (bool, optional):  Boolean value if the information should be exported with '&=' or '='. Defaults to True. 
 - <b>`reduce_assignment`</b> (bool, optional):  Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True. 
 - <b>`combine`</b> (bool, optional):  Boolean value if the exported infromation should be combined inside one txt-file. Defaults to False. 



**Returns:**
 
 - <b>`str | None`</b>:  Depending if txt_path is given, export LaTeX information of all reactions, ODEs, and derived from the model to a txt-file or a str 
## Helper Functions
### <kbd>method</kbd> `latex_func`

```python
latex_func(
    func: 'Callable',
    func_args: 'Iterable',
    math_expr: 'dict | None' = None,
    reduce_assignment: 'bool' = True
) → str
```

Helper function to 'latexify' model function given. 



**Args:**
 
 - <b>`func`</b> (Callable):  Function to 'latexify'. 
 - <b>`func_args`</b> (Iterable):  Math arguments to replace arguments of given function. 
 - <b>`math_expr`</b> (dict | None, optional):  Dictionary of names in model (keys) and attributed LaTeX conversion (values) if the given python var should not be used. Defaults to None. 
 - <b>`reduce_assignment`</b> (bool, optional):  Boolean value if the assingments inside the function should be reduced. Check latexify_py docs for more info. Defaults to True. 



**Returns:**
 
 - <b>`str`</b>:  Function with replaced values if applicable. Only the right hand side of the function! 

### <kbd>method</kbd> `export_as_txt`

```python
export_as_txt(inp: 'str', txt_path: 'Path') → None
```

Helper function to export changes made to information as a text-file. 



**Args:**
 
 - <b>`inp`</b> (str):  Input to be compared if changed and inserted into file 
 - <b>`txt_path`</b> (Path):  Path to txt-file. 
