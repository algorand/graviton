<!-- markdownlint-disable no-inline-html -->
<!-- markdownlint-disable ol-prefix -->
<!-- markdownlint-disable first-line-h1 -->
<p align="center"><img  width=100%  src="https://infura-ipfs.io/ipfs/QmUJQFQET7VHyfDepM9CNhGBEabjH42XzK39kAisPWdE3K"  border="0" /></p>

Graviton (aka the TEAL Blackbox Toolkit): Program Reporting and Testing via Dry Runs

**NOTE: to get math formulas to render here using Chrome, add the [xhub extension](https://chrome.google.com/webstore/detail/xhub/anidddebgkllnnnnjfkmjcaallemhjee/related) and reload.**

**DISCLAIMER**: Graviton is subject to change and makes no backwards compatability guarantees.

## Blackbox Testing Howto

### What is TEAL Blackbox Testing?

TEAL Blackbox Testing lets you gain confidence that your Algorand smart contracts
are correct by writing assertions and analyzing results via dry runs.

### Why Blackbox Testing?

Here are some use cases:

* by allowing you to assert that certain invariants hold over a large set of inputs you gain greater confidence that your TEAL programs and AVM smart contracts work as designed
* when tweaking, refactoring or optimizing your TEAL source, ensure that no regressions have occurred
* allows AVM developers to practice the art of TTDD (TEAL Test Driven Development)

## Simple TEAL Blackbox Toolkit Example: Program for $`x^2`$

Consider this [TEAL program](./tests/teal/lsig_square.teal) for computing $`x^2`$:

```plain
#pragma version 6
arg 0
btoi
callsub square_0
return

// square
square_0:
store 0
load 0
pushint 2 // 2
exp
retsub
```

We'd like to write some unit tests to validate its correctness and make **assertions** about the:

* program's opcode cost
* program's stack
* stack's height
* scratch variables
* final log message (this is especially useful for [ABI-compliant programs](https://developer.algorand.org/docs/get-details/dapps/smart-contracts/ABI/))
* status (**PASS** or **REJECT**)
* error conditions that are and aren't encountered

Even better, before making fine-grained assertions we'd like to get a sense of what the program is doing on a large set of inputs and discover _experimentally_ these **program invariants**. Let's go through how we can do this:

* start by making basic assertions and validate them using dry runs (see "**Basic Assertions**" section below)
* execute the program on a sequence of inputs and explore the results (see "**EDRA: Exploratory Dry Run Analysis**" section below)
* create invariants for the entire sequence and assert that the invariants hold (see "**Advanced: Asserting Invariants on a Dry Run Sequence**" section below)

> Becoming a TEAL Blackbox Toolkit Ninja involves 10 steps as described below

### Dry Run Environment Setup

**STEP 1**. Start with a running local node and make note of Algod's port number (for our [standard sandbox](https://github.com/algorand/sandbox) this is `4001`)

**STEP 2**. Set the `ALGOD_PORT` value in [tests/clients.py](./tests/clients.py#L7) to this port number. (The port is already pre-set to `4001` because [graviton](https://github.com/algorand/graviton)'s [CI process](https://en.wikipedia.org/wiki/Continuous_integration) uses the standad sandbox)

### TEAL Program for Testing: Logic Sig v. App

**STEP 3**. Next, you'll need to figure out if your TEAL program should be a Logic Signature or an Application. Each of these program _modes_ has its merits, but we won't get into the pros/cons here. From a Blackbox Test's perspective, the main difference is how external arguments are handled. Logic sigs rely on the [arg opcode](https://developer.algorand.org/docs/get-details/dapps/avm/teal/opcodes/#arg-n) while apps rely on [txna ApplicationArgs i](https://developer.algorand.org/docs/get-details/dapps/avm/teal/opcodes/#txna-f-i). In our $`x^2`$ **logic sig** example, you can see on [line 2](./tests/teal/lsig_square.teal#L2) that the `arg` opcode is used. Because each argument opcode (`arg` versus `ApplicationArgs`) is mode-exclusive, any program that takes input will execute successfully in _one mode only_.

**STEP 4**. Write the TEAL program that you want to test. You can inline the test as described here or follow the approach of `./tests/integration/blackbox_test.py` and save under `./tests/teal`. So following the inline
approach we begin our TEAL Blackbox script with an <a name="teal">inline teal source variable</a>:

```python
teal = """#pragma version 6
arg 0
btoi
callsub square_0
return

// square
square_0:
store 0
load 0
pushint 2 // 2
exp
retsub"""
```

### The TEAL Blackbox Toolkit's Utility Classes

The TEAL Blackbox Toolkit comes with the following main classes:

* `DryRunExecutor` - executes dry run's for apps and logic sigs for one or more inputs
* `DryRunInspector` - encapsulates a dry run's result for a single input and allows inspecting and making assertions about it
* `Invariant` - class for asserting invariants about a _sequence_ of dry run executions in a declarative fashion

### Basic Assertions

When executing a dry run using  `DryRunExecutor` you'll get back `DryRunInspector` objects. Such objects have
**assertable properties** which can be used to validate the dry run.

**STEP 4**. Back to our $`x^2`$ example, and assuming the `teal`  variable is defined [as above](#teal). You can run the following:

```python
from graviton.blackbox import DryRunExecutor
from tests.clients import get_algod

algod = get_algod()
x = 9
args = (x,)
inspector = DryRunExecutor.dryrun_logicsig(algod, teal, args)
assert inspector.status() == "PASS"
assert inspector.stack_top() == x**2
```

Here we have executed a dry run on input $`x=9`$, then asserted that:

* the program status was `PASS`
* the program exited with the top of its stack containing $`x^2 = 9^2 = 81`$

Some available _assertable properties_ are:

* `stack_top()`
* `last_log()`
* `cost()`
* `status()`
* `final_scratch()`
* `error()`
* `max_stack_height()`

See the [DryRunInspector class comment](./graviton/blackbox.py#L387) for more assertable properties and details.

### Printing out the TEAL Stack Trace for a Failing Assertion

**STEP 5**. The `DryRunInspector`'s `report()` method lets you print out
a handy report in the case of a failing assertion. Let's intentionally break the test case above by claiming that $`x^2 = x^3`$ for $`x=2`$ and print out this _report_ when our silly assertion fails.

```python
from graviton.blackbox import DryRunExecutor
from tests.clients import get_algod

algod = get_algod()
x = 2
args = (x,)
inspector = DryRunExecutor.dryrun_logicsig(algod, teal, args)

# This one's ok
expected, actual = "PASS", inspector.status()
assert expected == actual, inspector.report(
    args, f"expected {expected} but got {actual}"
)

# This one's absurd! x^3 != x^2
expected, actual = x**3, inspector.stack_top()
assert expected == actual, inspector.report(
    args, f"expected {expected} but got {actual}"
)
```

If we run the test (e.g. with `pytest`) we'll see a printout such as:

```sh
AssertionError:
===============
<<<<<<<<<<<expected 8 but got 4>>>>>>>>>>>
===============
      App Trace:
   step |   PC# |   L# | Teal              | Scratch   | Stack
--------+-------+------+-------------------+-----------+----------------------
      1 |     1 |    1 | #pragma version 6 |           | []
      2 |     2 |    2 | arg_0             |           | [0x0000000000000002]
      3 |     3 |    3 | btoi              |           | [2]
      4 |     7 |    6 | label1:           |           | [2]
      5 |     9 |    7 | store 0           | 0->2      | []
      6 |    11 |    8 | load 0            |           | [2]
      7 |    13 |    9 | pushint 2         |           | [2, 2]
      8 |    14 |   10 | exp               |           | [4]
      9 |     6 |    4 | callsub label1    |           | [4]
     10 |    15 |   11 | retsub            |           | [4]
===============
MODE: ExecutionMode.Signature
TOTAL COST: None
===============
FINAL MESSAGE: PASS
===============
Messages: ['PASS']
Logs: []
===============
-----BlackBoxResult(steps_executed=10)-----
TOTAL STEPS: 10
FINAL STACK: [4]
FINAL STACK TOP: 4
MAX STACK HEIGHT: 2
FINAL SCRATCH: {0: 2}
SLOTS USED: [0]
FINAL AS ROW: {'steps': 10, ' top_of_stack': 4, 'max_stack_height': 2, 's@000': 2}
===============
Global Delta:
[]
===============
Local Delta:
[]
===============
TXN AS ROW: {' Run': 0, ' cost': None, ' last_log': '`None', ' final_message': 'PASS', ' Status': 'PASS', 'steps': 10, ' top_of_stack': 4, 'max_stack_height': 2, 's@000': 2, 'Arg_00': 2}
===============
<<<<<<<<<<<expected 8 but got 4>>>>>>>>>>>
===============
assert 8 == 4
```

In particular, we can:

* Track the program execution by viewing its **App Trace**
  * 2 was assigned to **scratch slot #0** at step 5
  * the stack ended up with **4** on top
  * the run **PASS**'ed
* Read the message parameter that was provided and which explains in English what went wrong: `expected 8 but got 4`

### EDRA: Exploratory Dry Run Analysis

Let's expand our investigation from a single dry-run to multiple runs or a **run sequence**. We'll observe how _assertable properties_ depend on inputs and conjecture some program invariants. To aid in the investigation we'll generate a report in CSV format (Comma Separated Values) where:

* columns represent _assertable properties_ of dry-runs, and
* rows represent dry-run executions for specific inputs

**STEP 6**. Back to our $`x^2`$ example, here's how to generate a report with 1 row for each of the inputs `0, 1, ... , 15`:

```python
from graviton.blackbox import DryRunExecutor, DryRunInspector
from tests.clients import get_algod

algod = get_algod()
inputs = [(x,) for x in range(16)]
run_results = DryRunExecutor.dryrun_logicsig_on_sequence(algod, teal, inputs)
csv = DryRunInspector.csv_report(inputs, run_results)
print(csv)
```

Note that each element in the `inputs` array `(x,)` is itself a tuple as `args` given to a dry run execution need to be of type `Sequence` (remember, that these will be passed to a TEAL program which may take one, several, or no inputs at all).
At this point, you'll be able to look at your [dry run sequence results](./graviton/blackbox.py#L752) and conduct some analysis. For the $`x^2`$ example,
after loading the CSV in Google sheets and reformatting a bit it will look like:

<img width="465" alt="image" src="https://user-images.githubusercontent.com/291133/158812699-318169e2-487c-4dac-b97b-a9db8148b638.png">

Pointing out some interesting results:

* column `D` **Arg 00** has the input $`x`$ (it's the argument at index 0)
* column `A` contains the **Run** number
* column `E`  **top of stack** is the value at program's termination, i.e.  $`x^2`$
* column `B` **Status** of each runs **PASS**es _except for **Run 1** with **Arg 00** = 0_. (The first run **REJECT**s because $`0^2 = 0`$ and TEAL programs reject when the top of the stack is 0)
* column `G` shows scratch slot **s@000** which stores the value of $`x`$ (except for the case $`x = 0`$ in which appears empty; in fact, slots always default to the zero value and an **<a name="0val-artifact">artifact</a>** of dry-runs is that they do not report when 0-values get stored into previously empty slots as no state change actually occurs)
* column `F` **max stack height** is always 2. The final observation makes sense because there is no branching or looping in the program.

**STEP 7**. We can re-cast the observed effects in `Columns E, B, G, F` as **invariants** written in Python as follows:

* `inspector.stack_top() == x ** 2`
* `inspector.max_stack_height() == 2`
* `inspector.status() == ("REJECT" if x == 0 else "PASS")`
* `inspector.final_scratch() == ({} if x == 0 else {0: x})`

### Advanced: Asserting Invariants on a Dry Run Sequence

The final and most advanced topic we'll cover is how
to assert that invariants hold on a sequence of inputs. Lets take the information we gleaned in our EDRA CSV report,
and create an integration test out of it. There are two ways to achieve this goal:

* Procedural invariant assertions
* Declarative invariant assertions

#### Procedural Blackbox Dry Run Sequence Assertions

**STEP 8**. The procedural approach takes the _invariants_ and simply asserts them
inside of a for loop that iterates over the inputs and dry runs. One can call each dry run
execution independently, or use `DryRunExecutor`'s convenience methods `dryrun_app_on_sequence()` and
`dryrun_logicsig_on_sequence()`. For example, let's assert that the above invariants hold for all
$`x \leq 100`$:

```python
from graviton.blackbox import DryRunExecutor
from tests.clients import get_algod

algod = get_algod()
inputs = [(x,) for x in range(101)]
dryrun_results = DryRunExecutor.dryrun_logicsig_on_sequence(algod, teal, inputs)
for i, inspector in enumerate(dryrun_results):
    args = inputs[i]
    x = args[0]
    assert inspector.stack_top() == x**2
    assert inspector.max_stack_height() == 2
    assert inspector.status() == ("REJECT" if x == 0 else "PASS")
    assert inspector.final_scratch() == ({} if x == 0 else {0: x})
```

#### Declarative Blackbox Dry Run Sequence Assertions

**STEP 9**. The TEAL Blackbox Toolkit also allows for declarative style test writing.
Let's define some invariants for a particular
sequence of `lsig_square` TEAL program dry runs:

```python
scenario = {
    "inputs": [(i,) for i in range(100)],
    "invariants": {
        DRProp.stackTop: lambda args: args[0] ** 2,
        DRProp.maxStackHeight: 2,
        DRProp.status: lambda i: "REJECT" if i[0] = 0 else "PASS",
        DRProp.finalScratch: lambda args: ({} if args[0] else {0: args[0]}),
    },
}
```

In the parlance of the TEAL Blackbox Toolkit, a set of such declarative assertions
is called a **test scenario**. Scenarios are dict's containing two keys `inputs` and `invariants` and follow [certain conventions](./graviton/invariant.py#L101). In particular:

* **inputs** gives a list of tuples, each tuple representing the `args` to be fed into a single dry run execution
* **invariants** gives a dict that maps [DryRunProperty](./graviton/blackbox.py#L25)'s to an invariant _predicate_

In English, letting $`x`$ be the input variable for our square function, the above **test scenario**:

* provides a list of 100 tuples of the form $`(x)`$ that will serve as args.
  * IE: $`(0), (1), (2), ... , (99)`$
* establishes 4 different _invariants_ as follows:
  * the **stack's top** will contain $`x^2`$
  * the **max stack height** during execution is always 2
  * the executions' **status** is **PASS** except for the case $`x=0`$
  * the **final scratch** will have $`x`$ stored at slot `0` except for that strange $`x=0`$ case (recall the [0-val scratch slot artifact](#0val-artifact))

Declarative invariants make use of the following:

* `DryRunProperty` (aka `DRProp`): an enum that acts as a key in a scenario's assertions dict
* class `Invariant`
  * its constructor takes in a predicate (there are [4 kinds of predicates](#predicate)) and returns a callable that is used for runtime assertions
  * method `inputs_and_assertions()` validates a scenario and extracts out its assertions
  * method `dryrun_assert()` evaluates the dry-run sequence using the constructed `SequenceAssertion`

To employ the declarative test scenario above write the following:

```python
from graviton.blackbox import (
    DryRunExecutor,
    DryRunProperty as DRProp,
    ExecutionMode,
)
from graviton.invariant import Invariant
from tests.clients import get_algod

algod = get_algod()

scenario = {
    "inputs": [(i,) for i in range(100)],
    "invariants": {
        DRProp.stackTop: lambda args: args[0] ** 2,
        DRProp.maxStackHeight: 2,
        DRProp.status: lambda args: "REJECT" if args[0] == 0 else "PASS",
        DRProp.finalScratch: lambda args: ({0: args[0]} if args[0] else {}),
    },
}

# Validate the scenario and dig out inputs/invariants:
inputs, invariants = Invariant.inputs_and_invariants(
    scenario, ExecutionMode.Signature
)

# Execute the dry runs and obtain a sequence of DryRunInspectors:
inspectors = DryRunExecutor.dryrun_logicsig_on_sequence(algod, teal, inputs)

# Invariant assertions on sequence:
for dr_property, invariant in invariants.items():
    invariant.validates(dr_property, inputs, inspectors)
```
  
**STEP 10**. _**Deep Dive into Invariants via Exercises**_

Four kinds of <a name="predicate">predicates</a> are used to define _invariants_:

1. _simple python types_ - these are useful in the case of _constant_ invariants. In the above `maxStackHeight` is asserted to _**ALWAYS**_ equal 2 by using `2` in the declaration:

`DRProp.maxStackHeight: 2`

2. _1-variable functions_ -these are useful when you have a python "simulator" for the invariant. In the above `stackTop` is asserted to be $`x^2`$ by using a lambda expression for $`x^2`$ in the declaration:

`DRProp.stackTop: lambda args: args[0] ** 2`

3. _dictionaries_ of type `Dict[Tuple, Any]` - these are useful when you want to assert a discrete set of input-output pairs. For example, if you have 4 inputs that you want to assert are being squared, you could use

```python
DRProp.stackTop: {
  (2,): 4,
  (7,): 49,
  (13,): 169,
  (11,): 121,
}
```

>Note that this case illustrates why each `args` container should be a tuple intead of a list. In order to specify a map from args to expected, we need to make `args` a key in a dictionary. Python dictionary keys must be hashable and lists are _not hashable_ while tuples _are_ hashable, hence the tuple-requirement.

4. _2-variable functions_ -these are useful when your assertion is more subtle than out-and-out equality. For example, suppose you want to assert that the `cost` of each run is _between_ $`2n \pm 5`$ where $`n`$ is the first arg of the input. Then you could declare:

`DRProp.cost: lambda args, actual: 2*args[0] - 5 <= actual <= 2*args[0] + 5`

#### **EXERCISE A**

Convert each of the lambda expressions used above to dictionaries that assert the same thing.

#### **EXERCISE B**

Use 2-variable functions in order to _ignore_ the
weird $`x=0`$ cases above.

#### _PARTIAL SOLUTIONS to EXERCISES_

**Exercise A Partial Solution**. For `DRProp.status`'s declaration you could define the `dict` using dictionary comprehension syntax as follows:

```python
DRProp.status: {(x,): "PASS" if x else "REJECT" for x in range(100)},
```

**Exercise B Partial Solution**. For `DRProp.status`'s declaration you could ignore the case $`x=0`$ as follows:

```python
DRProp.status: lambda args, actual: "PASS" == actual if args[0] else True,
```

## Slow and Bad Fibonacci - Another Example Report

[This](https://docs.google.com/spreadsheets/d/1ax-jQdYCkKT61Z6SPeGm5BqAMybgkWJa-Dv0yVjgFSA/edit?usp=sharing) is an example of `app_slow_fibonacci.teal`'s Dryrun stats:
<img width="1231" alt="image" src="https://user-images.githubusercontent.com/291133/158705149-302d755f-afcc-4380-976a-ca14800c138f.png">
A few items to take note of:

* $`n`$ is given by **Arg_00**
* the app was **REJECT**ed for $`n = 0`$ because `fibonacci(0) == 0` is left at the top of the stack
* the app was **REJECT**ed for $`n > 7`$ because of exceeding budget
* the app **errored** only for $`n > 16`$ because of exceeding _dynamic_ budget
* the **cost** is growing exponentially (poor algorithm design)
* the **top of stack** contains `fibonacci(n)` except in the error case
* the **final_log** contains `hex(fibonacci(n))` except in the error and reject cases
* **max stack height** is $`2n`$ except for $`n=0`$ and the error case
* you can see the final values of scratch slots **s@000** and **s@001** which are respectively $`n`$ and `fibonacci(n)`

Here's an example of how [invariants can be asserted](https://github.com/algorand/graviton/blob/a8c7eab729a36503948849674ea55995d5fc4ec1/tests/integration/blackbox_test.py#L315) on this function.
