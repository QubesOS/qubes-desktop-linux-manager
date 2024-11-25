#!/usr/bin/python3 --
from collections import deque 
import gi
from os import abort
import select
import sys
import time
import traceback
from typing import List
import xcffib
import xcffib.xproto
gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject

class DisgustingX11FullscreenWindowHack(object):
    """
    GTK3 menus have a horrible bug under Xwayland: if the user clicks on a native
    Wayland surface, the menu is not dismissed.  This class works around the problem
    by using evil X11 hacks, such as a fullscreen input-only window.
    """
    def __init__(self) -> None:
        self.keep_going = False
        self.runtime_cb = None
        conn = self.conn = xcffib.connect()

        setup = conn.get_setup()
        if setup.roots_len != 1:
            raise RuntimeError(f"X server has {setup.roots_len} screens, this is not supported")
        screen, = setup.roots
        # This is not guaranteed to work, but assume it will.
        depth_32, = (depth for depth in screen.allowed_depths if depth.depth == 32)
        self.window_id = p = conn.generate_id()
        proto = self.proto = xcffib.xproto.xprotoExtension(conn)
        assert screen.width_in_pixels > 0
        assert screen.height_in_pixels > 0
        fullscreen = "_NET_WM_STATE_FULLSCREEN"
        wm_state_fullscreen_cookie = proto.InternAtom(only_if_exists=False,
                                                      name_len=len(fullscreen),
                                                      name=fullscreen,
                                                      is_checked=True)
        cookie1 = proto.CreateWindow(depth=0,
                                     parent=screen.root,
                                     x=0,
                                     y=0,
                                     wid=p,
                                     width=screen.width_in_pixels,
                                     height=screen.height_in_pixels,
                                     border_width=0,
                                     _class=xcffib.xproto.WindowClass.InputOnly,
                                     visual=depth_32.visuals[0].visual_id,
                                     value_mask=xcffib.xproto.CW.OverrideRedirect|xcffib.xproto.CW.EventMask,
                                     value_list=[0,xcffib.xproto.EventMask.ButtonPress],
                                     is_checked=True)
        wm_state_fullscreen = wm_state_fullscreen_cookie.reply().atom
        cookie2 = proto.ChangeProperty(mode=xcffib.xproto.PropMode.Replace,
                                       window=p,
                                       property=wm_state_fullscreen,
                                       type=xcffib.xproto.Atom.ATOM,
                                       format=32,
                                       data_len=1,
                                       data=[wm_state_fullscreen],
                                       is_checked=True)
        self.cookies = deque([cookie1, cookie2])
        source = GLib.unix_fd_source_new(conn.get_file_descriptor(),
                                         GLib.IOCondition(GLib.IO_IN|GLib.IO_HUP|GLib.IO_PRI))
        GObject.source_set_closure(source, self.source_callback)
        main_loop = GLib.main_context_ref_thread_default()
        assert main_loop is not None
        source_id = source.attach(main_loop)
        self.cb()
    def show_for_widget(self, widget) -> None:
        widget.connect("unmap-event", lambda _unused: self.hide())
        widget.connect("map", lambda _unused: self.show(widget.hide))
    def show(self, cb) -> None:
        if self.keep_going:
            return
        self.keep_going = True
        self.cookies.appendleft(self.proto.MapWindow(self.window_id, is_checked=True))
        self.runtime_cb = cb
        self.cb()
    def unmap(self) -> None:
        if self.keep_going:
            self.cookies.appendleft(self.proto.UnmapWindow(self.window_id, is_checked=True))
            self.keep_going = False
    def cb(self) -> None:
        self.conn.flush()
        while True:
            ev = self.conn.poll_for_event()
            if ev is None:
                return
            if self.cookies and self.cookies[-1].sequence == ev.sequence:
                self.cookies.pop().check()
            if isinstance(ev, xcffib.xproto.ButtonPressEvent):
                if ev.event == self.window_id:
                    self.runtime_cb()
                    self.keep_going = False
    def source_callback(self, fd, flags) -> int:
        try:
            assert fd == self.conn.get_file_descriptor()
            try:
                self.cb()
            except xcffib.ConnectionException:
                self.keep_going = False
                return GLib.SOURCE_REMOVE
            if flags & GLib.IO_HUP:
                self.keep_going = False
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        except BaseException:
            try:
                traceback.print_exc()
            finally:
                abort()

if __name__ == '__main__':
    a = DisgustingX11FullscreenWindowHack()
    main_loop = GLib.main_context_ref_thread_default()
    a.show(lambda *args, **kwargs: None)
    while a.keep_going:
        main_loop.iteration()
