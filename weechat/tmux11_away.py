# tmux11away mechanism

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

TIMEOUT_DETACHED = 120
TIMEOUT_IDLE = 1200

import weechat

import os
import stat
import time

weechat.register('tmux11_away', 'Benjamin Richter <br@waldteufel.eu>', '0.1', 'GPL3', 'tmux11away mechanism', '', '')
weechat.hook_timer(2000, 0, 0, 'check_away', '')

last_reason = None

def set_away(reason):
    global last_reason
    if reason == last_reason: return
    weechat.command('', '/away -all ' + reason)
    last_reason = reason

def check_away(data, remaining_calls):
    time_now = time.time()

    tmux_stat = os.stat(os.getenv('TMUX').split(',')[0])
    if (tmux_stat.st_mode & stat.S_IXUSR) == 0 and tmux_stat.st_ctime <= time_now - TIMEOUT_DETACHED:
        set_away('detached')
        return weechat.WEECHAT_RC_OK

    activity_path = os.path.join(os.getenv('XDG_RUNTIME_DIR'), 'activity')
    if os.path.exists(activity_path):
        last_activity = max(tmux_stat.st_ctime, os.stat(activity_path).st_ctime)
    else:
        last_activity = tmux_stat.st_ctime

    if last_activity <= time_now - TIMEOUT_IDLE:
        set_away('idle')
    else:
        set_away('')

    return weechat.WEECHAT_RC_OK
