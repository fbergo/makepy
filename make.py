#!/usr/bin/python3

import os
import re
import shutil
import sys
import argparse

# verbose/debug
verbose     = False
parse_debug = False

items   = []
vardict = {}
origdir = ''

# make items

class MakeItem:
    location = ''

    def __init__(self, location):
        self.location = location

    def allows_commands(self):
        return False
    
    def sub(self, str):
        while True:
            m=re.search(r'(\$\((\w+)\))', str, re.ASCII)
            if m == None:
                return str
            tosub = m.group(1)
            key = m.group(2)
            use = None
            if key in vardict:
                use = vardict[key]
            elif key in os.environ:
                use = os.environ[key]
            else:
                print("** Error: undefined variable " + key + " at " + self.location)
                make_exit(3)
            oldval = str
            str = str.replace(tosub, use)
            if parse_debug:
                print("#sub: " + key + " => " + use)
                print("  "+ oldval + " => " + str)

    def expr_eval(self, expr):
        ret = False
        v1  = None
        v2  = None
        op  = None
        # numeric value
        m = re.search(r'^(\d+)$', expr, re.ASCII)
        if m != None:
            v1 = m.group(1)            
            if int(m.group(1)) != 0:
                ret = True
            else:
                ret = False
        else:
            # v1 op v2
            m = re.search(r'^(\d+)\s*([=!<>]+)\s*(\d+)$', expr, re.ASCII)
            if m != None:
                v1 = int(m.group(1))
                v2 = int(m.group(3))
                op = m.group(2)
            else:
                m = re.search(r'^(\w+)\s*([=!]+)\s*(\w+)$', expr, re.ASCII)
                if m != None:
                    v1 = m.group(1)
                    v2 = m.group(3)
                    op = m.group(2)
                else:
                    m = re.search(r'^"(.*)"\s*([=!]+)\s*"(.*)"$', expr, re.ASCII)
                    if m != None:
                        v1 = m.group(1)
                        v2 = m.group(3)
                        op = m.group(2)
            if v1 == None:
                print("** Error: unable to evaluate expression " + expr + " at " + self.location)
                make_exit(3)
            else:
                if op == "==":
                    ret = v1 == v2
                elif op == "!=":
                    ret = v1 != v2
                elif op == "<":
                    ret = v1 < v2
                elif op == "<=":
                    ret = v1 <= v2
                elif op == ">":
                    ret = v1 > v2
                elif op == ">=":
                    ret = v1 >= v2
                else:
                    print("** Error: unsupported operator " + op + " at " + self.location)
                    make_exit(3)
        if parse_debug:
            print("#expr_eval: expr= " + expr)
            print("  v1=" + repr(v1) + " v2=" + repr(v2) + " op=" + repr(op) + " result=" + repr(ret))
        return ret
                
    def describe(self):
        return("MakeItem" + self.location)
    
class MakeEmpty:
    def __init__(self, location):
        self.location = location

    def describe(self):
        return("MakeEmpty" + self.location)

class MakeAssign(MakeItem):
    name  = ''
    value = ''

    def __init__(self, location, name, value):
        super().__init__(location)
        self.name  = name
        self.value = value

    def eval(self):
        global vardict
        self.value = self.sub(self.value)
        vardict[self.name] = self.value
        if parse_debug:
            print("#Assign.eval: " + self.name + " = " + self.value)
        return True

    def describe(self):
        return("MakeAssign" + self.location + " name=" + self.name + " value=" + self.value)

# if, else, elif, endif, ifdef, ifndef
class MakeConditional(MakeItem):
    macro     = ''
    condition = ''

    def __init__(self, location, macro, condition=''):
        super().__init__(location)
        self.macro = macro
        self.condition = condition

    def eval(self):
        self.condition = self.sub(self.condition)

        if self.macro in ['ifdef', 'ifndef']:
            ret = False
            self.condition = self.condition.lstrip().rstrip()
            if self.condition in os.environ or self.condition in vardict:
                ret = True
            if self.macro == 'ifndef':
                ret = not ret
            return ret
        elif self.macro in ['if', 'elif']:
            ret = False
            self.condition = self.condition.lstrip().rstrip()
            self.condition = self.sub(self.condition)
            ret = self.expr_eval(self.condition)
            return ret              
        else:
            return True

    def describe(self):
        return("MakeConditional" + self.location + " macro=" + self.macro + " condition=" + self.condition)

class MakeExplicit(MakeItem):
    name  = ''
    deps  = []
    cmds  = []

    def __init__(self, location, name):
        super().__init__(location)
        self.name  = name
        self.deps = []
        self.cmds = []

    def allows_commands(self):
        return True   

    def eval(self):
        self.name = self.sub(self.name)
        for idx, c in enumerate(self.deps):
            self.deps[idx] = self.sub(c)
        for idx, c in enumerate(self.cmds):
            self.cmds[idx] = self.sub(c)
        return True

    def describe(self):
        d = "MakeExplicit" + self.location + " name=" + self.name + " deps=" + ",".join(self.deps) + "\n"
        for c in self.cmds:
            d += "==> " + c + "\n"
        return d[:-1]
    
class MakeImplicit(MakeItem):
    source = ""
    dest   = ""
    cmds = []

    def __init__(self, location, source, dest):
        super().__init__(location)
        self.source = source
        self.dest   = dest

    def allows_commands(self):
        return True
    
    def eval(self):
        for idx, c in enumerate(self.cmds):
            self.cmds[idx] = self.sub(c)
        return True

    def describe(self):
        d = "MakeImplicit" + self.location + " source=" + self.source + " dest=" + self.dest + "\n"
        for c in self.cmds:
            d += "==> " + c + "\n"
        return d[:-1]

def push_empty(location):
    if not items or not isinstance(items[-1], MakeEmpty):
        items.append(MakeEmpty(location))

def parse_line(line, filename, num):
    fileloc = "[" + filename + ":" + repr(num) + "]"
    if parse_debug:
        print("#PL line=" + line + " " + fileloc)
    if len(line) == 0:
        if parse_debug:
            print("#PL.EMPTY")
            push_empty(fileloc)
        return True
    if line[:1] == "#":
        if parse_debug:
            print("#PL.COMMENT")
        return True
    
    # include
    m = re.search(r'^!include\s+"(.*)"$', line)
    if m != None:
        incfile = m.group(1)
        if parse_debug:
            print("#PL.INCLUDE " + incfile)
        if not parse_file(incfile):
            print("** Error: include " + incfile + " failed at " + fileloc)
            return False
        return True
    
    # assignment
    m = re.search(r'^([A-Za-z0-9_]+)\s*=\s*(\S+.*)\s*$', line, re.ASCII)
    if m != None:
        mi = MakeAssign(fileloc, m.group(1), m.group(2))
        if parse_debug:
            print("#PL.ASSIGN var=" + mi.name + " value=" + mi.value)
        items.append(mi)
        return True
    
    # implicit rule
    m = re.search(r'^\.(\S+)\.(\S+):\s*$', line, re.ASCII)
    if m != None:
        mi = MakeImplicit(fileloc, m.group(1), m.group(2))
        if parse_debug:
            print("#PL.IMPLICIT src=" + mi.source + " dest=" + mi.dest)
        items.append(mi)
        return True

    # explicit rule
    m = re.search(r'^(\S+)\s*:\s+(\S+.*)\s*$', line, re.ASCII)
    if m != None:
        mi = MakeExplicit(fileloc, m.group(1))
        mi.deps = m.group(2).split()
        if parse_debug:
            print("#PL.EXPLICIT name=" + mi.name + " deps=" + ",".join(mi.deps))
        items.append(mi)
        return True

    # explicit rule, no deps
    m = re.search(r'^(\S+)\s*:\s*$', line, re.ASCII)
    if m != None:
        mi = MakeExplicit(fileloc, m.group(1))
        if parse_debug:
            print("#PL.EXPLICIT name=" + mi.name + " deps=" + ",".join(mi.deps))
        items.append(mi)
        return True

    # conditional
    m = re.search(r'^!(\w+)\s+(\S+.*)\s*$', line, re.ASCII)
    if m != None:
        macro = m.group(1)
        cond  = m.group(2)
        if macro in ['if','elif','ifdef','ifndef']:
            mi = MakeConditional(fileloc, macro, cond)
        if parse_debug:
            print("#PL.CONDITIONAL macro=" + mi.macro + " condition=" + mi.condition)
        items.append(mi)
        return True

    # conditional without args
    m = re.search(r'^!(\w+)\s*$', line, re.ASCII)
    if m != None:
        macro = m.group(1)
        if macro in ['endif','else']:
            mi = MakeConditional(fileloc, macro)
        if parse_debug:
            print("#PL.CONDITIONAL macro=" + mi.macro)
        items.append(mi)
        return True

    # command in a command list
    m = re.search(r'^[ \t]+(.*)$', line, re.ASCII)
    if m != None:
        if not items or not items[-1].allows_commands():
            print("** Error: preceding command does not allow command list at " + fileloc)
            return False
        items[-1].cmds.append(m.group(1))
        if parse_debug:
            print("#PL.CMD: appended " + m.group(1))
        return True

    print("** Error: invalid line: " + line + " at " + fileloc)
    return False
    
def make_exit(code):
    if verbose:
        print("Restoring working directory to " + origdir)
    os.chdir(origdir)
    sys.exit(code)

def parse_file(filename):
    try:
        tname = filename
        if not os.path.isfile(tname):
            if ('\\' in tname):
                tname = re.sub(r'\\','/',filename)
                if os.path.exists(tname):
                    filename = tname
        with open(filename) as file:
            lines = [line.rstrip().lstrip("\r\n") for line in file]
    except IOError:
        print("** Error: Unable to read " + filename)
        return False

    cont = False
    mline = ''
    mnum  = 0

    if parse_debug:
        print("#PF.START filename=" + filename + " lines=" + repr(len(lines)))

    for num, line in enumerate(lines):
        if parse_debug:
            print("line " + repr(num+1) + ": " + line)
        if len(line)!=0 and line[0] == '#':
            continue
        if not cont:
            mnum = num
            mline = ''
        else:
            line = line.lstrip()            
        if line[-1:] == '\\' and line[0] != '#':
            if parse_debug:
                print("#PF.MULTILINE")
            cont = True
            if len(mline) != 0:
                mline += " "
            mline += line[:-1].rstrip()
            continue
        fileloc = "[" + filename + ":" + repr(mnum+1) + "]"
        if cont:
            if parse_debug:
                print("#PF.MULTILINE END")
            cont = False
            if len(mline) != 0:
                mline += " "
            mline += line
            if not parse_line(mline, filename, mnum+1):
                print("** Error: parse_line failed at " + fileloc)
                return False
        else:
            if not parse_line(line, filename, mnum+1):
                print("** Error: parse_line failed at " + fileloc)
                return False
    return True
        
# 1. interpret assignments
# 2. substitute variables
# 3. treat conditionals
# 4. remove empty nodes

def make_pass():
    global items
    SKIP    = 1
    EXEC    = 2
    SKIPALL = 3

    post = []
    condstack = []
    sitstack  = []

    # group 1: if, ifdef, ifndef
    # group 2: elif, else, endif

    for mi in items:
        sit = EXEC
        if sitstack:
            sit = sitstack[-1]

        #print("sit=" + repr(sit))
        #print(mi.describe())

        if isinstance(mi, MakeEmpty):
            continue
        elif isinstance(mi, MakeConditional):
            if mi.macro in ['if','ifdef','ifndef']:
                condstack.append(mi)
                if sit == EXEC:
                    ret = mi.eval()
                    if ret:
                        sitstack.append(EXEC)
                    else:
                        sitstack.append(SKIP)
                else:
                    sitstack.append(SKIPALL)
            elif mi.macro == 'elif':
                if not condstack:
                    print("** Error: mismatched !elif at " + mi.location)
                    make_exit(3)
                if sit == EXEC:
                    sitstack[-1] = SKIPALL
                elif sit == SKIP:
                    ret = mi.eval()
                    if ret:
                        sitstack[-1] = EXEC
            elif mi.macro == 'else':
                if not condstack:
                    print("** Error: mismatched !else at " + mi.location)
                    make_exit(3)
                if sit == EXEC:
                    sitstack[-1] = SKIP
                elif sit == SKIP:
                    sitstack[-1] = EXEC
            elif mi.macro == 'endif':
                if not condstack:
                    print("** Error: mismatched !endif at " + mi.location)
                    make_exit(3)
                condstack = condstack[:-1]
                sitstack = sitstack[:-1]
            else:
                print("** Error: unsupported macro " + mi.macro + " at " + mi.location)
                make_exit(3)
            continue
        elif isinstance(mi, MakeAssign) and sit==EXEC:
            mi.eval()
            post.append(mi)
            continue
        elif isinstance(mi, MakeImplicit) and sit==EXEC:
            mi.eval()
            post.append(mi)
            continue
        elif isinstance(mi, MakeExplicit) and sit==EXEC:
            mi.eval()
            post.append(mi)
            continue
        else:
            post.append(mi)

    items = post
    return True

# main

parser = argparse.ArgumentParser(prog='make.py',
                                 description='python-based Make tool',
                                 epilog='Felipe Bergo, 2024')
parser.add_argument('target', default='', nargs='*')
parser.add_argument('-f', dest='makefile', metavar='file', help='use file as Makefile',     default='Makefile', required=False)
parser.add_argument('-v', dest='verbose', help='verbose', required=False, action='store_true')
parser.add_argument('-vp', dest='parsedebug', help='verbose: parser debug', required=False, action='store_true')
parser.add_argument('-D', dest='workdir', metavar='dir', help='use dir as working directory', required=False)

args = parser.parse_args()

verbose     = args.verbose
parse_debug = args.parsedebug
origdir = os.path.abspath(os.getcwd())
newdir = ''

if args.workdir != None:
    newdir = os.path.abspath(args.workdir)
    if verbose:
        print("Changing working directory to " + newdir)
    os.chdir(newdir)

if verbose:
    print(args)

items.append(MakeEmpty("[none]"))
if not parse_file(args.makefile):
    if parse_debug:
        for i in items:
            print(i.describe())
    make_exit(2)

if parse_debug:
    print("*********************")
    print("** Step 1 Complete **")
    print("*********************")
    for i in items:
        print(i.describe())

# second pass
make_pass()

if parse_debug:
    print("*********************")
    print("** Step 2 Complete **")
    print("*********************")
    for i in items:
        print(i.describe())

make_exit(0)