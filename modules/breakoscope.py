''' Breakoscope Project
    
    Pavel Odvody <podvody@redhat.com> - 2017
    License: LGPL-3.0
    ---

    This file is loaded into GDB via the `-P` flag, two positional arguments
    are expected when invoking this file
  
    1) Breakoscope module to invoke
    2) Path to a file where to store result data

    The output is currently always a JSON document.
    For more information about the module definition and directory layout structure
    please refer to TODO: documentation.
'''
import gdb
import os
import json
import sys
import yaml


def dict_append_list(dictionary, key, value):
    ''' Provides simple way to store multiple `value`'s under `key` in the
        given `dictionary` without having to manually handle the vacant/present
        scenario

    '''
    if not value:
        return
    if key not in dictionary:
        dictionary[key] = [value]
    else:
        dictionary[key].append(value)
    dictionary[key] = list(set(dictionary[key]))


def get_string_value(spec):
    ''' Get a string value from the debugged process based on `spec`
        which is evaluated by GDB

    '''
    data = gdb.parse_and_eval(spec)
    if data.address and (data.address - 1) == 0:
        # Make sure we're not trying to dereference a null pointer here
        # by first checking that the given value is not a register value
        # (so having `address` field equal to None) and then checking the
        # address itself against 0.
        # GDB (for reasons unknown) adds sizeof(void*) to the address, so we
        # need to subtract 1 (yes, 1, due to operator overloading the address
        # field is mimicking pointer arithmetic)
        return None

    return data.string()


def string_result_append(source=None, dest='config_files'):
    ''' Curry `source` specification and `dest` destination key
        into a function that accepts current `invocation` context
        and return it

    '''
    def inner(invocation):
        ''' Curried function to be returned '''
        dict_append_list(invocation.output, dest, get_string_value(source))
    return inner


def _breakpoint_handler(event, invocation):
    ''' Handler for `gdb.events.stop` events

    '''
    # Could be `gdb.SignalEvent` as well
    if not isinstance(event, gdb.BreakpointEvent):
        return
    # Lookup & invoke breakpoint handler
    invocation.breakpoints[event.breakpoint.number](invocation)
    # Continue execution
    gdb.execute('c')


def _exit_handler(_, invocation):
    ''' Exit handler is callled when *debuggee* exits

    '''
    json.dump(invocation.output,
              open(invocation.outfile, 'a+'), indent=4)


def _terminate(invocation):
    ''' Gracefully terminate the exeuction, retaining any results

    '''
    _exit_handler(None, invocation)
    exit(0)


def _error(message):
    ''' Called when unrecoverable error is encountered

    '''
    print(message)
    exit(1)


def _get_rpm_version(package):
    ''' Get "version-relase" string of installed RPM or exit with error

    '''
    # The `subprocess.check_output` function performs bunch of things that are
    # incompatible with the environment inside GDB, so fallback
    # to using `os.popen` here
    handle = os.popen(
        'rpm -q --queryformat %{{version}}-%{{release}} {package}'.format(package=package)
    )
    value = handle.read()
    compound_error_code = handle.close()
    if compound_error_code:
        _error('RPM "{}" not installed:\n\n{}'.format(package,
                                                      (compound_error_code >> 8) & 0xFF))
    return value


def _breakoscope_invoke(module_path=None, outfile=None):
    ''' Invoke Breakoscope with configuration provided in YAML file at
        `module_path` and store result in `outfile`.

    '''
    module = yaml.load(open(module_path, 'r'))
    I = BreakoscopeInvocation()
    I.binary = module['binary']
    I.package = module['package']
    I.args = module.get('args', None)
    I.versions = {}
    I.outfile = outfile
    # Load version specific breakpoint definition
    for version, handler in module['versions'].items():
        breakpoints = []
        for breakpoint in handler['breakpoints']:
            if breakpoint['source'].startswith('py:'):
                # The `source` field in the breakpoint definition can either refer to:
                # 1) Name of a symbol from current frame which holds the desired value
                # 2) If the value starts with `py:` you can call arbitrary Python
                #    module/function, so for instance:
                #
                #       `py:logrotate.logrotate_handler`
                #
                #    will import function `logrotate_handler` from the `logrotate` 
                #    module and use it as the breakpoint's handler.
                mod, f = breakpoint['source'][3:].split('.')
                code = open(mod + '/__init__.py').read()
                # Compile the code in place and evaluate it, this allows us to grab
                # the function from locals, but special care needs to be taken to make
                # sure that the function name doesn't clash with any identifier already
                # present in the locals dict.
                eval(compile(code, '<dynamic>', 'exec'))
                func = locals()[f]
            else:
                func = string_result_append(source=breakpoint['source'], 
                                            dest=breakpoint.get('dest', 'config_files'))
            breakpoints.append((breakpoint['spec'], func))
        I.versions[version] = {'breakpoints': breakpoints, 'terminator': handler['terminator']}
    # Module loading done, run now
    I.run()


class BreakoscopeInvocation:

    ''' Absolute path to a binary to be executed '''
    binary = None

    ''' Runtime arguments to the binary '''
    args = None

    ''' Name of the RPM package providing `self.binary` '''
    package = None

    ''' The `self.versions` field contains mapping of RPM package versions to
        corresponding breakpoint locations for both generic and terminator
        breakpoints.

        Example:

            versions = {
                '1.0.0': {
                    'breakpoints': [('config.c:560', handler)],
                    'terminator': 'main.c:45'
                }
            }

        `breakpoints` - list of (spec, handler) tuples, where `spec` is a regular
                        string specifying the location of generic breakpoint using GDB
                        syntax, and `handler` the function being invoked when the
                        the particular breakpoint is hit
        `terminator`  - string specification of code location where we stop executing
                        the debuggee so that we can print results and exit

        It is advisable to place the `terminator` breakpoint very close after the code
        area responsible for initiating the reading of configurations files to minimize
        the possible side effects of dynamic instrumentation
    '''
    versions = None

    ''' Target file where output JSON will be written '''
    outfile = None

    def __init__(self):
        self._breakpoints = {}
        self._output = {}
        #self._run()

    @property
    def breakpoints(self):
        ''' Breakpoints getter '''
        return self._breakpoints

    @property
    def output(self):
        ''' Output getter '''
        return self._output

    def _find_version_data_or_exit(self):
        ''' Find version record for our `rpm` or exit

        '''
        version = _get_rpm_version(self.package)
        for ver, data in self.versions.items():
            # TODO: Do proper version comparison & wildcards support
            if version.startswith(ver):
                return data
        msg = "Unable to find matching handler for: {package}-{version}"
        _error(msg.format(package=self.package, version=version))

    def _add_breakpoint(self, spec, handler):
        ''' Handle breakpoint with `spec` specification using `handler`

        '''
        brk = gdb.execute('b ' + spec, to_string=True)
        if not brk.startswith('Breakpoint'):
            _error('Unable to set breakpoint: "{}"'.format(spec))
        _, num, _ = brk.split(' ', 2)
        self._breakpoints[int(num)] = handler

    def run(self):
        ''' Run the debugging flow:

            1) Find version of `self.package` currently installed, or exit
            2) Load `self.binary` into GDB
            3) Register generic + terminator breakpoints
            4) Connect to `stop` and `exited` GDB event streams
            5) Run the program with args from `self.args`

        '''
        data = self._find_version_data_or_exit()
        gdb.execute('file {binary}'.format(binary=self.binary))
        for breakpoint in [(data['terminator'], _terminate)] + data['breakpoints']:
            self._add_breakpoint(breakpoint[0], breakpoint[1])
        # Curry event handlers with `self` reference
        gdb.events.stop.connect(lambda event: _breakpoint_handler(event, self))
        gdb.events.exited.connect(lambda event: _exit_handler(event, self))
        run = 'r'
        if self.args:
            run += ' ' + self.args
        gdb.execute(run)


if len(sys.argv) < 2:
    _error('Expected 2 arguments')
_breakoscope_invoke(sys.argv[0], sys.argv[1])
