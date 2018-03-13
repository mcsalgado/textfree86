import os
import sys
import types
import itertools

def try_parse(arg, argtype):
    if argtype in ("int","integer"):
        try:
            i = int(arg)
            if str(i) == arg: return i
        except:
            raise Exception('badarg')

    elif argtype in ("float","num"):
        try:
            i = float(arg)
            if str(i) == arg: return i
        except:
            raise Exception('badarg')
    elif argtype in ("str", "string"):
        return arg
    elif argtype in ("bool", "boolean"):
        if arg == "true":
            return True
        elif arg == "false":
            return False
        raise Exception('badarg')
    try:
        i = int(arg)
        if str(i) == arg: return i
    except:
        pass
    try:
        f = float(arg)
        if str(f) == arg: return f
    except:
        pass
    return arg

def extract_args(template, argv):
    return args

def parse_argspec(argspec):
    """
        argspec is a short description of a command's expected args:
        "x y z"         three args (x,y,z) in that order
        "x y? z?"       three args, where the second two are optional. 
                        "arg1 arg2" is x=arg1, y=arg2, z=null
        "x y z..."      three args (x,y,z) where the final arg can be repeated 
                        "arg1 arg2 arg3 arg4" is z = [arg3, arg4]

        an argspec comes in the following format, and order
            <flags> <positional> <optional> <tail>

        for a option named 'foo', a:
            switch is '--foo?'
                `cmd --foo` foo is True
                `cmd`       foo is False
            flag is `--foo`
                `cmd --foo=x` foo is 'x'
            list is `--foo...`
                `cmd` foo is []
                `cmd --foo=1 --foo=2` foo is [1,2]
            positional is `foo`
                `cmd x`, foo is `x`
            optional is `foo?`
                `cmd` foo is null
                `cmd x` foo is x 
            tail is `foo...`
                `cmd` foo is []
                `cmd 1 2 3` foo is [1,2,3] 
    """
    positional = []
    optional = []
    tail = None
    flags = []
    lists = []
    switches = []

    args = argspec.split()

    argtypes = {}
    argnames = set()

    def argname(arg):
        if not arg:
            return arg
        if ':' in arg:
            name, atype = arg.split(':')
            argtypes[name] = atype 
        else:
            name = arg
        if name in argnames:
            raise Exception('duplicate arg name')
        argnames.add(name)
        return name

    nargs = len(args) 
    while args: # flags
        if not args[0].startswith('--'): break
        arg = args.pop(0)
        if arg.endswith('?'):
            if ':' in arg:
                raise Exception('switches have types')
            switches.append(argname(arg[2:-1]))
        elif arg.endswith('...'):
            lists.append(argname(arg[2:-3]))
        else:
            flags.append(argname(arg[2:]))

    while args: # positional
        if args[0].endswith(('...', '?')): break
        arg = args.pop(0)
        if arg.startswith('--'): raise Exception('badarg')
        positional.append(argname(arg))

    while args: # optional
        if args[0].endswith('...'): break
        arg = args.pop(0)
        if arg.startswith('--'): raise Exception('badarg')
        if not arg.endswith('?'): raise Exception('badarg')
        optional.append(argname(arg[:-1]))

    if args: # tail
        arg = args.pop(0)
        if arg.startswith('--'): raise Exception('badarg')
        if arg.endswith('?'): raise Exception('badarg')
        if not arg.endswith('...'): raise Exception('badarg')
        tail = argname(arg[:-3])

    if args:
        raise Exception('bad argspec')
    

    # check names are valid identifiers

    return nargs, {
            'switches': switches,
            'flags': flags,
            'lists': lists,
            'positional': positional, 
            'optional': optional , 
            'tail': tail, 
            'argtypes': argtypes,
    }


class wire:
    class Result:
        def __init__(self, exit_code, value):
            self.exit_code = exit_code
            self.value = value
            
    class Action:
        def __init__(self, mode, command, argv, errors=()):
            self.mode = mode
            self.path = command
            self.argv = argv
            self.errors = errors

    class Command:
        def __init__(self, prefix, name, subcommands, short, long, options):
            self.prefix = prefix
            self.name = name
            self.subcommands = subcommands
            self.short, self.long = short, long
            self.options = options


        def invoke(self, path,argv, environ):
            if argv and argv[0] == "help":
                action = self.invoke(path, argv[1:], environ)
                return wire.Action("help", action.path, {'manual': True})
            if argv and argv[0] in self.subcommands:
                return self.subcommands[argv[0]].invoke(path+[argv[0]], argv[1:], environ)

            options = []
            flags = {}
            args = {}

            for arg in argv:
                if arg.startswith('--'):
                    if '=' in arg:
                        key, value = arg[2:].split('=',1)
                    else:
                        key, value = arg[2:], None
                    if key not in flags:
                        flags[key] = []
                    flags[key].append(value)
                else:
                    options.append(arg)

            if 'help' in flags:
                return wire.Action("help", path, {'usage':True})

            if not self.options:
                return wire.Action("help", path, {'usage':True})

            for name in self.options['switches']:
                args[name] = False
                if name not in flags:
                    continue

                key, values = name, flags.pop(name)
                if not values or values[0] is not None:
                    return wire.Action("error", path, {'usage':True}, errors=("value given for switch flag {}".format(key),))
                if len(values) > 1:
                    return wire.Action("error", path, {'usage':True}, errors=("duplicate switch flag for: {}".format(key, ", ".join(repr(v) for v in values)),))

                args[key] = True

            for name in self.options['flags']:
                args[name] = None
                if name not in flags:
                    continue

                key, values = name, flags.pop(name)
                if not values or values[0] is None:
                    return wire.Action("error", path, {'usage':True}, errors=("missing value for option flag {}".format(key),))
                if len(values) > 1:
                    return wire.Action("error", path, {'usage':True}, errors=("duplicate option flag for: {}".format(key, ", ".join(repr(v) for v in values)),))

                args[key] = try_parse(value, self.options['argtypes'].get(key))

            for name in self.options['lists']:
                args[name] = []
                if name not in flags:
                    continue

                key, values = name, flags.pop(name)
                if not values or None in values:
                    return wire.Action("error", path, {'usage':True}, errors=("missing value for list flag {}".format(key),))

                for v in values:
                    args[key].append(try_parse(value, self.options['argtypes'].get(name)))

            named_args = False
            if flags:
                for name in self.options['positional']:
                    if name in flags:
                        named_args = True
                        break
                for name in self.options['optional']:
                    if name in flags:
                        named_args = True
                        break
                if self.options['tail'] in flags:
                    named_args = True
                        
            if named_args:
                for name in self.options['positional']:
                    args[name] = None
                    if name not in flags:
                        return wire.Action("error", path, {'usage':'True'}, errors=("missing named option: {}".format(name),))

                    key, values = name, flags.pop(name)
                    if not values or values[0] is None:
                        return wire.Action("error", path, {'usage':True}, errors=("missing value for named option {}".format(key),))
                    if len(values) > 1:
                        return wire.Action("error", path, {'usage':True}, errors=("duplicate named option for: {}".format(key, ", ".join(repr(v) for v in values)),))

                    args[key] = try_parse(value, self.options['argtypes'].get(key))

                for name in self.options['optional']:
                    args[name] = None
                    if name not in flags:
                        continue

                    key, values = name, flags.pop(name)
                    if not values or values[0] is None:
                        return wire.Action("error", path, {'usage':True}, errors=("missing value for named option {}".format(key),))
                    if len(values) > 1:
                        return wire.Action("error", path, {'usage':True}, errors=("duplicate named option for: {}".format(key, ", ".join(repr(v) for v in values)),))

                    args[key] = try_parse(value, self.options['argtypes'].get(key))

                name = self.options['tail']
                if name and name in flags:
                    args[name] = []

                    key, values = name, flags.pop(name)
                    if not values or None in values:
                        return wire.Action("error", path, {'usage':True}, errors=("missing value for named option  {}".format(key),))

                    for v in values:
                        args[key].append(try_parse(value, self.options['argtypes'].get(name)))
                

            else:
                if self.options['positional']:
                    for name in self.options['positional']:
                        if not options: 
                            return wire.Action("error", path, {'usage':'True'}, errors=("missing option: {}".format(name),))

                        args[name] = try_parse(options.pop(0),self.options['argtypes'].get(name))

                if self.options['optional']:
                    for name in self.options['optional']:
                        if not options: 
                            args[name] = None
                        else:
                            args[name] = try_parse(options.pop(0), self.options['argtypes'].get(name))

                if self.options['tail']:
                    tail = []
                    name = self.options['tail']
                    tailtype = self.options['argtypes'].get(name)
                    while options:
                        tail.append(try_parse(options.pop(0), tailtype))

                    args[name] = tail

            if flags:
                return wire.Action("error", path, {'usage': True}, errors=("unknown option flags: --{}".format("".join(flags)),))

            if options and named_args:
                return wire.Action("error", path, {'usage':True}, errors=("unnamed options given {!r}".format(" ".join(options)),))
            if options:
                return wire.Action("error", path, {'usage':True}, errors=("unrecognised option: {!r}".format(" ".join(options)),))
            return wire.Action("call", path, args)

        def help(self, path, *, usage=False):
            if path and path[0] in self.subcommands:
                return self.subcommands[path[0]].help(path[1:], usage=usage)
            else:
                if usage:
                    return self.usage()
                return self.manual()
            
        def manual(self):
            output = []
            full_name = list(self.prefix)
            full_name.append(self.name)
            output.append("{}{}{}".format(" ".join(full_name), (" - " if self.short else ""), self.short))

            output.append("")

            output.append(self.usage())
            output.append("")

            if self.long:
                output.append('description:')
                output.append(self.long)
                output.append("")

            if self.subcommands:
                output.append("commands:")
                for cmd in self.subcommands.values():
                    output.append("\t{.name}\t{}".format(cmd, cmd.short))
                output.append("")
            return "\n".join(output)

        def usage(self):
            args = []
            if self.subcommands:
                args.append('<command>')
            if self.options:
                if self.options['switches']:
                    args.extend("[--{0}]".format(o) for o in self.options['switches'])
                if self.options['flags']:
                    args.extend("[--{0}=<{0}>]".format(o) for o in self.options['flags'])
                if self.options['lists']:
                    args.extend("[--{0}=<{0}>...]".format(o) for o in self.options['lists'])
                if self.options['positional']:
                    args.extend("<{}>".format(o) for o in self.options['positional'])
                if self.options['optional']:
                    args.extend("[<{}>]".format(o) for o in self.options['optional'])
                if self.options['tail']:
                    args.append("[<{}>...]".format(self.options['tail']))

            full_name = list(self.prefix)
            full_name.append(self.name)
            return "usage: {} {}".format(" ".join(full_name), " ".join(args))


class cli:
    class Command:
        def __init__(self, name, short):
            self.name = name
            self.prefix = [] 
            self.subcommands = {}
            self.run_fn = None
            self.short = short
            self.options = None
            self.nargs = 0

        def subcommand(self, name, short):
            cmd = cli.Command(name, short)
            cmd.prefix.extend(self.prefix)
            cmd.prefix.append(self.name)
            self.subcommands[name] = cmd
            return cmd

        def call(self, path, argv):
            if path and path[0] == 'help':
                return self.help(path[1:])
            elif path and path[0] in self.subcommands:
                return self.subcommands[path[0]].call(path[1:], argv)
            elif self.run_fn:
                if len(argv) == self.nargs:
                    return self.run_fn({}, **argv)
                else:
                    return wire.Result(-1, "bad options")
            else:
                if len(argv) == 0:
                    return self.render().manual()
                else:
                    return wire.Result(-1, self.render.usage())

        def run(self, argspec=None):
            if argspec is not None:
                self.nargs, self.options = parse_argspec(argspec)

            def decorator(fn):
                self.run_fn = fn

                args = list(self.run_fn.__code__.co_varnames[:self.run_fn.__code__.co_argcount])
                if args and args[0] == 'context':
                    args.pop(0)
                args = [a for a in args if not a.startswith('_')]
                
                if not self.options:
                    self.options = {'positional': args, 'optional': [] , 'tail': None, 'flags': []}
                    self.nargs = len(args)
                else:
                    if self.nargs != len(args):
                        raise Exception('bad option definition')

                return fn
            return decorator

        def render(self):
            long_description =self.run_fn.__doc__ if self.run_fn else None
            return wire.Command(
                name = self.name,
                prefix = self.prefix,
                subcommands = {k: v.render() for k,v in self.subcommands.items()},
                short = self.short,
                long = long_description,
                options = self.options, 
            )
                
    #end Command

    def main(root):
        argv = sys.argv[1:]
        environ = os.environ

        obj = root.render()

        action = obj.invoke([], argv, environ)
    
        if action.mode == "help":
            result = obj.help(action.path, usage=action.argv.get('usage'))
        elif action.mode == "error":
            print("error: {}".format(", ".join(action.errors)))
            result = obj.help(action.path, usage=action.argv.get('usage'))
        elif action.mode == "call":
            result = root.call(action.path, action.argv)

        if isinstance(result, wire.Result):
            exit_code = result.exit_code
            result = result.value
        else:
            exit_code = -len(action.errors)

        if isinstance(result, types.GeneratorType):
            for r in result:
                print(r)
        else:
            print(result)

        sys.exit(exit_code)

root = cli.Command('example', 'cli example programs')

nop = root.subcommand('nop', 'nothing')

add = root.subcommand('add', "adds two numbers")

@add.run("a b")
def add_cmd(context, a, b):
    return a+b

echo = root.subcommand('echo', "echo")
@echo.run("--reverse? line:str...")
def echocmd(context, line, reverse):
    """echo all arguments"""
    if reverse:
        return (" ".join(x for x in line))[::-1]
    return " ".join(x for x in line)

ev = root.subcommand('cat', "line at a time echo")
@ev.run()
async def eval_cmd(context):
    async for msg in context.stdin():
        await context.stdout.write(msg)

demo = root.subcommand('demo', "demo of argspec")
@demo.run('--switch? --value --bucket... pos1 opt1? opt2? tail...')
def run(context, switch, value, bucket, pos1, opt1, opt2, tail):
    output = [ 
            "\tswitch:{}".format(switch),
            "\tvalue:{}".format(value),
            "\tbucket:{}".format(bucket),
            "\tpos1:{}".format(pos1),
            "\topt1:{}".format(opt1),
            "\topt2:{}".format(opt2),
            "\ttail:{}".format(tail),
    ]
    return "\n".join(output)
if __name__ == '__main__':
    cli.main(root)
