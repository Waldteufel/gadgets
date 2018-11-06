#!/usr/bin/python
# status bar, to be used with i3bar

import sys
import systemd.journal
import logging

logging.getLogger().addHandler(systemd.journal.JournalHandler())

def log_uncaught_exceptions(*exc_info):
    if isinstance(exc_info[1], KeyboardInterrupt): return
    logging.error('Unhandled exception:', exc_info=exc_info)
sys.excepthook = log_uncaught_exceptions

import os
import math
import json
import time
import threading
import html
import subprocess

import colorsys

from collections import deque, namedtuple

from contextlib import contextmanager
import dbus, dbus.mainloop.glib

import gi
gi.require_version('GUdev', '1.0')
from gi.repository import GObject, GLib, GUdev, Gio


RED_RGB = '#ef2929'
RED_HSV = (0, 29/35, 15/16)

YELLOW_RGB = '#fcaf3e'
YELLOW_HSV = (9/91, 49/65, 84/85)

GREEN_RGB = '#9fee00'
GREEN_HSV = (2/9, 1, 14/15)

GRAY_RGB = '#555753'
GRAY_HSV = (1/4, 4/87, 29/85)

WHITE_RGB = '#eeeeec'
WHITE_HSV = (1/6, 1/100, 14/15)

YELLOW_GRAY_HSV = (9/91, 4/87, 29/85)
RED_WHITE_HSV = (0, 1/100, 14/15)


class Bar(object):

    def __init__(self, stream, events=None):
        self.stream = stream
        self.lock = threading.Lock()
        stream.write('{ "version": 1, "click_events": false }\n')
        stream.write('[')

    def close(self):
        self.stream.write(']')

    @contextmanager
    def update(self):
        with self.lock:
            self.stream.write('[')
            self.first = True
            self.handlers = {}
            yield
            self.stream.write('],\n')
            self.stream.flush()

    def append(self, **kwargs):
        if not self.first:
            self.stream.write(',')
        self.first = False
        self.stream.write(json.dumps(kwargs))


def blend(p, *, low, high):
    mix = colorsys.hsv_to_rgb(*tuple((1 - p) * a + p * b for a, b in zip(low, high)))
    return '#{:02X}{:02X}{:02X}'.format(*tuple(round(255 * v) for v in mix))

def make_block(f):
    if f == 0: return dict(full_text=chr(9630), color=GRAY_RGB)
    elif f > 1: return dict(full_text=chr(9600), color=RED_RGB)
    else: return dict(full_text=chr(9600 + math.ceil(8 * f)))

def get_property(path, prop):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith('#'): continue
                k, v = line.strip().split('=')
                if k == prop:
                    return v
            else:
                return None
    except FileNotFoundError:
        return None

def get_contents(*fn, dtype=str, default=None):
    try:
        ok, data = GLib.file_get_contents(os.path.join(*fn))
        if not ok: return default
        elif dtype is bytes: return data
        else: return dtype(data.decode('utf8').strip())
    except:
        return default

def update_bar():
    if os.getppid() == 1:
        main_loop.quit()

    wpa_supplicant = system_bus.get_object('fi.w1.wpa_supplicant1', '/fi/w1/wpa_supplicant1')

    with bar.update():
        # networks
        for ifname in sorted(os.listdir('/sys/class/net')):
            if ifname == 'lo' or ifname == 'bonding_masters' or ifname.startswith('bond'):
                continue

            ifindex = get_contents('/sys/class/net/{}/ifindex'.format(ifname), dtype=int)

            text = ifname
            color = GRAY_RGB

            if ifname.startswith('wl'):
                try:
                    wifi_interface = system_bus.get_object('fi.w1.wpa_supplicant1', wpa_supplicant.GetInterface(ifname, dbus_interface='fi.w1.wpa_supplicant1'))
                    bss_path = wifi_interface.Get('fi.w1.wpa_supplicant1.Interface', 'CurrentBSS', dbus_interface='org.freedesktop.DBus.Properties')
                    if bss_path != '/':
                        bss = system_bus.get_object('fi.w1.wpa_supplicant1', bss_path)
                        ssid = bss.Get('fi.w1.wpa_supplicant1.BSS', 'SSID', dbus_interface='org.freedesktop.DBus.Properties')
                        text = "{}: {}".format(ifname, bytes(ssid).decode('utf8', errors='replace'))
                    if wifi_interface.Get('fi.w1.wpa_supplicant1.Interface', 'State', dbus_interface='org.freedesktop.DBus.Properties') == 'scanning':
                        color = YELLOW_RGB
                except:
                    logging.exception('while inspecting wifi interface ' + ifname)

            bonding_state = get_contents('/sys/class/net/{}/bonding_slave/state'.format(ifname))
            operstate = get_contents('/sys/class/net/{}/operstate'.format(ifname))

            if operstate != 'down':
                while ifname is not None:
                    if get_property('/run/systemd/netif/links/{}'.format(ifindex), 'OPER_STATE') == 'routable':
                        if bonding_state == 'backup':
                            color = WHITE_RGB
                        else:
                            color = GREEN_RGB
                        break
                    ifname = get_property('/sys/class/net/{}/master/uevent'.format(ifname), 'INTERFACE')
                    ifindex = get_contents('/sys/class/net/{}/ifindex'.format(ifname), dtype=int)

            bar.append(full_text=text, color=color)

        # power
        battery_path = '/sys/class/power_supply/BAT0'
        if os.path.exists(battery_path):
            status = get_contents(battery_path, 'status')
            energy_now = get_contents(battery_path, 'energy_now', dtype=int, default=0) / 1000000
            power_now = get_contents(battery_path, 'power_now', dtype=int, default=0) / 1000000
            alarm = get_contents(battery_path, 'alarm', dtype=int, default=0) / 1000000
            if status == 'Discharging' and power_now > 0:
                p = max(0, 1 - math.exp((alarm - energy_now) / power_now))
                energy_color = blend(p, low=RED_HSV, high=RED_WHITE_HSV)
                power_color = WHITE_RGB
                power_now *= -1
            elif status == 'Charging':
                energy_color = WHITE_RGB
                power_color = YELLOW_RGB
            else: # idle
                energy_color = WHITE_RGB
                power_color = GRAY_RGB
            bar.append(full_text='<span color="{}">{:.0f} Wh</span> <span color="{}">{:+.0f} W*dt</span>'.format(energy_color, energy_now, power_color, power_now), markup='pango')

        # cpu load = 1 - (idle + iowait) / total
        cpuload = 1 - (cpustat_history[-1].idle - cpustat_history[-2].idle + cpustat_history[-1].iowait - cpustat_history[-2].iowait) / (sum(cpustat_history[-1]) - sum(cpustat_history[-2]))
        bar.append(full_text='{:3.0%}'.format(cpuload), color=blend(cpuload, low=YELLOW_GRAY_HSV, high=YELLOW_HSV))

        # cpu temp
        tempcolor = max(0, min(1, (temperature - 70) / 15))
        bar.append(full_text='{:.0f} °C'.format(temperature), color=blend(tempcolor, low=RED_WHITE_HSV, high=RED_HSV))

        # sound recording
        rec_streams = pulse_core.Get('org.PulseAudio.Core1', 'RecordStreams', dbus_interface='org.freedesktop.DBus.Properties')
        if len(rec_streams) > 0:
            bar.append(full_text='● <span rise="-1000">REC</span>', color=RED_RGB, markup='pango')

        # sound volume
        pulse_sink_path = None
        try:
            pulse_sink_path = pulse_core.Get('org.PulseAudio.Core1', 'FallbackSink', dbus_interface='org.freedesktop.DBus.Properties')
        except:
            logging.exception('while determining pulse fallback sink')

        if pulse_sink_path:
            try:
                pulse_sink = pulse_bus.get_object(object_path=pulse_sink_path)
                pulse_vol = pulse_sink.Get('org.PulseAudio.Core1.Device', 'Volume', dbus_interface='org.freedesktop.DBus.Properties')[0] / 65536
                pulse_block = make_block(pulse_vol)
                if pulse_sink.Get('org.PulseAudio.Core1.Device', 'IsNetworkDevice', dbus_interface='org.freedesktop.DBus.Properties'):
                    pulse_block['markup'] = 'pango'
                    pl = pulse_sink.Get('org.PulseAudio.Core1.Device', 'PropertyList', dbus_interface='org.freedesktop.DBus.Properties')
                    host = bytes(pl['device.description'][:-1]).decode('utf8').split('@')[1]
                    pulse_block['full_text'] = '{vol} <span rise="-1000">@{host}</span>'.format(host=html.escape(host), vol=pulse_block['full_text'])
                    if 'color' not in pulse_block:
                        pulse_block['color'] = YELLOW_RGB
                if pulse_sink.Get('org.PulseAudio.Core1.Device', 'Mute', dbus_interface='org.freedesktop.DBus.Properties'):
                    pulse_block['color'] = GRAY_RGB
                bar.append(**pulse_block)
            except:
                logging.exception('while determining sink status')
        else:
            bar.append(full_text='?', color=GRAY_RGB)

        # updates
        #updates = get_contents(os.getenv('HOME'), '.cache/pacman/updates')
        #if updates:
        #    updates = updates.strip().split('\n')
        #    if len(updates) > 0:
        #        bar.append(full_text='▲<span rise="-1000">{}</span>'.format(len(updates)), markup='pango', color=GREEN_RGB)

        # clock
        bar.append(full_text=time.strftime('%b %d'))
        bar.append(full_text=time.strftime('%H:%M'))
    return True

next_update = None

def schedule_update(*args):
    def do_update():
        global next_update
        next_update = None
        update_bar()
        return False
    global next_update
    if next_update is None:
        next_update = GLib.idle_add(do_update)
    return True

CPUStat = namedtuple('CPUStat', ['user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal'])
cpustat_history = deque([CPUStat(0, 0, 0, 0, 0, 0, 0, 0)] * 2, maxlen=2)

def update_stats(*args):
    global temperature
    with open('/proc/stat') as f:
        cpustat_history.append(CPUStat(*(int(x) for x in f.readline().strip().split()[1:-2])))
    temperature = get_contents('/sys/class/thermal/thermal_zone2/temp', dtype=int) / 1000
    return True

GObject.threads_init()
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
main_loop = GObject.MainLoop()

bar = Bar(sys.stdout)

time.sleep(1)

system_bus = dbus.SystemBus()
system_bus.add_signal_receiver(schedule_update, 'PropertiesChanged', 'fi.w1.wpa_supplicant1.Interface')

subprocess.call(['pacmd', 'unload-module module-dbus-protocol'], stdout=subprocess.DEVNULL)
subprocess.call(['pacmd', 'load-module module-dbus-protocol'], stdout=subprocess.DEVNULL)

pulse_bus = dbus.connection.Connection('unix:path=' + os.getenv('XDG_RUNTIME_DIR') + '/pulse/dbus-socket')
pulse_core = pulse_bus.get_object(object_path='/org/pulseaudio/core1')
pulse_bus.add_signal_receiver(schedule_update, 'VolumeUpdated', 'org.PulseAudio.Core1.Device')
pulse_bus.add_signal_receiver(schedule_update, 'MuteUpdated', 'org.PulseAudio.Core1.Device')
pulse_bus.add_signal_receiver(schedule_update, 'FallbackSinkUpdated', 'org.PulseAudio.Core1')
pulse_bus.add_signal_receiver(schedule_update, 'FallbackSinkUnset', 'org.PulseAudio.Core1')
pulse_bus.add_signal_receiver(schedule_update, 'NewRecordStream', 'org.PulseAudio.Core1')
pulse_bus.add_signal_receiver(schedule_update, 'RecordStreamRemoved', 'org.PulseAudio.Core1')
pulse_core.ListenForSignal('org.PulseAudio.Core1.Device.VolumeUpdated', dbus.Array(signature='o'))
pulse_core.ListenForSignal('org.PulseAudio.Core1.Device.MuteUpdated', dbus.Array(signature='o'))
pulse_core.ListenForSignal('org.PulseAudio.Core1.FallbackSinkUpdated', dbus.Array(signature='o'))
pulse_core.ListenForSignal('org.PulseAudio.Core1.FallbackSinkUnset', dbus.Array(signature='o'))
pulse_core.ListenForSignal('org.PulseAudio.Core1.NewRecordStream', dbus.Array(signature='o'))
pulse_core.ListenForSignal('org.PulseAudio.Core1.RecordStreamRemoved', dbus.Array(signature='o'))

udev = GUdev.Client.new(['power_supply'])
udev.connect('uevent', schedule_update)

link_dir = Gio.File.new_for_path('/run/systemd/netif/links')
link_mon = link_dir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
link_mon.connect('changed', schedule_update)

GLib.timeout_add_seconds(5, update_stats)
GLib.timeout_add_seconds(5, schedule_update)

update_stats()
schedule_update()

try:
    main_loop.run()
finally:
    bar.close()
