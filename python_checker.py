import os
import re
from subprocess import Popen, PIPE

import sublime
import sublime_plugin


DEFAULT_CHECKERS = [
        [
            "/usr/bin/pep8",
            [
                "--ignore="
            ],
            False,
            "keyword.python_checker.outline"
        ],
        [
            "/usr/bin/pyflakes",
            [
            ],
            True,
            "invalid.python_checker.outline"
        ]
    ]

try:
    from local_settings import CHECKERS
except ImportError as e:
    print ('''
Please create file local_settings.py in the same directory with
python_checker.py. Add to local_settings.py list of your checkers.

Example:

CHECKERS = [('/Users/vorushin/.virtualenvs/checkers/bin/pep8', []),
            ('/Users/vorushin/.virtualenvs/checkers/bin/pyflakes', [])]

First parameter is path to command, second - optional list of arguments.
If you want to disable line length checking in pep8, set second parameter
to ['--ignore=E501'].

You can also insert checkers using sublime settings.

For example in your project settings, add:
    "settings":
    {
        "python_syntax_checkers":
        [
            ["/usr/bin/pep8", ["--ignore=E501,E128,E221"] ],
            ["/usr/bin/pyflakes", [] ]
        ]
    }
''')


global view_messages
global view_lines
global view_totals
view_messages = {}
view_lines = {}
view_totals = {}


class PythonCheckerCommand(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        check_and_mark(view)

    def on_modified_async(self, view):
        check_and_mark(view, True)

    def on_post_save_async(self, view):
        check_and_mark(view)

    def on_close(self, view):
        global view_messages
        view_messages[view.id()].clear()
        del view_messages[view.id()]
        del view_lines[view.id()]
        view.erase_status('python_checker')

    def on_selection_modified(self, view):
        global view_messages
        lineno = view.rowcol(view.sel()[0].end())[0]
        _message = ''
        if view.id() in view_lines and lineno in view_lines[view.id()]:
            for basename, basename_lines in view_messages[view.id()].items():
                if lineno in basename_lines:
                    _message += (basename_lines[lineno]).decode('utf-8') + ';'
        if _message or view_totals.get(view.id(), ''):
            view.set_status('python_checker', '{} ({} )'.format(_message, view_totals.get(view.id(), '')))
        else:
            view.set_status('python_checker', 'OK')


def check_and_mark(view, is_buffer=False):
    if not 'python' in view.settings().get('syntax').lower():
        return
    if not view.file_name() and not is_buffer:
        return

    checkers = view.settings().get('python_syntax_checkers', [])
    checkers_basenames = [
        os.path.basename(checker[0]) for checker in checkers]

    # TODO: improve settings and default handling
    # TODO: just use the checkers in path
    if 'CHECKERS' in globals():
        checkers.extend([checker for checker in CHECKERS
            if os.path.basename(checker[0]) not in checkers_basenames])
    checkers_basenames = [
        os.path.basename(checker[0]) for checker in checkers]
    checkers.extend([checker for checker in DEFAULT_CHECKERS
            if os.path.basename(checker[0]) not in checkers_basenames])

    line_messages = {}
    for checker, args, run_in_buffer, checker_scope in checkers:
        checker_messages = []
        line_messages = {}
        if not is_buffer or is_buffer and run_in_buffer:
            try:
                if not is_buffer:
                    p = Popen([checker, view.file_name()] + args, stdout=PIPE,
                    stderr=PIPE)
                    stdout, stderr = p.communicate(None)
                else:
                    p = Popen([checker] + args, stdin=PIPE, stdout=PIPE,
                    stderr=PIPE)
                    stdout, stderr = p.communicate(bytes(view.substr(sublime.Region(0, view.size())), 'utf-8'))
                checker_messages += parse_messages(stdout)
                checker_messages += parse_messages(stderr)
            except OSError:
                print ("Checker could not be found:", checker)
            except Exception as e:
                print ("Generic error while running checker:", e)
            else:
                basename = os.path.basename(checker)
                outline_name = 'python_checker_outlines_{}'.format(basename)
                print("outline name {}".format(outline_name))
                underline_name = 'python_checker_underlines_{}'.format(basename)
                outline_scope = checker_scope
                outlines = []
                underlines = []
                for m in checker_messages:
                    print ("[%s] %s:%s:%s %s" % (
                        checker.split('/')[-1], view.file_name(),
                        m['lineno'] + 1, m['col'] + 1, m['text']))
                    outlines.append(view.full_line(view.text_point(m['lineno'], 0)))
                    if m['col']:
                        a = view.text_point(m['lineno'], m['col'])
                        underlines.append(sublime.Region(a, a))
                    if m['text']:
                        if m['lineno'] in line_messages:
                            line_messages[m['lineno']] += b';' + m['text']
                        else:
                            line_messages[m['lineno']] = m['text']
                view.erase_regions(outline_name)
                view.add_regions(outline_name, outlines, outline_scope,
                    icon='circle',
                    flags=sublime.DRAW_EMPTY | sublime.DRAW_OUTLINED)
                view.erase_regions(underline_name)
                view.add_regions(underline_name, underlines,
                    'keyword.python_checker.underline', flags=
                    sublime.DRAW_EMPTY_AS_OVERWRITE | sublime.DRAW_OUTLINED)
                checker_messages.clear()
                add_messages(view.id(), basename, line_messages)


def add_messages(view_id, basename, basename_lines):
    global view_messages
    global view_lines
    global view_totals
    if view_id not in view_messages:
        view_messages[view_id] = {}
    view_messages[view_id][basename] = basename_lines
    lines = set()
    view_totals[view_id] = ''
    for basename, basename_lines in view_messages[view_id].items():
        lines.update(basename_lines.keys())
        if basename_lines.keys():
            view_totals[view_id] += ' {}:{}'.format(basename, len(basename_lines.keys()))

    view_lines[view_id] = lines


def parse_messages(checker_output):
    '''
    Examples of lines in checker_output

    pep8 on *nix
    /Users/vorushin/Python/answers/urls.py:24:80: E501 line too long \
    (96 characters)

    pyflakes on *nix
    /Users/vorushin/Python/answers/urls.py:4: 'from django.conf.urls.defaults \
    import *' used; unable to detect undefined names

    pyflakes, invalid syntax message (3 lines)
    /Users/vorushin/Python/answers/urls.py:14: invalid syntax
    dict_test = {key: value for (key, value) in [('one', 1), ('two': 2)]}
                                                                    ^

    pyflakes on Windows
    c:\Python26\Scripts\pildriver.py:208: 'ImageFilter' imported but unused
    '''

    pep8_re = re.compile(b'.*:(\d+):(\d+):\s+(.*)')
    pyflakes_re = re.compile(b'.*:(\d+):\s+(.*)')

    messages = []
    for i, line in enumerate(checker_output.splitlines()):
        if pep8_re.match(line):
            lineno, col, text = pep8_re.match(line).groups()
        elif pyflakes_re.match(line):
            lineno, text = pyflakes_re.match(line).groups()
            col = 1
            if text == 'invalid syntax':
                col = invalid_syntax_col(checker_output, i)
        else:
            continue
        messages.append({'lineno': int(lineno) - 1,
                         'col': int(col) - 1,
                         'text': text,
                         })

    return messages


def invalid_syntax_col(checker_output, line_index):
    '''
    For error messages like this:

    /Users/vorushin/Python/answers/urls.py:14: invalid syntax
    dict_test = {key: value for (key, value) in [('one', 1), ('two': 2)]}
                                                                    ^
    '''
    for line in checker_output.splitlines()[line_index + 1:]:
        if line.startswith(' ') and line.find('^') != -1:
            return line.find('^')
