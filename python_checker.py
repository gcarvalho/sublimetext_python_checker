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
        ],
        [
            "/usr/local/bin/pylint",
            [
                "-fparseable",
                "-iy",
                "-d C0301,C0302,C0111,C0103,R0911,R0912,R0913,R0914,R0915,W0142"
            ],
            False,
            "comment.python_checker.outline"
        ],
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


VIEW_MESSAGES = {}
VIEW_LINES = {}
VIEW_TOTALS = {}


class PythonCheckerCommand(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        if view.id() not in VIEW_LINES:  # TODO use change_count()
            check_and_mark(view)

    def on_modified_async(self, view):
        if view.id() in VIEW_LINES:
            del VIEW_LINES[view.id()]
        check_and_mark(view, True)

    def on_post_save_async(self, view):
        check_and_mark(view)

    def on_close(self, view):
        if view.id() in VIEW_MESSAGES:
            VIEW_MESSAGES[view.id()].clear()
            del VIEW_MESSAGES[view.id()]
            del VIEW_LINES[view.id()]
        view.erase_status('python_checker')

    def on_selection_modified(self, view):
        lineno = view.rowcol(view.sel()[0].begin())[0]
        _message = ''
        if view.id() in VIEW_LINES and lineno in VIEW_LINES[view.id()]:
            for _, basename_lines in VIEW_MESSAGES[view.id()].items():
                if lineno in basename_lines:
                    _message += (basename_lines[lineno]).decode('utf-8') + ';'
        if _message or VIEW_TOTALS.get(view.id(), ''):
            view.set_status('python_checker', '{} ({} )'.format(_message, VIEW_TOTALS.get(view.id(), '')))
        else:
            view.set_status('python_checker', 'OK')


def check_and_mark(view, is_buffer=False):
    if view.settings().get('syntax', None) and \
        not 'python' in view.settings().get('syntax', '').lower():
        return
    if not view.file_name() and not is_buffer:
        return
    mesg_quick = '' if is_buffer else '(everything)'
    view.set_status('python_checker_running', 'Checking Python {}...'.format(mesg_quick))
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
                    params = [checker, view.file_name()]
                    for arg in args:
                        params.insert(1, arg)
                    p = Popen(params, stdout=PIPE,
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
                underline_name = 'python_checker_underlines_{}'.format(basename)
                outline_scope = checker_scope
                outlines = []
                underlines = []
                for m in checker_messages:
                    # print ("[%s] %s:%s:%s %s" % (
                    #     checker.split('/')[-1], view.file_name(),
                    #     m['lineno'] + 1, m['col'] + 1, m['text']))
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
    view.erase_status('python_checker_running')


def add_messages(view_id, basename, basename_lines):
    if view_id not in VIEW_MESSAGES:
        VIEW_MESSAGES[view_id] = {}
    VIEW_MESSAGES[view_id][basename] = basename_lines
    lines = set()
    VIEW_TOTALS[view_id] = ''
    for basename, basename_lines in VIEW_MESSAGES[view_id].items():
        lines.update(basename_lines.keys())
        if basename_lines.keys():
            VIEW_TOTALS[view_id] += ' {}:{}'.format(basename, len(basename_lines.keys()))

    if lines:
        VIEW_LINES[view_id] = lines
    else:
        VIEW_LINES[view_id] = 'OK'


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
