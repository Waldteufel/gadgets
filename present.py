#!/usr/bin/python3
# present.py - show two pdf presentations in sync (e.g., to show notes on a second screen)
# Benjamin Richter, Feb 2014

# use something like this with i3
# for_window [window_role="presentation_slides"] move container to output VGA1; fullscreen
# for_window [window_role="presentation_notes"] move container to output LVDS1

import os.path
import argparse
from gi.repository import GLib, Gtk, Gdk, Gio, Poppler
import cairo
from datetime import datetime
import time

class Stopwatch(object):

    def __init__(self):
        self.started = time.time()
        self.paused = self.started
        self.offset = 0

    def restart(self):
        self.started = time.time()
        self.paused = None
        self.offset = 0
        return self.started

    def get_time(self):
        now = time.time()
        t = now - self.started
        if self.paused is not None:
            t -= now - self.paused
        t -= self.offset
        return t

    def is_paused(self):
        return self.paused is not None

    def pause(self):
        self.paused = time.time()

    def resume(self):
        self.offset += time.time() - self.paused
        self.paused = None


class PdfWindow(Gtk.Window):

    def __init__(self, role, clip, title_format, show_meta=False):
        Gtk.Window.__init__(self)
        self.page_idx = None
        self.clip = clip
        self.title_format = title_format
        self.show_meta = show_meta
        self.set_role(role)
        self.connect("delete-event", Gtk.main_quit)
        self.connect("key-press-event", key_pressed)
        self.connect("draw", self.draw_slides)
        self.set_app_paintable(True)
        GLib.timeout_add(500, self.redraw_regularily)

    def redraw_regularily(self):
        self.queue_draw()
        return True

    def reload_document(self):
        self.document = Poppler.Document.new_from_file(self.gio_file.get_uri(), None)
        self.set_title(self.title_format.format(self.document.get_title()))
        self.queue_draw()

    def load_document(self, src):
        self.gio_file = Gio.File.new_for_path(src)
        self.reload_document()
        self.monitor = self.gio_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
        def file_changed(monitor, old, new, ev):
            if ev != Gio.FileMonitorEvent.CHANGES_DONE_HINT:
                return

            GLib.timeout_add(100, self.reload_document)
        self.monitor.connect("changed", file_changed)

    def draw_slides(self, widget, cr):
        if self.show_meta and slides_window.page_idx is not None:
            cr.set_source_rgb(0.4, 0.4, 0.8)
        else:
            cr.set_source_rgb(0, 0, 0)
        cr.paint()

        rect = widget.get_allocation()
        if self.page_idx is not None:
            page = self.document.get_page(self.page_idx)
        else:
            page = self.document.get_page(page_idx)
        page_width, page_height = page.get_size()

        clip_left = page_width * self.clip[0]
        clip_top = page_height * self.clip[1]
        clip_right = page_width * self.clip[2]
        clip_bottom = page_height * self.clip[3]

        clip_width = clip_right - clip_left
        clip_height = clip_bottom - clip_top

        if clip_width/clip_height <= rect.width/rect.height:
            scale = rect.height / clip_height
        else:
            scale = rect.width / clip_width

        win_width = rect.width / scale
        win_height = rect.height / scale

        cr.save()
        cr.scale(scale, scale)
        cr.translate(-clip_left, -clip_top)
        cr.translate(win_width/2 - clip_width/2, win_height/2 - clip_height/2)
        cr.rectangle(clip_left, clip_top, clip_width, clip_height)
        cr.clip()
        page.render(cr)
        cr.restore()

        if self.show_meta:
            cr.save()
            cr.select_font_face("Courier", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(24)
            delta = stopwatch.get_time()
            text = "{:.0f}:{:02.0f}".format(delta//60, delta%60)
            ext = cr.text_extents(text)
            cr.move_to(rect.width - ext[2] - 10, 10 + ext[3])
            if stopwatch.is_paused():
                p = (int((time.time()*2) % 2 >= 1) + 1) / 3
                cr.set_source_rgb(p, p, p)
            else:
                cr.set_source_rgb(1, 1, 1)
            cr.text_path(text)
            cr.clip()
            cr.paint()
            cr.restore()


def log_time(text):
    now = datetime.now()
    delta = stopwatch.get_time()
    print('{:>16s} after {:.0f}:{:02.0f} (at {:%X})'.format('{} on {:<3d}'.format(text, page_idx+1), delta//60, delta%60, now))

def key_pressed(widget, ev):
    key = Gdk.keyval_name(ev.keyval)

    if key == 'Left' or key == 'Page_Up':
        set_page(page_idx - 1)
    elif key == 'Right' or key == 'space' or key == 'Page_Down':
        set_page(page_idx + 1)
    elif key == 's':
        log_time('restarted')
        print()
        stopwatch.restart()
    elif key == 'p':
        if stopwatch.is_paused():
            log_time('resumed')
            stopwatch.resume()
        else:
            log_time('paused')
            stopwatch.pause()
    elif key == 'r':
        log_time('reloaded')
        slides_window.reload_document()
        notes_window.reload_document()
    elif key == 'Escape' or key == 'backslash':
        if slides_window.page_idx is None:
            slides_window.page_idx = page_idx
            log_time('froze')
        else:
            slides_window.page_idx = None
            log_time('unfroze')
        slides_window.queue_draw()
        notes_window.queue_draw()
    elif key == 'q':
        Gtk.main_quit()

def set_page(idx):
    global page_idx
    page_idx = max(0, min(slides_window.document.get_n_pages() - 1, idx))
    now = datetime.now()
    log_time('arrived')
    slides_window.queue_draw()
    notes_window.queue_draw()


import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

stopwatch = Stopwatch()
stopwatch.restart()
print('Started at', datetime.now())

arg_parser = argparse.ArgumentParser(description='Show two PDF files in sync.')
arg_parser.add_argument('slides', metavar='SLIDES', help='PDF file to show as slides')
arg_parser.add_argument('notes', metavar='NOTES', help='PDF file to show as notes')
arg_parser.add_argument('-j', metavar='N', dest='page', type=int, default=1, help='Jump to page')
args = arg_parser.parse_args()

slides_window = PdfWindow('presentation_slides', (0, 0, 1, 1), '{} (slides)')
notes_window = PdfWindow('presentation_notes', (0, 0, 1, 1), '{} (notes)', show_meta=True)

slides_window.load_document(args.slides)
notes_window.load_document(args.notes)

set_page(args.page-1)

slides_window.show_all()
notes_window.show_all()

Gtk.main()
log_time('quit')
