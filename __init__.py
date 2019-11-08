#!/usr/bin/env python2
# coding: utf-8

import os
from sys import argv
if '-t' in argv:
    testing = True
    argv.remove('-t')
else:
    testing = False
if not testing: 
    os.environ['KIVY_WINDOW'] = 'sdl2'
    os.environ['KIVY_GL_BACKEND'] = 'gl'
from os.path import join
from kivy import kivy_data_dir
from kivy.lang import Builder
from kivy.app import App
from kivy.config import Config
from kivy.clock import Clock
from kivy.properties import OptionProperty
from os.path import join
from subprocess import Popen
import threading
import logging
import site

from elements import UltraKeyboard
from settings import *
from home import *
from files import *
from status import *
import parameters as p

#add parent directory to sys.path so main.kv (parser.py) can import from it
site.addsitedir(p.kgui_dir)

#this needs an absolute path otherwise config will only be loaded when working directory is the parent directory
if testing: Config.read(join(p.kgui_dir, "config-test.ini"))
else:       Config.read(join(p.kgui_dir, "config.ini"))

#load a custom style.kv with changes to filechooser and more
Builder.unload_file(join(kivy_data_dir, "style.kv"))
Builder.load_file(join(p.kgui_dir, "style.kv"))

#add threading.thread => inherits start() method to start in new thread
class mainApp(App, threading.Thread):

    # Property for controlling the state as shown in the statusbar.
    state = OptionProperty("normal", options=[
        # Every string set has to be in this list
        "normal",
        "printing",
        "paused",
        "error",
        "initializing",
        ])

    def __init__(self, config = None, **kwargs):# runs in klippy thread
        logging.info("Kivy app initializing...")
        if not testing:
            self.klipper_config = config
            self.printer = self.klipper_config.get_printer()
            self.reactor = self.printer.get_reactor()
            self.printer.register_event_handler("klippy:ready", self.handle_ready)
        super(mainApp, self).__init__(**kwargs)

    def run(self):
        logging.info("Kivy app.run")
        Clock.schedule_once(self.change_vkeyboard, 0)
        super(mainApp, self).run()

    def handle_ready(self):
        self.gcode = self.printer.lookup_object('gcode')
        self.toolhead = self.printer.lookup_object('toolhead')
        self.sdcard = self.printer.lookup_object('virtual_sdcard', None)
        self.fan = self.printer.lookup_object('fan', None)
        self.extruder0 = self.printer.lookup_object('extruder0', None)
        self.extruder1 = self.printer.lookup_object('extruder1', None)
        self.heater_bed = self.printer.lookup_object('heater_bed', None)

    def recieve_speed(self):
        return 77
    def send_speed(self,val):
        print("send {} as speed".format(val))

    def recieve_flow(self):
        return 107
    def send_flow(self,val):
        print("send {} as flow".format(val))

    def recieve_fan(self):
        return 77
    def send_fan(self,val):
        print("send {} as fan".format(val))

    def recieve_temp_A(self):
        return 77
    def send_temp_A(self,val):
        k = self
        self.value = val#temporary should be recieve call afterwards
        print("send {} as Temp A".format(val))

    def recieve_temp_B(self):
        return 77
    def send_temp_B(self,val):
        print("send {} as Temp B".format(val))

    def recieve_temp_bed(self):
        return 77
    def send_temp_bed(self,val):
        print("send {} as Temp bed".format(val))


    def send_up_Z(self):
        print("move Z up")
    def send_down_Z(self):
        print("move Z down")
    def send_stop_Z(self):
        print("stop Z")
    def send_home_Z(self):
        self.reactor.register_async_callback((lambda e: self.gcode.cmd_G28("Z")))
    def send_stop(self):
        print("stop print")
        self.state = "normal"
    def send_play(self):
        print("resume print")
        self.state = "printing"
        nt = Notifications()
        nt.show()
    def send_pause(self):
        print("pause print")
        self.state = "paused"

    def send_calibrate(self):
        print("calibrate")

    def send_acc(self, val):
        print("Sent Accelleration of {} to printer".format(val))
    def request_acc(self):
        return 36

    def poweroff(self):
        Popen(['sudo','systemctl', 'poweroff'])
    def reboot(self):
        Popen(['sudo','systemctl', 'reboot'])
    def restart_klipper(self):
        def restart(e=None):
            self.printer.run_result = 'fimrmware_restart'
            self.printer.reactor.end()
        self.reactor.register_async_callback(restart())
    def quit(self):
        self.stop()

    def change_vkeyboard(self, dt):
        self.root_window.set_vkeyboard_class(UltraKeyboard)
    
def load_config(config): #Entry point
    kgui_object = mainApp(config)
    kgui_object.start()
    return kgui_object

if __name__ == "__main__":
    import time
    mainApp().start()
    if not testing:
        while True:
            time.sleep(1)
