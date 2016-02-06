# forward notifications via irssinotifier

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

import os
import subprocess

weechat.register('irssinotifier_ng', 'Benjamin Richter <br@waldteufel.eu>', '0.1', 'GPL3', 'forward notifications via irssinotifier', '', '')
weechat.hook_print('', 'irc_privmsg', '', 1, 'mobile_notify_hook', '')

def mobile_notify_hook(udata, buf, date, tags, displayed, highlight, prefix, message):
    if os.getenv('TMUX'):
        tmux_path = os.getenv('TMUX').split(',')[0]
        if os.access(tmux_path, os.X_OK):
            return weechat.WEECHAT_RC_OK

    relays = weechat.infolist_get('relay', '', '')
    if relays:
        while weechat.infolist_next(relays):
            status = weechat.infolist_string(relays, 'status_string')
            if status == 'connected':
                weechat.infolist_free(relays)
                return weechat.WEECHAT_RC_OK
        weechat.infolist_free(relays)

    if displayed and (highlight or 'notify_private' in tags.split(',')):
        if weechat.buffer_get_string(buf, 'localvar_type') == 'private':
            channel = '!PRIVATE'
        else:
            channel = weechat.buffer_get_string(buf, 'localvar_name')

        subprocess.check_call(['irssinotifier_ng', message, channel, prefix])

    return weechat.WEECHAT_RC_OK
