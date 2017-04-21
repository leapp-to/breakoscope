Breakoscope 0.5
===============

Breakoscope is a project utilizing dynamic instrumentation of programs via a debbuger 
in order to extract runtime information in a precise, targeted way by leveraging 
simplified program model ("SPM"). The name is a portmanteau of terms "breakpoint" and "scope", 
think microscope, stethoscope, periscope ...


Usage
=====
Help:
```
$ breakoscope -h
breakoscope [-h | -v] MODULE
Execute Breakoscope module and output JSON formatted output

Options:

  -v   : print verbose information to stderr
  -vv  : print very verbose information to stderr
  -h   : display this information and exit
```

Example run of the `nginx` module:
```
$ breakoscope nginx
{
    "config_files": [
        "/etc/nginx/nginx.conf",
        "/etc/nginx/mime.types"
    ]
}
```

Prerequisites
=============

- GDB with Python3.X support
- PyYAML

Architecture
============

Breakoscope uses GDB automation script `breakoscope.py` to process module definition files 
and execute the actual analysis. Each module is defined as a directory with `definition.yml` 
YAML file inside:
```
/var/lib/breakoscope/<module_name>/definition.yml
```

So for example the `nginx` module looks as follows:
```
/var/lib/breakoscope/nginx/
└── definition.yml
```

The overall execution is centered around modules providing a set of interesting code locations 
from which we can extract desired data. This definition (see `versions.breakpoints.spec` below) 
is coupled with a handler (see `versions.breakpoints.source` below) that encapsulates the logic 
of extracting the value itself.

Module Definition
=================

The module definition itself looks as follows:
```
name: nginx module
binary: /usr/sbin/nginx
package: nginx
versions:
  1.10.2-1:
    breakpoints:
    - spec: ngx_conf_file.c:122
      source: filename->data
    terminator: ngx_cycle.c:280
```

The list of supported keys and their purpose is as follows:

| Key | Purpose |
|-----|---------|
| `name` | Generic name of the module |
| `binary` | Absolute path to a binary to execute |
| `package` | RPM package containing the binary |
| `user` | Execute the analysis as a specific user |
| `versions` | Dictionary of breakpoint mappings for different versions of the package |
| `versions.breakpoints` | A lists of breakpoints that will be used to extract data |
| `versions.breakpoints.spec` | Location specification |
| `versions.breakpoints.source` | Symbol in the current scope from which to extract data or custom handler |
| `versions.terminator` | Location where we stop executing and exit |

More detailed information can be found in the `BreakoscopeInvocation` class defined 
in `modules/breakoscope.py`.
Note that `versions.breakpoints.source` can also point to custom handler written in 
Python that can perform additional data formatting - this behavior is supported 
via the `py:module.function` syntax, for more information see the `logrotate` module.

Simplified Program Model
========================

The SPM models every program into two basic components:

1) Configuration
   Takes care of command line parsing and loading & parsing of config files
2) Main Loop
   Performs actual work and should never be reached as part of Breakoscope execution

Not every program can be modelled like this, however, empirically speaking the vast 
majority of programs can since they operate in the following way:

```
int main(argc, argv) {
    ...
    args = parsed_cmd_args(argc, argv)
    conf = parse_config(args)
    do_work(conf)
}
```

The reason why this model works is because it's the natural way how to handle *data dependencies*.
First we need to parse command line arguments, perhaps because our application supports supplying 
an alternate configuration file that way, but this step isn't stricly necessary and can be omitted. 
After the command line arguments have been dealt with, we proceed by loading and parsing the 
configuration file themselves. Only after the configuration files have been loaded, we have enough 
context to actually start doing something interesting. So instead of pseudocode, let's draw a 
data dependency diagram:

```
+-------------------+       +----------------------+       +--------------------+
|                   |       |                      |       |                    |
|  Parse arguments  +------>+  Parse config files  +------>+    Run main loop   |
|                   |       |                      |       |                    |
+-------------------+       +----------------------+       +--------------------+
```

Supported Applications
======================

Breakoscope currently contains modules for extracting configuration paths from the following applications:

- Apache HTTPD
- nginx
- MariaDB
- Logrotate
- ...

Contributing
============

If you find an error/bug please open an issue in the GitHub repository - https://github.com/leapp-to/breakoscope/issues - 
and make sure to fill in all the fields marked with `*` (required).
Code tweaks, bugfixes, new modules etc. are always welcome, please open a pull request and wait
for one of the reviewers to pick it up.


License
=======

The Breakoscope project is licensed under LGPL-3.0
