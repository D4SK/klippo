from datetime import datetime
import os
import uuid
import xml.etree.ElementTree as ET

from Models.Http.ClusterMaterial import ClusterMaterial
from Models.Http.ClusterPrinterStatus import ClusterPrinterStatus
from Models.Http.ClusterPrintJobStatus import ClusterPrintJobStatus


class ContentManager(object):

    def __init__(self, module):
        self.module = module

        self.printer_status = ClusterPrinterStatus(
            enabled=True,
            firmware_version=self.module.VERSION,
            friendly_name="Super Sayan Printer",
            ip_address=self.module.ADDRESS,
            machine_variant="Ultimaker 3",
            # One of: idle, printing, error, maintenance, booting
            status="idle",
            unique_name="super_sayan_printer",
            uuid=self.new_uuid(),
            configuration=[{ #TODO update
                "extruder_index": 0,
                "material": {
                    "brand": "Generic",
                    "guid": "60636bb4-518f-42e7-8237-fe77b194ebe0",
                    "color": "#8cb219",
                    "material": "ABS",
                    },
                },
            ],
        )
        self.print_jobs = [] # type: [ClusterPrinJobStatus]
        self.materials = [] # type: [ClusterMaterial]

        self.parse_materials()

    def parse_materials(self):
        """
        Read all material files and generate a ClusterMaterial Model.
        For the model only the GUID and version fields are required.
        """
        ns = {"m": "http://www.ultimaker.com/material",
              "cura": "http://www.ultimaker.com/cura"}
        for fname in os.listdir(self.module.MATERIAL_PATH):
            if not fname.endswith(".xml.fdm_material"):
                continue
            path = os.path.join(self.module.MATERIAL_PATH, fname)
            tree = ET.parse(path)
            root = tree.getroot()
            metadata = root.find("m:metadata", ns)
            uuid = metadata.find("m:GUID", ns).text
            version = int(metadata.find("m:version", ns).text)
            self.add_material(uuid, version)

    def add_material(self, uuid, version):
        """Add to the list of local materials"""
        #TODO: read in filament_manager
        new_material = ClusterMaterial(
            guid=uuid,
            version=version,
        )
        self.materials.append(new_material)

    def get_print_job_status(self, filename):
        return ClusterPrintJobStatus(
            created_at=self.get_time_str(),
            force=False,
            machine_variant="Ultimaker 3",
            name=filename,
            started=False,
            # One of: wait_cleanup, finished, sent_to_printer, pre_print,
            # pausing, paused, resuming, queued, printing, post_print
            # (possibly also aborted and aborting)
            status="queued",
            time_total=0, #TODO set from the beginning
            time_elapsed=0,
            uuid=self.new_uuid(),
            configuration=[{"extruder_index": 0}],
            constraints=[],
            assigned_to=self.printer_status.unique_name,
            printer_uuid=self.printer_status.uuid,
        )

    def add_test_print(self, filename):
        """
        Testing only: add a print job outside of klipper and pretend
        we're printing.
        """
        self.print_jobs.append(self.get_print_job_status(filename))
        self.print_jobs[0].status = "printing"
        self.print_jobs[0].started = True
        self.print_jobs[0].time_total = 10000
        self.print_jobs[0].time_elapsed += 2

        self.printer_status.status = "printing"

    def update_printers(self):
        """Update currently loaded material (TODO) and state"""
        state = self.module.sdcard.get_status(
                self.module.reactor.monotonic())["state"]
        if state in {"printing", "paused"}:
            self.printer_status.status = "printing"
        else:
            self.printer_status.status = "idle"

    def update_print_jobs(self):
        """Read queue, Update status, elapsed time"""
        s = self.module.sdcard.get_status(
                self.module.reactor.monotonic())

        # Update self.print_jobs with the queue
        new_print_jobs = []
        for i, fname in enumerate(s["queued_files"]):
            print_job = None
            for j, pj in enumerate(self.print_jobs):
                if pj.name == fname:
                    print_job = self.print_jobs.pop(j)
                    break
            if print_job is None: # Newly add print job
                new_print_jobs.append(self.get_print_job_status(fname))
            else:
                new_print_jobs.append(print_job)
        self.print_jobs = new_print_jobs

        if self.print_jobs: # Update first print job if there is one
            elapsed = self.module.sdcard.get_printed_time(
                    self.module.reactor.monotonic())
            self.print_jobs[0].time_elapsed = elapsed
            self.print_jobs[0].time_total = (
                    s["estimated_remaining_time"] + elapsed)
            if s["state"] in {"printing", "paused"}: # Should cover all cases
                self.print_jobs[0].status = s["state"]
            if s["state"] == "printing":
                self.print_jobs[0].started = True

    @staticmethod
    def new_uuid():
        """Returns a newly generated UUID as a str"""
        # uuid1() returns a uuid based on time and IP address
        # uuid4() would generate a completely random uuid
        return str(uuid.uuid1())

    @staticmethod
    def get_time_str():
        """Returns the current UTC time in a string in ISO8601 format"""
        now = datetime.utcnow()
        return now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def get_printer_status(self):
        if not self.module.testing:
            self.update_printers()
        return [self.printer_status.serialize()]
    def get_print_jobs(self):
        if not self.module.testing:
            self.update_print_jobs()
        return [m.serialize() for m in self.print_jobs]
    def get_materials(self):
        return [m.serialize() for m in self.materials]
