"""Generic functions."""

import itertools
import re
import traceback


from pytype.pytd import pytd


def variable_product(variables):
  """Take the Cartesian product of a number of Variables.

  Args:
    variables: A sequence of Variables.

  Returns:
    A list of lists of Values, where each sublist has one element from each
    of the given Variables.
  """
  return itertools.product(*(v.values for v in variables))


def _variable_product_items(variableitems):
  """Take the Cartesian product of a list of (key, value) tuples.

  See variable_product_dict below.

  Args:
    variableitems: A dict mapping object to typegraph.Variable.

  Yields:
    A sequence of [(key, typegraph.Value), ...] lists.
  """
  if variableitems:
    headkey, headvar = variableitems[0]
    for tail in _variable_product_items(variableitems[1:]):
      for headvalue in headvar.values:
        yield [(headkey, headvalue)] + tail
  else:
    yield []


def variable_product_dict(variabledict):
  """Take the Cartesian product of variables in the values of a dict.

  This Cartesian product is taken using the dict keys as the indices into the
  input and output dicts. So:
    variable_product_dict({"x": Variable(a, b), "y": Variable(c, d)})
      ==
    [{"x": a, "y": c}, {"x": a, "y": d}, {"x": b, "y": c}, {"x": b, "y": d}]
  This is exactly analogous to a traditional Cartesian product except that
  instead of trying each possible value of a numbered position, we are trying
  each possible value of a named position.

  Args:
    variabledict: A dict with variable values.

  Returns:
    A list of dicts with Value values.
  """
  return [dict(d) for d in _variable_product_items(variabledict.items())]


def maybe_truncate(s, length=30):
  """Truncate long strings (and append '...'), but leave short strings alone."""
  s = str(s)
  if len(s) > length-3:
    return s[0:length-3] + "..."
  else:
    return s


def pretty_conjunction(conjunction):
  """Pretty-print a conjunction. Use parentheses as necessary.

  E.g. ["a", "b"] -> "(a & b)"

  Args:
    conjunction: List of strings.
  Returns:
    A pretty-printed string.
  """
  if not conjunction:
    return "true"
  elif len(conjunction) == 1:
    return conjunction[0]
  else:
    return "(" + " & ".join(conjunction) + ")"


def pretty_dnf(dnf):
  """Pretty-print a disjunctive normal form (disjunction of conjunctions).

  E.g. [["a", "b"], ["c"]] -> "(a & b) | c".

  Args:
    dnf: A list of list of strings. (Disjunction of conjunctions of strings)
  Returns:
    A pretty-printed string.
  """
  if not dnf:
    return "false"
  else:
    return " | ".join(pretty_conjunction(c) for c in dnf)


def numeric_sort_key(s):
  return tuple((int(e) if e.isdigit() else e) for e in re.split(r"(\d+)", s))


def compute_predecessors(nodes):
  """Build a transitive closure.

  For a list of nodes, compute all the predecessors of each node.

  Args:
    nodes: A list of nodes or blocks.
  Returns:
    A dictionary that maps each node to a set of all the nodes that can reach
    that node.
  """
  # incoming + node because our CFGs are reflexive: Every node can reach itself.
  predecessors = {node: set(node.incoming) | {node} for node in nodes}

  # This is essentially Floyd-Warshall, except we compute sets of predecessors
  # instead of minimal distances.
  for n1 in nodes:
    for n2 in nodes:
      for n3 in nodes:
        # n2 -> n1 -> n3
        if n2 in predecessors[n1] and n1 in predecessors[n3]:
          predecessors[n3].add(n2)

  return predecessors


def order_nodes(nodes):
  """Build an ancestors first traversal of CFG nodes.

  This guarantees that at least one predecessor of a block is scheduled before
  the block itself, and it also tries to schedule as many of them before the
  block as possible (so e.g. if two branches merge in a node, it prefers to
  process both the branches before that node).

  Args:
    nodes: A list of nodes or blocks. They have two attributes: "incoming" and
      "outgoing". Both are lists of other nodes.
  Returns:
    A list of nodes in the proper order.
  """
  if not nodes:
    return []
  root = nodes[0]
  predecessor_map = compute_predecessors(nodes)
  dead = {node for node, predecessors in predecessor_map.items()
          if root not in predecessors}
  queue = {root: predecessor_map[root]}
  order = []
  seen = set()
  while queue:
    # Find node with minimum amount of predecessors that's connected to a node
    # we already processed.
    _, _, node = min((len(predecessors), node.id, node)
                     for node, predecessors in queue.items())
    del queue[node]
    if node in seen:
      continue
    order.append(node)
    seen.add(node)
    # Remove this node from the predecessors of all nodes after it.
    for _, predecessors in queue.items():
      predecessors.discard(node)
    # Potentially schedule nodes we couldn't reach before:
    for n in node.outgoing:
      if not hasattr(n, "incoming"):
        # UNKNOWN_TARGET etc.
        continue
      if n not in queue:
        queue[n] = predecessor_map[n] - seen

  # check that we don't have duplicates and that we didn't miss anything:
  assert len(set(order) | dead) == len(set(nodes))

  return order


def flattened_superclasses(cls):
  """Given a pytd.Class return a list of all superclasses.

  Args:
    cls: A pytd.Class object.
  Returns:
    A frozenset of all superclasses of the given class including itself and any
    transitive superclasses.
  """
  if isinstance(cls, pytd.ClassType):
    cls = cls.cls
  return frozenset([cls]) | frozenset(c
                                      for base in cls.parents
                                      for c in flattened_superclasses(base))


class HashableDict(dict):
  """A dict subclass that can be hashed.

  Instances should not be modified. Methods that would modify the dictionary
  have been overwritten to throw an exception.
  """

  def __init__(self, *args, **kwargs):
    super(HashableDict, self).__init__(*args, **kwargs)
    self._hash = hash(frozenset(self.items()))

  def update(self):
    raise TypeError()

  def clear(self):
    raise TypeError()

  def pop(self):
    raise TypeError()

  def popitem(self):
    raise TypeError()

  def setdefault(self):
    raise TypeError()

  def __setitem__(self):
    raise TypeError()

  def __delitem__(self):
    raise TypeError()

  def __hash__(self):
    return self._hash


def log_traceback(logger_call, msg):
  """Put a "compact" reversed traceback into the log, for debugging.

  It combines the regular traceback's 2 lines per item to a single line and
  shortens the file path to the "interesting" part.

  Sample ouput:
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/typegraphvm.py", line 490, in convert_constant                  utils.log_traceback(log.error, '***tb: %s')
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/typegraphvm.py", line 611, in maybe_convert_constant            return self.convert_constant(name, pyval)
    ERROR:pytype.typegraphvm:***tb: File "pytype/typegraph/atomic_abstract_value.py", line 755, in _load_attribute  variable = self._resolver(name, self._member_map[name])
    ERROR:pytype.typegraphvm:***tb: File "pytype/typegraph/atomic_abstract_value.py", line 769, in has_attribute    self._load_attribute(name)
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/typegraphvm.py", line 895, in load_from                         if not store.has_attribute(name):
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/typegraphvm.py", line 909, in load_builtin                      return self.load_from(self.frame.f_builtins, name)
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/pyvm2.py", line 777, in byte_LOAD_GLOBAL                        val = self.load_builtin(name)
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/pyvm2.py", line 404, in dispatch                                why = bytecode_fn(*arguments)
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/pyvm2.py", line 483, in run_instruction                         why = self.dispatch(byteName, arguments)
    ERROR:pytype.typegraphvm:***tb: File "py/pytype/typegraphvm.py", line 750, in run_frame                         why = self.run_instruction()

  Args:
    logger_call: something that accepts the same args as logging.info
    msg: a log format string with exactly one %s in it
  """
  # TODO(pludemann): remove this function when it's no longer needed.
  fixed_lines = reversed([_shorten_traceback_line_filename(tb) for tb in
                          traceback.extract_stack()])
  for l in traceback.format_list(fixed_lines)[1:]:
    # traceback.format_list is always two lines; split, shorten and combine
    l1, l2 = l.strip().split('\n')
    # ljust(80) happens to work reasonably well, if your screen is about
    # 170 chars wide:
    logger_call(msg, l1.ljust(80) + l2.lstrip())


def _shorten_traceback_line_filename(tb_line):
  # extract last part of path
  return ("/".join(tb_line[0].split("/")[-3:]),) + tb_line[1:]


def mro_merge(seqs):
  """Merge a sequence of MROs into a single resulting MRO.

  This code is copied from the following URL with print statments removed.
  https://www.python.org/download/releases/2.3/mro/

  Args:
    seqs: A sequence of MROs.

  Returns:
    A single resulting MRO.

  Raises:
    TypeError: If we discovered an illegal inheritance.
  """
  res = []
  while True:
    nonemptyseqs = [seq for seq in seqs if seq]
    if not nonemptyseqs:
      return res
    for seq in nonemptyseqs:  # find merge candidates among seq heads
      cand = seq[0]
      nothead = [s for s in nonemptyseqs if cand in s[1:]]
      if nothead:
        cand = None  # reject candidate
      else:
        break
    if not cand:
      raise TypeError("Illegal inheritance.")
    res.append(cand)
    for seq in nonemptyseqs:  # remove candidate
      if seq[0] == cand:
        del seq[0]


def compute_mro(c):
  """Compute the class precedence list (mro) according to C3.

  This code is copied from the following URL with print statements removed.
  https://www.python.org/download/releases/2.3/mro/

  Args:
    c: The Class to compute the MRO for. This needs to be an instance
      with the members "mro" and "bases".
  Returns:
    A list of Class objects in Method Resolution Order.
  """
  return tuple(mro_merge([[c]] +
                         [list(base.mro) for base in c.bases()] +
                         [list(c.bases())]))
