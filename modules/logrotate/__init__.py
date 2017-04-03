def logrotate_handler(invocation):
    from os.path import join, isabs

    # Read relative file name of the config file
    value = get_string_value('configFile')

    # Move to callers stack frame since the string
    # that was used to chdir() is stored there
    gdb.execute('f 1')

    # Read current directory string
    base = get_string_value('path')

    # Join paths only if path isn't already absolute
    if base and value and not isabs(value):
        value = join(base, value)
    dict_append_list(invocation.output, 'config_files', value)

