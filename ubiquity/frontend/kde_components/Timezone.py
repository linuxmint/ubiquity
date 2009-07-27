# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

import datetime
import ubiquity.tz
import math

#contains information about a geographical timezone city
class City:
    def __init__(self, cName, zName, lat, lng, raw_zone):
        self.city_name = cName
        self.zone_name = zName
        self.lat = lat
        self.long = lng
        self.pixmap = None
        # pre-split zone text
        self.raw_zone = raw_zone
        #index in the cities array
        self.index = 0
    
class TimezoneMap(QWidget):
    def __init__(self, frontend):
        QWidget.__init__(self, frontend.userinterface.map_frame)
        self.frontend = frontend
        #dictionary of zone name -> {'cindex', 'citites'}
        self.zones = {}
        # currently active city
        self.selected_city = None
        #dictionary of full name (ie. 'Australia/Sydney') -> city
        self.cities = {}
        self.setObjectName("timezone_map")
        
        #load background pixmap
        self.imagePath = "/usr/share/ubiquity/pixmaps/timezone"
        self.pixmap = QPixmap("%s/bg.png" % self.imagePath)
        
        #redraw timer for selected city time
        self.timer = QTimer(self)
        QApplication.instance().connect(self.timer, SIGNAL("timeout()"), self.update)
        self.timer.start(1000)
        
        #load the pixmaps for the zone overlays
        zones = ['0.0', '1.0', '2.0', '3.0', '3.5', '4.0', '4.5', '5.0', '5.75', '6.0', 
            '6.5', '7.0', '8.0', '9.0', '9.5', '10.0', '10.5', '11.0', '11.5', '12.0', '12.75', '13.0',
            '-1.0', '-2.0', '-3.0', '-3.5', '-4.0', '-5.0', '-5.5', '-6.0', '-7.0', 
            '-8.0', '-9.0', '-9.5', '-10.0', '-11.0']
            
        zonePixmaps = {}
            
        for zone in zones:
            #print '%s/timezone_%s.png' % (self.imagePath, zone)
            zonePixmaps[zone] = QPixmap('%s/timezone_%s.png' % (self.imagePath, zone));
            
        #load the timezones from database
        tzdb = ubiquity.tz.Database()
        for location in tzdb.locations:
            zone_bits = location.zone.split('/')
            
            if len(zone_bits) == 1:
                continue
            
            zoneName = zone_bits[0]
            #join the possible city names for the subregion
            #and replace the _ for a space
            cityName = '/'.join(zone_bits[1:]).replace('_', ' ')
            
            # zone is the hours offset from 0
            zoneHour = (location.raw_utc_offset.seconds)/3600.0 + location.raw_utc_offset.days * 24
            
            #wrap around
            if zoneHour > 13.0:
                zoneHour -= 24.0
            
            # add the zone if we don't have t already listed
            if not self.zones.has_key(zoneName):
                self.zones[zoneName] = {'cities' : [], 'cindex': 0}    
            
            #make new city
            city = City(cityName, zoneName, location.latitude, location.longitude, location.zone)
            
            #set the pixamp to show for the city
            zoneS = str(zoneHour)
            
            #try to find the closest zone
            if not zonePixmaps.has_key(zoneS):
                if zonePixmaps.has_key(str(zoneHour + .25)):
                    zoneS = str(zoneHour + .25)
                elif zonePixmaps.has_key(str(zoneHour + .25)):
                    zoneS = str(zoneHour - .25)
                elif zonePixmaps.has_key(str(zoneHour + .5)):
                    zoneS = str(zoneHour + .5)
                elif zonePixmaps.has_key(str(zoneHour - .5)):
                    zoneS = str(zoneHour - .5)
                else:
                    #no zone...default to nothing
                    zoneS = None
                
            if zoneS:
                city.pixmap = zonePixmaps[zoneS]
            
            self.cities[location.zone] = city
            
            # add the city to the zone list
            city.index = len(self.zones[zoneName]['cities'])
            self.zones[zoneName]['cities'].append(city)
       
        QApplication.instance().connect(self.frontend.userinterface.timezone_zone_combo, 
            SIGNAL("currentIndexChanged(QString)"), self.regionChanged)
        QApplication.instance().connect(self.frontend.userinterface.timezone_city_combo, 
            SIGNAL("currentIndexChanged(int)"), self.cityChanged)
            
        # zone needs to be added to combo box
        keys = self.zones.keys()
        keys.sort()
        for z in keys:
            self.zones[z]['cindex'] = self.frontend.userinterface.timezone_zone_combo.count()
            self.frontend.userinterface.timezone_zone_combo.addItem(z)
       
    # called when the region(zone) combo changes
    def regionChanged(self, region):
        self.frontend.userinterface.timezone_city_combo.clear()
        #blank entry first to prevent a city from being selected
        self.frontend.userinterface.timezone_city_combo.addItem("")
        
        #add all the cities
        for c in self.zones[str(region)]['cities']:
            self.frontend.userinterface.timezone_city_combo.addItem(c.city_name, QVariant(c))
            
    # called when the city combo changes
    def cityChanged(self, cityindex):
        if cityindex < 1:
            return
            
        city = self.frontend.userinterface.timezone_city_combo.itemData(cityindex).toPyObject()
        self.selected_city = city
        self.repaint()
        
    #taken from gtk side
    def longitudeToX(self, longitude):
        # Miller cylindrical map projection is just the longitude as the
        # calculation is the longitude from the central meridian of the projection.
        # Convert to radians.
        x = (longitude * (math.pi / 180)) + math.pi # 0 ... 2pi
        # Convert to a percentage.
        x = x / (2 * math.pi)
        x = x * self.width()
        # Adjust for the visible map starting near 170 degrees.
        # Percentage shift required, grabbed from measurements using The GIMP.
        x = x - (self.width() * 0.039073402)
        return x

    def latitudeToY(self, latitude):
        # Miller cylindrical map projection, as used in the source map from the CIA
        # world factbook.  Convert latitude to radians.
        y = 1.25 * math.log(math.tan((0.25 * math.pi) + \
            (0.4 * (latitude * (math.pi / 180)))))
        # Convert to a percentage.
        y = abs(y - 2.30341254338) # 0 ... 4.606825
        y = y / 4.6068250867599998
        # Adjust for the visible map not including anything beyond 60 degrees south
        # (150 degrees vs 180 degrees).
        y = y * (self.height() * 1.2)
        return y
       
    def paintEvent(self, paintEvent):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        
        if self.selected_city != None:
            c = self.selected_city
            cpos = self.getPosition(c.lat, c.long)
            
            if (c.pixmap):
                painter.drawPixmap(self.rect(), c.pixmap)
            
            painter.drawLine(cpos + QPoint(1,1), cpos - QPoint(1,1))
            painter.drawLine(cpos + QPoint(1,-1), cpos - QPoint(1,-1))
            #painter.drawText(cpos + QPoint(2,-2), c.city_name)
            
            # paint the time instead of the name
            try:
                now = datetime.datetime.now(ubiquity.tz.SystemTzInfo(c.raw_zone))
                timestring = now.strftime('%X')
                
                text_offset = QPoint(2,-2)
            
                # correct the text render position if text will render off widget
                text_size = painter.fontMetrics().size(Qt.TextSingleLine, timestring)
                if cpos.x() + text_size.width() > self.width():
                    text_offset.setX(-text_size.width() - 2)
                if cpos.y() - text_size.height() < 0:
                    text_offset.setY(text_size.height() - 2)
                
                painter.drawText(cpos + text_offset, timestring)
            except ValueError:
                # Some versions of Python have problems with clocks set
                # before the epoch (http://python.org/sf/1646728).
                # ignore and don't display a string
                pass
            
        #debug info for making sure the cities are in proper places
        '''for c in self.zones['America']['cities']:
            cpos = self.getPosition(c.lat, c.long)
            
            painter.drawLine(cpos + QPoint(1,1), cpos - QPoint(1,1))
            painter.drawLine(cpos + QPoint(1,-1), cpos - QPoint(1,-1))
            #painter.drawText(cpos + QPoint(2,-2), c.city_name)'''
        
    # @return pixel coordinate of a latitude and longitude for self
    # map uses Miller Projection, but is also clipped
    def getPosition(self, la, lo):
        # need to add/sub magic numbers because the map doesn't actually go from -180...180, -90...90
        # thus the upper corner is not -180, -90 and we have to compensate
        # we need a better method of determining the actually range so we can better place citites (shtylman)
        xdeg_offset = -6
        # the 180 - 35) accounts for the fact that the map does not span the entire -90 to 90
        # the map does span the entire 360 though, just offset
        x = (self.width() * (180.0 + lo) / 360.0) + (self.width() * xdeg_offset/ 180.0)
        x = x % self.width()
        
        #top and bottom clipping latitudes
        topLat = 81
        bottomLat = -59
        
        #percent of entire possible range
        topPer = topLat/180.0
        totalPer = (topLat - bottomLat)/180.0
        
        # get the y in rectangular coordinates
        y = 1.25 * math.log(math.tan(math.pi/4.0 + 0.4 * math.radians(la)))
        
        # calculate the map range (smaller than full range because the map is clipped on top and bottom
        fullRange = 4.6068250867599998
        # the amount of the full range devoted to the upper hemisphere
        topOffset = fullRange*topPer
        mapRange = abs(1.25 * math.log(math.tan(math.pi/4.0 + 0.4 * math.radians(bottomLat))) - topOffset)
        
        # Convert to a percentage of the map range
        y = abs(y - topOffset)
        y = y / mapRange
        
        # this then becomes the percentage of the height
        y = y * self.height()
        
        return QPoint(int(x), int(y))
        
    def mouseReleaseEvent(self, mouseEvent):
        selected_zone = -1
        
        pos = mouseEvent.pos()
        #rescale mouse coords to have proper x/y position on unscaled image
        x = int(pos.x() * self.pixmap.width()/self.width())
        y = int(pos.y() * self.pixmap.height()/self.height())
        
        # get closest city to the point clicked
        closest = None
        bestdist = 0
        for z in self.zones.values():
            for c in z['cities']:
                np = pos - self.getPosition(c.lat, c.long)
                dist = np.x() * np.x() + np.y() * np.y()
                if (dist < bestdist or closest == None):
                    closest = c
                    bestdist = dist
                    continue
        
        #we need to set the combo boxes
        #this will cause the redraw we need
        if closest != None:
            cindex = self.zones[closest.zone_name]['cindex']
            self.frontend.userinterface.timezone_zone_combo.setCurrentIndex(cindex)
            self.frontend.userinterface.timezone_city_combo.setCurrentIndex(closest.index + 1)

    # sets the timezone based on the full name (i.e 'Australia/Sydney')
    def set_timezone(self, name):
        self._set_timezone(self.cities[name])
    
    # internal set timezone based on a city
    def _set_timezone(self, city):
        cindex = self.zones[city.zone_name]['cindex']
        self.frontend.userinterface.timezone_zone_combo.setCurrentIndex(cindex)
        self.frontend.userinterface.timezone_city_combo.setCurrentIndex(city.index + 1)

    # return the full timezone string
    def get_timezone(self):
        if self.selected_city == None:
            return None
        
        return self.selected_city.raw_zone
