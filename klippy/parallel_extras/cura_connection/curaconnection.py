#!/usr/bin/env python3
"""
Handles the discovery and the server for the  connection with Cura.

This module does not fully run in a seperate thread, but the server
does,  which is doing most of the work  outside of initializing and
shutting down,  which is handled in the CuraConnectionModule class.
"""

import logging
import os
import platform
import socket
import time

import location

from .contentmanager import ContentManager
from . import server
from .zeroconfhandler import ZeroConfHandler


class CuraConnectionModule:

    # How many seconds after the last request to consider disconnected
    # 4.2 allows missing just one update cycle (every 2sec)
    CONNECTION_TIMEOUT = 4.2

    def __init__(self, config):
        self.reactor = config.get_reactor()
        self.reactor.logger.setFormatter(logging.Formatter(
                fmt="%(levelname)s: \t[%(asctime)s] %(message)s"))
        self.testing = config is None

        # Global variables
        self.VERSION = "5.2.11" # We need to disguise as Cura Connect for now
        self.NAME = platform.node()
        self.PATH = os.path.dirname(os.path.realpath(__file__))
        self.SDCARD_PATH = config.location.print_files()
        self.MATERIAL_PATH = location.material_dir()
        self.ADDRESS = None

        self.bom_number = config.get('bom_number', "213482") # Use Ultimaker 3 if not provided
        self.machine_variant = config.get('machine_variant', "Ultimaker 3")
        self.print_core_id = config.get('print_core_id', "AA 0.4")
        self.content_manager = None
        self.zeroconf_handler = None
        self.server = None
        self.metadata = config.get_printer().load_object(config, "gcode_metadata")
        # These are loaded a bit late, they sometimes miss the klippy:connect event
        # klippy:ready works since it only occurs after kguis handle_connect reports back
        self.reactor.cb(self.load_object, "filament_manager")
        self.reactor.cb(self.load_object, "print_history")
        self.reactor.register_event_handler("klippy:ready", self.handle_ready)
        self.reactor.register_event_handler("klippy:disconnect", self.handle_disconnect)

    def handle_ready(self):
        """
        Now it's safe to start the server once there is a network connection
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.wait_for_network()

    def wait_for_network(self, eventtime=0):
        """
        This function executes every 2 seconds until a network
        connection is established.  At that point the IPv4-Address is
        saved and the server started.
        """
        try:
            self.sock.connect(("10.255.255.255", 1))
        except OSError:
            self.reactor.register_callback(self.wait_for_network, self.reactor.monotonic() + 2)
        else:
            self.ADDRESS = self.sock.getsockname()[0]
            self.sock.close()
            self.start()

    def start(self):
        """Start the zeroconf service, and the server in a seperate thread"""
        self.content_manager = ContentManager(self)
        self.zeroconf_handler = ZeroConfHandler(self)
        self.server = server.get_server(self)

        self.zeroconf_handler.start() # Non-blocking
        self.server.start() # Starts server thread
        logging.debug("Cura Connection Server started")

    def handle_disconnect(self, *args):
        """
        This might take a little while, be patient
        can be called before start() e.g. when klipper initialization fails
        """
        if self.server is not None: # Server was started
            self.zeroconf_handler.stop()
            logging.debug("Cura Connection Zeroconf shut down")
            if self.server.is_alive():
                self.server.shutdown()
                self.server.join()
                logging.debug("Cura Connection Server shut down")
        self.reactor.register_async_callback(self.reactor.end)

    def is_connected(self):
        """
        Return true if there currently is an active connection.
        Also see CONNECTION_TIMEOUT
        """
        return (self.server is not None and
                time.time() - self.server.last_request < self.CONNECTION_TIMEOUT)

    def get_thumbnail_path(self, index, filename):
        """Return the thumbnail path for the specified print"""
        md = self.metadata.get_metadata(self.content_manager.klippy_jobs[index].path)
        path = md.get_thumbnail_path()
        if not path or not os.path.exists(path):
            path = os.path.join(self.PATH, "default.png")
        return path

    @staticmethod
    def add_print(printer, path):
        # If the last print ended at least 10 minutes (600 seconds) ago,
        # assume the buildplate is clear
        return printer.objects['virtual_sdcard'].add_print(path, assume_clear_after=600)

    @staticmethod
    def resume_print(printer, uuid):
        return printer.objects['virtual_sdcard'].resume_print()

    @staticmethod
    def pause_print(printer, uuid):
        return printer.objects['virtual_sdcard'].pause_print()

    @staticmethod
    def stop_print(printer, uuid):
        return printer.objects['virtual_sdcard'].stop_print()

    @staticmethod
    def queue_delete(printer, index, uuid):
        """Delete the print job from the queue"""
        return printer.objects['virtual_sdcard'].remove_print(index, uuid)

    @staticmethod
    def queue_move(printer, index, uuid, move):
        return printer.objects['virtual_sdcard'].move_print(index, uuid, move)

    @staticmethod
    def load_object(printer, object_name):
        klipper_config = printer.objects['configfile'].read_main_config()
        printer.load_object(klipper_config, object_name)


def load_config(config):
    """Entry point, called by Klippy"""
    module = CuraConnectionModule(config)
    return module
