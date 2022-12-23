#!/usr/bin/env python3

import ast
import codecs
import os
import pkgutil
import sys
from typing import Tuple

import chardet


ENCODING = ""


def get_encoding(module_path):  # type: (str) -> str
    """
    First tries to detect the encoding for the file,
    otherwise, returns global encoding default
    """
    try:
        res = chardet.detect(module_path)
        return res["encoding"]
    except TypeError:
        pass

    global ENCODING
    if not ENCODING:
        try:
            ENCODING = codecs.lookup("utf-8-sig").name
        except LookupError:
            ENCODING = codecs.lookup("utf-8").name
    return ENCODING


def visit_ast(
    source_text,  # type: str
    avoid_check_funcs,  # type: bool
    module_path,  # type: str
    module_name="",  # type: str
    debug_mode=False,  # type: bool
):  # type: (...) -> str
    parsed_ast = ast.parse(source_text, module_path)

    try:
        from ddtrace.appsec.iast.ast.visitor import AstVisitor

        visitor = AstVisitor(
            avoid_check_funcs,
            filename=module_path,
            module_name=module_name,
        )
        modified_ast = visitor.visit(parsed_ast)

        if not visitor.ast_modified:
            return ""

    except Exception:
        raise

    return modified_ast


def astpatch_source(
    module_path="",  # type: str
    module_name="",  # type: str
    avoid_check_funcs=False,  # type: bool
):  # type: (...) -> Tuple[str, str]

    if not module_path and not module_name:
        raise Exception("Implementation Error: You must pass module_name and, optionally, module_path")

    if not module_path:
        # Get the module path from the module name (foo.bar -> foo/bar.py)
        loader = pkgutil.get_loader(module_name)

        assert loader
        # Python 3 loaders
        if hasattr(loader, "path"):
            module_path = loader.path
        # Python 2 loaders
        elif hasattr(loader, "filename"):
            module_path = loader.filename
            # Fix for the case where a __init__.py should be loaded
            if not module_path.endswith((".py", ".pyc")):
                module_path__init = module_path + "/__init__.py"
                if os.path.isfile(module_path__init):
                    module_path = module_path__init

        elif hasattr(loader, "_loader") and hasattr(loader._loader, "path"):
            # urlib.parse enter in this condition.
            module_path = loader._loader.path
        else:
            # Enter in this else if the loader is instance of BuiltinImporter but
            # isinstance(loader, BuiltinImporter) doesn't work
            return "", ""

    if not module_path:
        return "", ""

    # Get the file extension, if it's dll, os, pyd, dyn, dynlib: return
    # If its pyc or pyo, change to .py and check that the file exists. If not,
    # return with warning.
    _, module_ext = os.path.splitext(module_path)

    if module_ext not in {".pyo", ".pyc", ".pyw", ".py"}:
        # Probably native or built-in module
        return "", ""

    if sys.version_info[0] >= 3:
        with open(module_path, "r", encoding=get_encoding(module_path)) as source_file:
            try:
                source_text = source_file.read()
            except UnicodeDecodeError:
                return "", ""
    else:
        with open(module_path, "rb") as source_file:
            try:
                source_text = source_file.read().encode(get_encoding(module_path))
            except UnicodeDecodeError:
                return "", ""

    if os.stat(module_path).st_size == 0:
        # Don't patch empty files like __init__.py
        return "", ""

    if len(source_text.strip()) == 0:
        # Don't patch empty files like __init__.py
        return "", ""

    new_source = visit_ast(
        source_text,
        avoid_check_funcs,
        module_path,
        module_name=module_name,
    )
    if not new_source:
        return "", ""

    return module_path, new_source
