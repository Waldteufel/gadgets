# buffer manager

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import weechat
from collections import defaultdict

weechat.register('bufmgr', 'Benjamin Richter <br@waldteufel.eu>', '0.2', 'GPL3', 'buffer manager', '', '')
weechat.hook_signal('hotlist_changed', 'hotlist_changed_hook', '')
weechat.hook_signal('buffer_opened', 'sort_buffers', '')
weechat.hook_signal('buffer_hidden', 'sort_buffers', '')
weechat.hook_signal('buffer_unhidden', 'sort_buffers', '')

BUFFER_TYPES = defaultdict(lambda: 99, core=0, channel=1, query=2)

def hotlist():
    hotlist = weechat.infolist_get("hotlist", "", "")
    while weechat.infolist_next(hotlist):
        yield weechat.infolist_pointer(hotlist, 'buffer_pointer')
    weechat.infolist_free(hotlist)

def buffers():
    buffers = weechat.infolist_get("buffer", "", "")
    while weechat.infolist_next(buffers):
        yield weechat.infolist_pointer(buffers, 'pointer')
    weechat.infolist_free(buffers)

def buffer_key(bufs):
    hidden = min(weechat.buffer_get_integer(buf, "hidden") for buf in bufs)
    localvar_type = min(BUFFER_TYPES[weechat.buffer_get_string(buf, "localvar_type")] for buf in bufs)
    return (hidden, localvar_type)

def hotlist_changed_hook(udata, signal, data):
    for buf in hotlist():
        weechat.buffer_set(buf, "hidden", "0")
    return weechat.WEECHAT_RC_OK

def sort_buffers(udata, signal, buf):
    bufs_dict = defaultdict(set)
    for buf in buffers():
        if weechat.buffer_get_integer(buf, "active") != 0:
           bufs_dict[weechat.buffer_get_integer(buf, "number")].add(buf)

    for i, bufs in enumerate(sorted(bufs_dict.values(), key=buffer_key), 1):
        buf = next(iter(bufs))
        weechat.buffer_set(buf, "number", str(i))
    return weechat.WEECHAT_RC_OK
