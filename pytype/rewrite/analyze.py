"""Check and infer types."""

import dataclasses
import logging
from typing import Optional

from pytype import config
from pytype import errors
from pytype import load_pytd
from pytype.blocks import blocks
from pytype.pyc import pyc
from pytype.pytd import pytd
from pytype.rewrite import vm

# How deep to follow call chains:
_INIT_MAXIMUM_DEPTH = 4  # during module loading
_MAXIMUM_DEPTH = 3  # during analysis of function bodies

log = logging.getLogger(__name__)


class Context:
  """Analysis context."""

  def __init__(self):
    # TODO(b/241479600): This is a placeholder to make everything compile and
    # run for now, but we'll need to write a new version of errors.py.
    self.errorlog = errors.ErrorLog()


@dataclasses.dataclass
class Analysis:
  """Analysis results."""

  context: Context
  ast: Optional[pytd.TypeDeclUnit]
  ast_deps: Optional[pytd.TypeDeclUnit]


def check_types(
    src: str,
    options: config.Options,
    loader: load_pytd.Loader,
    init_maximum_depth: int = _INIT_MAXIMUM_DEPTH,
    maximum_depth: int = _MAXIMUM_DEPTH,
) -> Analysis:
  """Check types for the given source code."""
  _analyze(src, options, loader, init_maximum_depth, maximum_depth)
  return Analysis(Context(), None, None)


def infer_types(
    src: str,
    options: config.Options,
    loader: load_pytd.Loader,
    init_maximum_depth: int = _INIT_MAXIMUM_DEPTH,
    maximum_depth: int = _MAXIMUM_DEPTH,
) -> Analysis:
  """Infer types for the given source code."""
  _analyze(src, options, loader, init_maximum_depth, maximum_depth)
  ast = pytd.TypeDeclUnit('inferred + unknowns', (), (), (), (), ())
  deps = pytd.TypeDeclUnit('<all>', (), (), (), (), ())
  return Analysis(Context(), ast, deps)


def _analyze(
    src: str,
    options: config.Options,
    loader: load_pytd.Loader,
    init_maximum_depth: int,
    maximum_depth: int,
) -> None:
  """Analyze the given source code."""
  del loader, init_maximum_depth, maximum_depth
  code = _get_bytecode(src, options)
  # TODO(b/241479600): Populate globals from builtins.
  globals_ = {}
  module_vm = vm.VM(code, initial_locals=globals_, globals_=globals_)
  module_vm.run()
  # TODO(b/241479600): Analyze classes and functions.


def _get_bytecode(src: str, options: config.Options) -> blocks.OrderedCode:
  code = pyc.compile_src(
      src=src,
      python_version=options.python_version,
      python_exe=options.python_exe,
      filename=options.input,
      mode='exec',
  )
  ordered_code, unused_block_graph = blocks.process_code(code)
  return ordered_code
