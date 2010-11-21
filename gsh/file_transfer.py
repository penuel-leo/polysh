# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# See the COPYING file for license information.
#
# Copyright (c) 2007, 2008 Guillaume Chazarain <guichaz@gmail.com>

import base64
import os
import random
import zipimport

from gsh import callbacks
from gsh import pity
from gsh.console import console_output
from gsh import remote_dispatcher
from gsh import dispatchers

CMD_PREFIX = 'python -c "`echo "%s"|tr , \\\\\\n|openssl base64 -d`" '

CMD_SEND = CMD_PREFIX + 'send "%s" "%s" "%s"\n'
CMD_FORWARD = CMD_PREFIX + 'forward "%s" "%s"\n'
CMD_RECEIVE = CMD_PREFIX + 'receive "%s" "%s"\n'

def pity_dot_py_source():
    path = pity.__file__
    if not os.path.exists(path):
      try:
        zip_importer = zipimport.zipimporter(os.path.dirname(path))
      except Exception:
        return
      return zip_importer.get_source('pity')
    if not path.endswith('.py'):
        # Read from the .py source file
        dot_py_start = path.find('.py')
        if dot_py_start >= 0:
            path = path[:dot_py_start+3]

    return file(path).read()

def base64version():
    python_lines = []
    for line in pity_dot_py_source().splitlines():
        hash_pos = line.find('#')
        if hash_pos >= 0:
            line = line[:hash_pos]
        line = line.rstrip()
        if line:
            python_lines.append(line)
    python_source = '\n'.join(python_lines)
    encoded = base64.encodestring(python_source).rstrip('\n').replace('\n', ',')
    return encoded

BASE64_PITY_PY = base64version()

def file_transfer_cb(dispatcher, host_port):
    previous_shell = get_previous_shell(dispatcher)
    previous_shell.dispatch_write(pity.STDIN_PREFIX + host_port + '\n')

def get_previous_shell(shell):
    shells = [i for i in dispatchers.all_instances() if i.enabled]
    current_pos = shells.index(shell)
    while True:
        current_pos = (current_pos - 1) % len(shells)
        prev_shell = shells[current_pos]
        if prev_shell.enabled:
            return prev_shell

def replicate(shell, path):
    nr_peers = len([i for i in dispatchers.all_instances() if i.enabled])
    if nr_peers <= 1:
        console_output('No other remote shell to replicate files to\n')
        return
    receiver = get_previous_shell(shell)
    pity_py = BASE64_PITY_PY
    for i in dispatchers.all_instances():
        if not i.enabled:
            continue
        cb = lambda host_port, i=i: file_transfer_cb(i, host_port)
        transfer1, transfer2 = callbacks.add('file transfer', cb, False)
        if i == shell:
            i.dispatch_command(CMD_SEND % (pity_py, path, transfer1, transfer2))
        elif i != receiver:
            i.dispatch_command(CMD_FORWARD % (pity_py, transfer1, transfer2))
        else:
            i.dispatch_command(CMD_RECEIVE % (pity_py, transfer1, transfer2))
        i.change_state(remote_dispatcher.STATE_RUNNING)

class local_uploader(remote_dispatcher.remote_dispatcher):
    def __init__(self, path_to_upload):
        remote_dispatcher.remote_dispatcher.__init__(self, '.')
        self.path_to_upload = path_to_upload
        self.upload_started = False

    def launch_ssh(self, name):
        os.execl('/bin/bash', 'bash')

    def change_state(self, state):
        remote_dispatcher.remote_dispatcher.change_state(self, state)
        if state != remote_dispatcher.STATE_IDLE:
            return

        if not self.upload_started:
            replicate(self, self.path_to_upload)
            self.upload_started = True
        else:
            self.disconnect()
            self.close()

def upload(local_path):
    local_shell = local_uploader(local_path)

