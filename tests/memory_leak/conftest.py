import os
import sys

import pytest

from tests.utils import call_program


try:
    from xml.etree import cElementTree as ElementTree
except ImportError:
    from xml.etree import ElementTree


def _parse_valgrind_xml_errors(path):
    doc = ElementTree.parse(str(path))
    errors = []

    def _elm_to_dict(elm):
        if elm.tag == "stack":
            return [_elm_to_dict(c) for c in elm]

        data = {c.tag: _elm_to_dict(c) for c in elm}
        if not data:
            return elm.text.strip()
        return data

    for error in doc.findall("error"):
        errors.append(_elm_to_dict(error))

    return errors


def _format_valgrind_errors(errors):
    out = ""
    for error in errors:
        out += "What:\n\t{0}\nStack:\n".format(error["xwhat"]["text"])
        for frame in error["stack"]:
            line = ""
            if "dir" in frame:
                line += frame["dir"]
            if "file" in frame:
                if line:
                    line += "."
                line += frame["file"]
            if "line" in frame:
                line += "({})".format(frame["line"])
            if "fn" in frame:
                if line:
                    line += ": "
                line += frame["fn"]
            if line:
                line = "\t{}\n".format(line)
            out += line
    return out


@pytest.fixture
def run_memory_leak_test(tmpdir):
    def _run(code, **kwargs):
        pyfile = tmpdir.join("test.py")
        pyfile.write(code)

        xml = tmpdir.join("valgrind.xml")

        env = os.environ.copy()
        env.update(
            {
                "PYTHONMALLOC": "malloc",
            }
        )

        if "env" in kwargs:
            env.update(kwargs["env"])
        kwargs["env"] = env

        out, err, status, pid = call_program(
            "valgrind",
            "--trace-children=yes",
            "--leak-check=full",
            "--show-leak-kinds=definite",
            "--xml=yes",
            "--xml-file={}".format(xml),
            sys.executable,
            str(pyfile),
            **kwargs
        )
        assert status == 0, err

        errors = _parse_valgrind_xml_errors(xml)
        assert len(errors) == 0
        # , _format_valgrind_errors(errors)

    yield _run
