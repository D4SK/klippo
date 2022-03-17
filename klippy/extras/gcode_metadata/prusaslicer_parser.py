import re

from .base_parser import BaseParser

class PrusaSlicerParser(BaseParser):

    PATTERN_DETECT = re.compile("generated by PrusaSlicer",
                                flags=re.IGNORECASE)
    SLICER = "PrusaSlicer"

    # Read the tail when in a UFP file
    _needs_tail=True

    def get_flavor(self):
        return self.options.get("gcode_flavor")

    def get_diameter(self, extruder=0):
        diameter = self.options.get("filament_diameter")
        if not diameter: # Includes case that diameter is 0
            return super().get_diameter()
        return diameter

    def get_density(self, extruder=0):
        density = self.options.get("filament_density")
        if not density:
            return super().get_density()
        return density

    def get_material_amount(self, extruder=None, measure=None):
        length = self.options.get("filament used [mm]")
        return self.convert_filament(length=length, measure=measure)

    pattern_time = re.compile(r"((?P<days>\d+)d\s*)?" +
                              r"((?P<hours>\d+)h\s*)?" +
                              r"((?P<minutes>\d+)m\s*)?" +
                              r"((?P<seconds>\d+)s)?")
    def get_time(self):
        """
        The time is in a format like "2d 5h 23m 12s" or "8m 20s"
        """
        time_str = self.options.get("estimated printing time (normal mode)")
        match = re.match(self.pattern_time, time_str)
        if match:
            seconds = (((int(match["days"] or 0) * 24 +
                         int(match["hours"] or 0)) * 60 +
                        int(match["minutes"] or 0)) * 60 +
                       int(match["seconds"] or 0))
            return seconds
