#!/usr/bin/python
# status bar, to be used with i3bar

import sys
import os
import math
import json
import time
import threading

import colorsys

from collections import deque

from contextlib import contextmanager
import dbus, dbus.mainloop.glib
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

    def __init__(self, stream):
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

def systemd_get_property(path, prop):
    with open(path) as f:
        for line in f:
            if line.startswith('#'): continue
            k, v = line.strip().split('=')
            if k == prop:
                return v
        else:
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

    with bar.update():
        # networks
        for ifname in os.listdir('/sys/class/net'):
            if ifname == 'lo':
                continue

            ifindex = get_contents('/sys/class/net/{}/ifindex'.format(ifname), dtype=int)

            text = ifname
            color = GRAY_RGB

            if ifname.startswith('wl'):
                wifi_interface = system_bus.get_object('fi.w1.wpa_supplicant1', wpa_supplicant.GetInterface(ifname))
                bss_path = wifi_interface.Get('fi.w1.wpa_supplicant1.Interface', 'CurrentBSS', dbus_interface='org.freedesktop.DBus.Properties')
                if bss_path != '/':
                    bss = system_bus.get_object('fi.w1.wpa_supplicant1', bss_path)
                    ssid = bss.Get('fi.w1.wpa_supplicant1.BSS', 'SSID', dbus_interface='org.freedesktop.DBus.Properties')
                    text = "{}: {}".format(ifname, bytes(ssid).decode('utf8', errors='replace'))
                if wifi_interface.Get('fi.w1.wpa_supplicant1.Interface', 'State', dbus_interface='org.freedesktop.DBus.Properties') == 'scanning':
                    color = YELLOW_RGB

            if systemd_get_property('/run/systemd/netif/links/{}'.format(ifindex), 'OPER_STATE') == 'routable':
                color = GREEN_RGB

            bar.append(full_text=text, color=color)

        # power
        battery_path = '/sys/class/power_supply/BAT0'
        if os.path.exists(battery_path):
            status = get_contents(battery_path, 'status')
            energy_now = get_contents(battery_path, 'energy_now', dtype=int, default=0) / 1000000
            if status == 'Discharging':
                power_now = get_contents(battery_path, 'power_now', dtype=int, default=0) / 1000000
                bar.append(full_text='{:.0f} W'.format(power_now))
                if power_now > 0:
                    alarm = get_contents(battery_path, 'alarm', dtype=int, default=0) / 1000000
                    p = max(0, 1 - math.exp((alarm - energy_now) / power_now))
                    energy_color = blend(p, low=RED_HSV, high=RED_WHITE_HSV)
                else:
                    energy_color = GRAY_RGB
            elif status == 'Charging':
                energy_color = YELLOW_RGB
            elif status == 'Full':
                energy_color = GREEN_RGB
            else: # idle
                energy_color = GRAY_RGB
            bar.append(full_text='{:.0f} Wh'.format(energy_now), color=energy_color)

        # cpu load = 1 - idle time / total time
        cpuload = 1 - (cpustat[-1][3] - cpustat[-2][3]) / (sum(cpustat[-1]) - sum(cpustat[-2]))
        bar.append(full_text='{:3.0%}'.format(cpuload), color=blend(cpuload, low=YELLOW_GRAY_HSV, high=YELLOW_HSV))

        # cpu temp
        temp = get_contents('/sys/class/thermal/thermal_zone1/temp', dtype=int) / 1000
        tempcolor = max(0, min(1, (temp - 70) / 15))
        bar.append(full_text='{:.0f} °C'.format(temp), color=blend(tempcolor, low=RED_WHITE_HSV, high=RED_HSV))

        # sound volume
        pulse_sink = pulse_bus.get_object(object_path=pulse_core.Get('org.PulseAudio.Core1', 'FallbackSink', dbus_interface='org.freedesktop.DBus.Properties'))
        pulse_vol = pulse_sink.Get('org.PulseAudio.Core1.Device', 'Volume', dbus_interface='org.freedesktop.DBus.Properties')[0] / 65535
        pulse_block = make_block(pulse_vol)
        if pulse_sink.Get('org.PulseAudio.Core1.Device', 'Mute', dbus_interface='org.freedesktop.DBus.Properties'):
            pulse_block['color'] = GRAY_RGB
        bar.append(**pulse_block)

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

cpustat = deque([(0,) * 10], maxlen=2)

def update_cpustat(*args):
    with open('/proc/stat') as f:
        cpustat.append(tuple(int(x) for x in f.readline().strip().split()[1:]))
    return True

GObject.threads_init()
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
main_loop = GObject.MainLoop()

bar = Bar(sys.stdout)

time.sleep(1)

system_bus = dbus.SystemBus()
wpa_supplicant = dbus.Interface(system_bus.get_object('fi.w1.wpa_supplicant1', '/fi/w1/wpa_supplicant1'), 'fi.w1.wpa_supplicant1')
system_bus.add_signal_receiver(schedule_update, 'PropertiesChanged', 'fi.w1.wpa_supplicant1.Interface')

pulse_bus = dbus.connection.Connection('unix:path=/run/user/1000/pulse/dbus-socket')
pulse_core = pulse_bus.get_object(object_path='/org/pulseaudio/core1')
pulse_bus.add_signal_receiver(schedule_update, 'VolumeUpdated', 'org.PulseAudio.Core1.Device')
pulse_bus.add_signal_receiver(schedule_update, 'MuteUpdated', 'org.PulseAudio.Core1.Device')
pulse_core.ListenForSignal('org.PulseAudio.Core1.Device.VolumeUpdated', dbus.Array(signature='o'))
pulse_core.ListenForSignal('org.PulseAudio.Core1.Device.MuteUpdated', dbus.Array(signature='o'))

udev = GUdev.Client.new(['power_supply'])
udev.connect('uevent', schedule_update)

link_dir = Gio.File.new_for_path('/run/systemd/netif/links')
link_mon = link_dir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
link_mon.connect('changed', schedule_update)

GLib.timeout_add_seconds(5, update_cpustat)
GLib.timeout_add_seconds(5, schedule_update)

update_cpustat()
schedule_update()

try:
    main_loop.run()
finally:
    bar.close()
